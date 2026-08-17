import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactElement } from "react";

const dispatch = vi.fn();
vi.mock("../../src/lib/dispatch", () => ({
  dispatch: (endpoint: string, call: unknown) => dispatch(endpoint, call),
  // `adminMutate` unwraps the envelope, so returning `{ data: ... }` here would make
  // `data.success` undefined and send every mutation down its failure branch.
  adminMutate: async (call: unknown) => {
    const response = (await dispatch("adminMutation", call)) as { data?: unknown } | null;
    return response?.data ?? null;
  },
}));

import { VolumeMountPanel } from "../../src/components/admin/VolumeMountPanel";
import { I18nProvider } from "../../src/i18n";
import { asVolumeUuid } from "../../src/lib/dispatchActions";

const MOUNTED = {
  volumeName: "vol1",
  svm: "svm1",
  state: "online",
  junctionPath: "/vol1",
  mounted: true,
  suggestedPath: "/vol1",
  nfsLifs: [{ name: "nfs_lif1", address: "10.0.1.10", usable: true }],
  smbLifs: [{ name: "nfs_lif1", address: "10.0.1.10", usable: true }],
  nfsEnabled: true,
  cifsEnabled: true,
  cifsServerName: "FSXSVM01",
  cifsDomain: "EXAMPLE.LOCAL",
  shares: [{ name: "vol1_share", path: "/vol1", encryption: false }],
  nfsReady: true,
  smbReady: true,
  lifError: "",
};

const UNMOUNTED = {
  ...MOUNTED,
  junctionPath: "",
  mounted: false,
  nfsReady: false,
  smbReady: false,
  shares: [],
};

const renderPanel = (ui: ReactElement) => {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <I18nProvider>{ui}</I18nProvider>
    </QueryClientProvider>,
  );
};

const panel = (info: Record<string, unknown>, overrides: Record<string, unknown> = {}) => {
  dispatch.mockImplementation((_endpoint: string, call: { action: string }) => {
    if (call.action in overrides) return Promise.resolve({ data: overrides[call.action] });
    if (call.action === "getVolumeMountInfo") return Promise.resolve({ data: info });
    return Promise.resolve({ data: { success: true } });
  });
  return renderPanel(
    <VolumeMountPanel
      volumeUuid={asVolumeUuid("u-vol1")}
      volumeName="vol1"
      onClose={() => {}}
      onChanged={onChanged}
    />,
  );
};

const onChanged = vi.fn();

/** The parameters of the last call to an action, for asserting what was sent. */
const paramsOf = (action: string) => {
  const call = dispatch.mock.calls
    .map(([, c]) => c as { action: string; params?: Record<string, unknown> })
    .reverse()
    .find((c) => c.action === action);
  return call?.params;
};

beforeEach(() => {
  dispatch.mockReset();
  onChanged.mockReset();
  vi.spyOn(window, "confirm").mockReturnValue(true);
});

