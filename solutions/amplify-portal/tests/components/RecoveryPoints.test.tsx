import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

const recoveryPointsQuery = vi.fn();
vi.mock("../../src/lib/dispatch", () => ({
  recoveryPointsQuery: (call: unknown) => recoveryPointsQuery(call),
  restoreMutate: async () => null,
}));

let isStorageAdmin: boolean | null = true;
vi.mock("../../src/hooks/useStorageAdmin", () => ({
  useStorageAdmin: () => isStorageAdmin,
}));

import { RecoveryPoints } from "../../src/components/RecoveryPoints";
import { I18nProvider } from "../../src/i18n";

const HOME = "ap-northeast-1";
const OTHER_REGION = "us-east-1";
// Documentation placeholders, not real accounts.
const OWN_ACCOUNT = "123456789012";
const OWNER_ACCOUNT = "111122223333";
const LAG = "LOGICALLY_AIR_GAPPED_BACKUP_VAULT";

interface Call {
  action: string;
  params?: Record<string, unknown>;
}

const localVault = (name: string, region = HOME) => ({
  backupVaultName: name,
  backupVaultArn: `arn:aws:backup:${region}:${OWN_ACCOUNT}:backup-vault:${name}`,
  ownerAccountId: OWN_ACCOUNT,
  ownedByThisAccount: true,
  region,
  vaultType: "BACKUP_VAULT",
  vaultState: "AVAILABLE",
  encryptionKeyType: "AWS_OWNED_KMS_KEY",
  locked: false,
  numberOfRecoveryPoints: 1,
});

const sharedVault = (name = "shared-vault") => ({
  ...localVault(name),
  backupVaultArn: `arn:aws:backup:${HOME}:${OWNER_ACCOUNT}:backup-vault:${name}`,
  ownerAccountId: OWNER_ACCOUNT,
  ownedByThisAccount: false,
  vaultType: LAG,
});

const point = (overrides: Record<string, unknown> = {}) => ({
  recoveryPointArn: `arn:aws:backup:${HOME}:${OWN_ACCOUNT}:recovery-point:rp-1`,
  resourceArn: `arn:aws:fsx:${HOME}:${OWN_ACCOUNT}:volume/fs-0123/fsvol-0123`,
  resourceType: "FSx",
  creationDate: "2026-01-02T00:00:00+00:00",
  status: "AVAILABLE",
  statusMessage: "",
  backupVaultName: "Default",
  ownerAccountId: OWN_ACCOUNT,
  region: HOME,
  vaultType: "BACKUP_VAULT",
  isEncrypted: true,
  encryptionKeyArn: "",
  backupSizeInBytes: 2048,
  ...overrides,
});

/** What the stubbed handler answers; each test sets what it needs. */
let sharedVaults: unknown[] = [];
let pointsFor: (params: Record<string, unknown>) => unknown = () => ({ recoveryPoints: [point()] });

const respond = () => {
  recoveryPointsQuery.mockImplementation(async (call: Call) => {
    const params = call.params ?? {};
    const region = (params.backupVaultRegion as string | undefined) || HOME;
    if (call.action === "listBackupVaults") {
      return {
        backupVaults: [localVault("Default", region), localVault("regional-vault", region)],
        region,
        homeRegion: HOME,
        regions: [HOME, OTHER_REGION],
        error: null,
        errorCode: null,
      };
    }
    if (call.action === "listSharedBackupVaults") {
      return { backupVaults: sharedVaults, region, error: null, errorCode: null };
    }
    return pointsFor(params);
  });
};

const renderPanel = () => {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <I18nProvider>
        <RecoveryPoints />
      </I18nProvider>
    </QueryClientProvider>,
  );
};

/** Calls made for one action, in order. */
const callsTo = (action: string) =>
  recoveryPointsQuery.mock.calls.map(([call]) => call as Call).filter((call) => call.action === action);

const lastListCall = (): Call | undefined => {
  const calls = callsTo("listRecoveryPoints");
  return calls[calls.length - 1];
};

const vaultSelect = () => screen.getByLabelText("Vault to show") as HTMLSelectElement;

beforeEach(() => {
  recoveryPointsQuery.mockReset();
  isStorageAdmin = true;
  sharedVaults = [];
  pointsFor = () => ({ recoveryPoints: [point()], error: null, errorCode: null });
  respond();
});

afterEach(() => {
  localStorage.removeItem("portal-locale");
});

