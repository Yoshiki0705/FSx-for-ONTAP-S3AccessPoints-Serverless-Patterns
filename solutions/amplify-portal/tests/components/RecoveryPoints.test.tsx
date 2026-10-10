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

/** A successful listBackupVaults answer for one Region. */
const okVaults = (region: string) => ({
  backupVaults: [localVault("Default", region), localVault("regional-vault", region)],
  region,
  homeRegion: HOME,
  regions: [HOME, OTHER_REGION],
  error: null,
  errorCode: null,
});

/** What the stubbed handler answers; each test sets what it needs. */
let sharedVaults: unknown[] = [];
let pointsFor: (params: Record<string, unknown>) => unknown = () => ({ recoveryPoints: [point()] });
/** Replaces the listBackupVaults answer (it may reject); null keeps the successful default. */
let vaultsFor: ((params: Record<string, unknown>) => unknown) | null = null;

const respond = () => {
  recoveryPointsQuery.mockImplementation(async (call: Call) => {
    const params = call.params ?? {};
    const region = (params.backupVaultRegion as string | undefined) || HOME;
    if (call.action === "listBackupVaults") {
      return vaultsFor ? vaultsFor(params) : okVaults(region);
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
  vaultsFor = null;
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

describe("RecoveryPoints: a failed vault list does not strand the user", () => {
  const regionSelect = () => screen.getByLabelText("Region") as HTMLSelectElement;

  /** The other Region's vault list fails; the home Region's succeeds. */
  const failOtherRegion = (answer: () => unknown) => {
    vaultsFor = (params) => (params.backupVaultRegion === OTHER_REGION ? answer() : okVaults(HOME));
  };

  const switchToOtherRegionAndBack = async () => {
    renderPanel();
    await screen.findByRole("table");
    await waitFor(() => expect(screen.getByLabelText("Region")).toBeTruthy());

    fireEvent.change(regionSelect(), { target: { value: OTHER_REGION } });
    await screen.findByText(/Could not load the list of vaults in this Region/);
  };

  const failureShapes: Array<[string, () => unknown]> = [
    // What a handler that left the Region context off its failure answers looked like.
    [
      "an error answer without the Region context",
      () => ({ backupVaults: [], error: "The security token included in the request is invalid", errorCode: "UnrecognizedClientException" }),
    ],
    [
      "an error answer that carries the Region context",
      () => ({
        backupVaults: [],
        homeRegion: HOME,
        regions: [HOME, OTHER_REGION],
        error: "The security token included in the request is invalid",
        errorCode: "UnrecognizedClientException",
      }),
    ],
    ["a rejected request", () => Promise.reject(new Error("Network error"))],
  ];

  it.each(failureShapes)("keeps the Region selector and says why, after %s", async (_label, answer) => {
    failOtherRegion(answer);

    await switchToOtherRegionAndBack();

    // The selector is still there, still on the Region that failed.
    expect(regionSelect().value).toBe(OTHER_REGION);
    expect(screen.getByRole("option", { name: HOME })).toBeTruthy();
  });

  it.each(failureShapes)("lets the user return to the home Region after %s", async (_label, answer) => {
    failOtherRegion(answer);
    await switchToOtherRegionAndBack();

    fireEvent.change(regionSelect(), { target: { value: HOME } });

    await screen.findByRole("table");
    expect(regionSelect().value).toBe(HOME);
    expect(vaultSelect().value).toBe("default");
    expect(screen.queryByText(/Could not load the list of vaults in this Region/)).toBeNull();
  });

  it("shows the message of a rejected vault-list request", async () => {
    failOtherRegion(() => Promise.reject(new Error("Network error")));

    await switchToOtherRegionAndBack();

    expect(screen.getByText(/Network error/)).toBeTruthy();
  });

  it("shows the message of an error answer", async () => {
    failOtherRegion(() => ({ backupVaults: [], error: "The security token included in the request is invalid", errorCode: "UnrecognizedClientException" }));

    await switchToOtherRegionAndBack();

    expect(screen.getByText(/The security token included in the request is invalid/)).toBeTruthy();
  });

  it("keeps restore disabled for a row with a Region while the portal's own Region is unknown", async () => {
    // The vault list never answers successfully, so the home Region is never learned,
    // yet the default listing returns a row that names a Region.
    vaultsFor = () => Promise.reject(new Error("Network error"));
    renderPanel();

    await screen.findByRole("table");

    expect((screen.getByRole("button", { name: "Restore" }) as HTMLButtonElement).disabled).toBe(true);
    expect(screen.getByText(/Restore is unavailable until the portal's own Region is known/)).toBeTruthy();
  });

  it("does not disable restore for a row of the home Region once the home Region is known", async () => {
    renderPanel();

    await screen.findByRole("table");
    await waitFor(() => expect(screen.getByLabelText("Region")).toBeTruthy());

    expect((screen.getByRole("button", { name: "Restore" }) as HTMLButtonElement).disabled).toBe(false);
    expect(screen.queryByText(/Restore is unavailable until the portal's own Region is known/)).toBeNull();
  });
});

describe("RecoveryPoints: what a denied or revoked read tells the user", () => {
  it("names only the IAM ARN scope when AWS denies a vault of this account", async () => {
    pointsFor = (params) =>
      params.backupVaultName === "regional-vault"
        ? { recoveryPoints: [], error: "An error occurred (AccessDeniedException)", errorCode: "AccessDeniedException" }
        : { recoveryPoints: [point()], error: null, errorCode: null };
    renderPanel();
    await screen.findByRole("table");
    await waitFor(() => expect(screen.getByRole("option", { name: "regional-vault" })).toBeTruthy());

    fireEvent.change(vaultSelect(), { target: { value: "local:regional-vault" } });

    await screen.findByText(/does not allow this vault's ARN/);
    // A share cannot be the cause for a vault this account owns.
    expect(screen.queryByText(/AWS RAM share was revoked/)).toBeNull();
    expect(screen.queryByText(/share has not been accepted/)).toBeNull();
  });

  it("asks for the shared list again when the handler reports the vault is no longer shared", async () => {
    sharedVaults = [sharedVault()];
    pointsFor = (params) =>
      params.backupVaultAccountId
        ? { recoveryPoints: [], error: "not shared", errorCode: "VaultNotShared" }
        : { recoveryPoints: [point()], error: null, errorCode: null };
    renderPanel();
    await screen.findByRole("table");
    await waitFor(() => expect(screen.getByText(`${OWNER_ACCOUNT} / shared-vault`)).toBeTruthy());
    const before = callsTo("listSharedBackupVaults").length;

    // The owner revoked the share since the list was fetched; the handler is the first to know.
    sharedVaults = [];
    fireEvent.change(vaultSelect(), { target: { value: `shared:${OWNER_ACCOUNT}:shared-vault` } });

    await screen.findByText(/no longer in the list of shared vaults/);
    await waitFor(() => expect(callsTo("listSharedBackupVaults").length).toBeGreaterThan(before));
    // The revoked vault does not stay in the selector until the next manual refresh.
    await waitFor(() => expect(screen.queryByText(`${OWNER_ACCOUNT} / shared-vault`)).toBeNull());
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