describe("VolumeMountPanel", () => {
  it("shows the command with the data LIF address and the junction path", async () => {
    panel(MOUNTED);

    // The address and the path have to appear together: either alone is a command
    // that cannot be pasted.
    await waitFor(() => expect(screen.getByText(/10\.0\.1\.10:\/vol1/)).toBeTruthy());
    expect(screen.getByText(/mount -t nfs/)).toBeTruthy();
  });

  it("offers both UNC forms, by server name and by FQDN", async () => {
    panel(MOUNTED);

    // They fail in different places -- the short form only resolves inside the
    // domain -- so showing one leaves the operator guessing which case they are in.
    await waitFor(() => expect(screen.getByText(/\\\\FSXSVM01\\vol1_share/)).toBeTruthy());
    expect(screen.getByText(/\\\\FSXSVM01\.EXAMPLE\.LOCAL\\vol1_share/)).toBeTruthy();
  });

  it("proposes the volume's own path when it is not mounted", async () => {
    panel(UNMOUNTED);

    const field = await waitFor(() => screen.getByPlaceholderText("/vol1") as HTMLInputElement);
    expect(field.value).toBe("/vol1");
  });

  it("mounts at the proposed path and tells the list to reload", async () => {
    panel(UNMOUNTED, { mountVolume: { success: true, junctionPath: "/vol1" } });

    const button = await waitFor(() => screen.getByRole("button", { name: "Mount" }));
    fireEvent.click(button);

    await waitFor(() => expect(paramsOf("mountVolume")).toBeTruthy());
    expect(paramsOf("mountVolume")).toMatchObject({ volumeUuid: "u-vol1", junctionPath: "/vol1" });
    // Without this the row goes on showing the state from before the mount.
    await waitFor(() => expect(onChanged).toHaveBeenCalled());
  });

  it("mounts at an edited path rather than the proposal", async () => {
    panel(UNMOUNTED, { mountVolume: { success: true, junctionPath: "/data/vol1" } });

    const field = await waitFor(() => screen.getByPlaceholderText("/vol1"));
    fireEvent.change(field, { target: { value: "/data/vol1" } });
    fireEvent.click(screen.getByRole("button", { name: "Mount" }));

    await waitFor(() => expect(paramsOf("mountVolume")?.junctionPath).toBe("/data/vol1"));
  });

  it("does not offer to mount an offline volume", async () => {
    panel({ ...UNMOUNTED, state: "offline" });

    const button = await waitFor(() => screen.getByRole("button", { name: "Mount" }) as HTMLButtonElement);
    // The backend refuses it, and the panel says which step comes first rather than
    // sending a request that is going to be refused.
    expect(button.disabled).toBe(true);
    expect(screen.getByText(/offline/)).toBeTruthy();
  });

  it("sends the confirmation with an unmount", async () => {
    panel(MOUNTED, { unmountVolume: { success: true, alreadyUnmounted: false, previousPath: "/vol1" } });

    fireEvent.click(await waitFor(() => screen.getByRole("button", { name: "Unmount" })));

    await waitFor(() => expect(paramsOf("unmountVolume")).toMatchObject({ confirm: true }));
  });

  it("does not unmount when the confirmation is declined", async () => {
    vi.spyOn(window, "confirm").mockReturnValue(false);
    panel(MOUNTED);

    fireEvent.click(await waitFor(() => screen.getByRole("button", { name: "Unmount" })));

    await waitFor(() => expect(dispatch).toHaveBeenCalled());
    expect(paramsOf("unmountVolume")).toBeUndefined();
  });

  it("reports an already-unmounted volume as that, not as an unmount", async () => {
    panel(MOUNTED, { unmountVolume: { success: true, alreadyUnmounted: true, previousPath: "" } });

    fireEvent.click(await waitFor(() => screen.getByRole("button", { name: "Unmount" })));

    await waitFor(() => expect(screen.getByText("It was already unmounted")).toBeTruthy());
  });

  it("says which of the three reasons blocks an NFS command", async () => {
    panel({ ...MOUNTED, nfsEnabled: false, nfsReady: false });

    // Each reason calls for a different action, so they are not collapsed into one
    // "unavailable" message.
    await waitFor(() => expect(screen.getByText(/NFS is disabled on this SVM/)).toBeTruthy());
    expect(screen.queryByText(/mount -t nfs/)).toBeNull();
  });

  it("says a LIF exists but cannot serve, rather than reporting none", async () => {
    panel({
      ...MOUNTED,
      nfsLifs: [{ name: "nfs_lif1", address: "10.0.1.10", usable: false }],
      nfsReady: false,
    });

    await waitFor(() => expect(screen.getByText(/No usable NFS data LIF/)).toBeTruthy());
  });

  it("explains a missing SMB share instead of showing an empty section", async () => {
    panel({ ...MOUNTED, shares: [], smbReady: false });

    await waitFor(() => expect(screen.getByText(/No SMB share leads to this volume/)).toBeTruthy());
  });
});