describe("RecoveryPoints: vault and Region scope", () => {
  it("lists this account's configured vaults first, with no account or vault argument", async () => {
    renderPanel();

    await screen.findByRole("table");

    const first = callsTo("listRecoveryPoints")[0];
    expect(first.params?.backupVaultAccountId).toBeUndefined();
    expect(first.params?.backupVaultName).toBeUndefined();
    expect(first.params?.backupVaultRegion).toBeUndefined();
    expect(vaultSelect().value).toBe("default");
  });

  it("says nothing is shared, and offers no shared group, when the shared list is empty", async () => {
    renderPanel();

    await screen.findByText("No vaults have been shared with this account in this Region.");

    expect(document.querySelector('optgroup[label="Vaults shared by other accounts through AWS RAM"]')).toBeNull();
  });

  it("offers a shared vault by owner and name, and lists its points in the same table", async () => {
    sharedVaults = [sharedVault()];
    pointsFor = (params) =>
      params.backupVaultAccountId === OWNER_ACCOUNT
        ? {
            recoveryPoints: [
              point({
                recoveryPointArn: `arn:aws:backup:${HOME}:${OWNER_ACCOUNT}:recovery-point:rp-shared`,
                backupVaultName: "shared-vault",
                ownerAccountId: OWNER_ACCOUNT,
                vaultType: LAG,
              }),
            ],
          }
        : { recoveryPoints: [point()] };
    renderPanel();
    await screen.findByRole("table");

    await waitFor(() => expect(screen.getByText(`${OWNER_ACCOUNT} / shared-vault`)).toBeTruthy());
    fireEvent.change(vaultSelect(), { target: { value: `shared:${OWNER_ACCOUNT}:shared-vault` } });

    await screen.findByText(`Owner account: ${OWNER_ACCOUNT}`);
    const call = lastListCall();
    expect(call?.params?.backupVaultName).toBe("shared-vault");
    expect(call?.params?.backupVaultAccountId).toBe(OWNER_ACCOUNT);
    // The air-gapped marker comes from the row: a shared vault is not in this
    // account's own vault list.
    expect(screen.getByText(/Logically air-gapped vault/)).toBeTruthy();
    expect(screen.getAllByRole("table")).toHaveLength(1);
  });

  it("asks for a vault when another Region is chosen, rather than reusing the configured set", async () => {
    renderPanel();
    await screen.findByRole("table");

    fireEvent.change(screen.getByLabelText("Region"), { target: { value: OTHER_REGION } });

    await screen.findByText("Select a vault.");
    // The configured vault names belong to the home Region, so no list is requested.
    const regional = callsTo("listRecoveryPoints").filter((c) => c.params?.backupVaultRegion === OTHER_REGION);
    expect(regional).toHaveLength(0);
  });

  it("lists a vault in another Region and disables restore for its rows", async () => {
    pointsFor = (params) =>
      params.backupVaultRegion === OTHER_REGION
        ? {
            recoveryPoints: [
              point({ region: OTHER_REGION, recoveryPointArn: `arn:aws:backup:${OTHER_REGION}:${OWN_ACCOUNT}:recovery-point:rp-2` }),
            ],
          }
        : { recoveryPoints: [point()] };
    renderPanel();
    await screen.findByRole("table");

    // A home Region row restores.
    expect((screen.getByRole("button", { name: "Restore" }) as HTMLButtonElement).disabled).toBe(false);

    fireEvent.change(screen.getByLabelText("Region"), { target: { value: OTHER_REGION } });
    await screen.findByText("Select a vault.");
    await waitFor(() => expect(screen.getByRole("option", { name: "regional-vault" })).toBeTruthy());
    fireEvent.change(vaultSelect(), { target: { value: "local:regional-vault" } });

    await screen.findByText(`Region: ${OTHER_REGION}`);
    const call = lastListCall();
    expect(call?.params?.backupVaultRegion).toBe(OTHER_REGION);
    expect(call?.params?.backupVaultName).toBe("regional-vault");
    expect((screen.getByRole("button", { name: "Restore" }) as HTMLButtonElement).disabled).toBe(true);
    expect(screen.getByText(`A restore can only be started in the portal's own Region (${HOME}).`)).toBeTruthy();
  });

  it("returns to the default view with a notice when the selected share leaves the shared list", async () => {
    sharedVaults = [sharedVault()];
    renderPanel();
    await screen.findByRole("table");
    await waitFor(() => expect(screen.getByText(`${OWNER_ACCOUNT} / shared-vault`)).toBeTruthy());
    fireEvent.change(vaultSelect(), { target: { value: `shared:${OWNER_ACCOUNT}:shared-vault` } });
    await waitFor(() => expect(vaultSelect().value).toBe(`shared:${OWNER_ACCOUNT}:shared-vault`));

    // The owner revokes the AWS RAM share.
    sharedVaults = [];
    fireEvent.click(screen.getByRole("button", { name: "Refresh" }));

    await screen.findByText(/no longer in the list of shared vaults/);
    expect(vaultSelect().value).toBe("default");
  });

  it("shows the same notice when the handler reports the vault is no longer shared", async () => {
    sharedVaults = [sharedVault()];
    pointsFor = (params) =>
      params.backupVaultAccountId
        ? { recoveryPoints: [], error: "not shared", errorCode: "VaultNotShared" }
        : { recoveryPoints: [point()], error: null, errorCode: null };
    renderPanel();
    await screen.findByRole("table");
    await waitFor(() => expect(screen.getByText(`${OWNER_ACCOUNT} / shared-vault`)).toBeTruthy());

    fireEvent.change(vaultSelect(), { target: { value: `shared:${OWNER_ACCOUNT}:shared-vault` } });

    await screen.findByText(/no longer in the list of shared vaults/);
    expect(vaultSelect().value).toBe("default");
  });

  it("names the three possible causes when AWS answers AccessDeniedException", async () => {
    sharedVaults = [sharedVault()];
    pointsFor = (params) =>
      params.backupVaultAccountId
        ? { recoveryPoints: [], error: "An error occurred (AccessDeniedException)", errorCode: "AccessDeniedException" }
        : { recoveryPoints: [point()], error: null, errorCode: null };
    renderPanel();
    await screen.findByRole("table");
    await waitFor(() => expect(screen.getByText(`${OWNER_ACCOUNT} / shared-vault`)).toBeTruthy());

    fireEvent.change(vaultSelect(), { target: { value: `shared:${OWNER_ACCOUNT}:shared-vault` } });

    await screen.findByText(/does not allow this vault's ARN, the AWS RAM share was revoked, or the share has not been accepted/);
  });

  it("shows both the status and the status message of a COMPLETED point that carries one", async () => {
    pointsFor = () => ({
      recoveryPoints: [point({ status: "COMPLETED", statusMessage: "Resource data was only partly captured" })],
    });
    renderPanel();

    await screen.findByRole("table");
    expect(screen.getByText("Resource data was only partly captured")).toBeTruthy();
  });

  it("keeps both selectors on screen while a selection is still loading", async () => {
    renderPanel();
    await screen.findByRole("table");
    await waitFor(() => expect(screen.getByRole("option", { name: "regional-vault" })).toBeTruthy());

    // The next listing never settles. The panel used to be replaced by a spinner while
    // its query was pending, which removed the control being used.
    pointsFor = () => new Promise(() => {});
    fireEvent.change(vaultSelect(), { target: { value: "local:regional-vault" } });

    await waitFor(() => expect(document.querySelector("p.loading")).not.toBeNull());
    expect(screen.getByLabelText("Vault to show")).toBeTruthy();
    expect(screen.getByLabelText("Region")).toBeTruthy();
  });

  it("hides the restore column from users outside storage-admin", async () => {
    isStorageAdmin = false;
    renderPanel();

    await screen.findByRole("table");

    expect(screen.queryByRole("button", { name: "Restore" })).toBeNull();
    expect(screen.queryByRole("columnheader", { name: "Actions" })).toBeNull();
  });
});

describe("RecoveryPoints: where monitoring is described", () => {
  it("links to the English Observability page, in a new tab, without an opener", async () => {
    renderPanel();
    await screen.findByRole("table");

    const link = screen.getByRole("link", { name: /Open the Observability documentation/ }) as HTMLAnchorElement;

    expect(link.href).toBe(
      "https://github.com/Yoshiki0705/FSx-for-ONTAP-Observability-integrations/blob/main/docs/en/cyber-resilience-capability-map.md",
    );
    expect(link.target).toBe("_blank");
    expect(link.rel).toBe("noopener noreferrer");
  });

  it("links to the Japanese page in the Japanese locale", async () => {
    localStorage.setItem("portal-locale", "ja");
    renderPanel();
    await screen.findByRole("table");

    const link = screen.getByRole("link", { name: /Observability 側の説明を開く/ }) as HTMLAnchorElement;

    expect(link.href).toBe(
      "https://github.com/Yoshiki0705/FSx-for-ONTAP-Observability-integrations/blob/main/docs/ja/cyber-resilience-capability-map.md",
    );
  });

  it("states that this panel does not monitor job failures or share revocation", async () => {
    renderPanel();

    await screen.findByText(/This portal does not monitor job failures/);
  });
});
