import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, waitFor, fireEvent, act } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactElement } from "react";

const dispatch = vi.fn();
vi.mock("../../src/lib/dispatch", () => ({
  dispatch: (endpoint: string, call: unknown) => dispatch(endpoint, call),
}));

import { VolumeSelector } from "../../src/components/admin/VolumeSelector";
import { I18nProvider } from "../../src/i18n";
import { setActiveSvm } from "../../src/lib/activeSvm";

/**
 * The selector is the single place six panels get the volume they then act on, so what
 * is tested here is the reporting contract rather than the markup: which volume the
 * parent is told about, and -- the case that has no visible symptom -- that it is told
 * when a pick stops being valid.
 *
 * A volume name is unique within an SVM, not within a file system. Same-named volumes
 * across SVMs are ordinary, so a name held across a scope change does not fail: it
 * resolves, to a different volume. Nothing on screen would say so.
 */

const VOL1 = {
  name: "vol1",
  uuid: "u-vol1",
  sizeGiB: 100,
  state: "online",
  securityStyle: "unix",
  snaplockType: "non_snaplock",
};
const VOL2 = { ...VOL1, name: "vol2", uuid: "u-vol2" };
/** Same name as VOL1, different SVM. This is the pair that makes the void matter. */
const OTHER_SVM_VOL1 = { ...VOL1, uuid: "u-other-vol1" };

const renderUi = (ui: ReactElement) => {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <I18nProvider>{ui}</I18nProvider>
    </QueryClientProvider>,
  );
};

/** The list ONTAP answers with, by active SVM. */
const listPerSvm = (byRequestNumber: Record<string, unknown[]>) => {
  dispatch.mockImplementation(() => {
    const svm = current;
    return Promise.resolve({ data: { volumes: byRequestNumber[svm] ?? [] } });
  });
};

let current = "";

beforeEach(() => {
  dispatch.mockReset();
  current = "";
  setActiveSvm("");
});

afterEach(() => {
  setActiveSvm("");
});

/** Move the portal to another SVM, as the SVM selector does. */
const switchSvm = async (name: string) => {
  current = name;
  await act(async () => {
    setActiveSvm(name);
  });
};

describe("VolumeSelector", () => {
  it("reports the auto-selected volume once", async () => {
    listPerSvm({ "": [VOL1, VOL2] });
    const onSelect = vi.fn();
    renderUi(<VolumeSelector onSelect={onSelect} autoSelectFirst />);

    await waitFor(() => expect(onSelect).toHaveBeenCalledWith(VOL1));
    expect(onSelect).toHaveBeenCalledTimes(1);
  });

  it("reports null when the placeholder is chosen, not the previous volume", async () => {
    listPerSvm({ "": [VOL1, VOL2] });
    const onSelect = vi.fn();
    renderUi(<VolumeSelector onSelect={onSelect} />);

    await waitFor(() => expect(screen.getByText(/vol2 \(100 GiB, unix\)/)).toBeTruthy());
    fireEvent.change(screen.getByRole("combobox"), { target: { value: "u-vol2" } });
    expect(onSelect).toHaveBeenLastCalledWith(VOL2);

    fireEvent.change(screen.getByRole("combobox"), { target: { value: "" } });
    expect(onSelect).toHaveBeenLastCalledWith(null);
  });

  it("voids a pick when the active SVM changes under it", async () => {
    listPerSvm({ "": [VOL1, VOL2], fsxsvm02: [OTHER_SVM_VOL1] });
    const onSelect = vi.fn();
    renderUi(<VolumeSelector onSelect={onSelect} />);

    await waitFor(() => expect(screen.getByText(/vol1 \(100 GiB, unix\)/)).toBeTruthy());
    fireEvent.change(screen.getByRole("combobox"), { target: { value: "u-vol1" } });
    expect(onSelect).toHaveBeenLastCalledWith(VOL1);

    await switchSvm("fsxsvm02");

    // Not the same-named volume on the new SVM, and not the old one either.
    await waitFor(() => expect(onSelect).toHaveBeenLastCalledWith(null));
    const select = screen.getByRole("combobox") as HTMLSelectElement;
    expect(select.value).toBe("");
  });

  it("auto-selects again on the new SVM rather than keeping the old volume", async () => {
    listPerSvm({ "": [VOL1], fsxsvm02: [OTHER_SVM_VOL1] });
    const onSelect = vi.fn();
    renderUi(<VolumeSelector onSelect={onSelect} autoSelectFirst />);

    await waitFor(() => expect(onSelect).toHaveBeenLastCalledWith(VOL1));

    await switchSvm("fsxsvm02");

    // Same name, different volume: only the UUID distinguishes them, which is why the
    // parent is handed the record and not the name.
    await waitFor(() => expect(onSelect).toHaveBeenLastCalledWith(OTHER_SVM_VOL1));
  });

  // A dropdown holding the first page of volumes looks exactly like a complete list, so
  // the operator's volume being absent reads as the volume not existing. Verified here
  // rather than by lowering the handler's page size against hardware, which would have
  // meant leaving a five-volume limit deployed for the length of a screenshot.
  it("says the list is a partial one, and offers search to get past it", async () => {
    dispatch.mockResolvedValue({ data: { volumes: [VOL1, VOL2], truncated: true } });
    renderUi(<VolumeSelector onSelect={vi.fn()} />);

    await waitFor(() => expect(document.querySelector(".volume-selector-truncated")).toBeTruthy());
    expect(document.querySelector(".volume-selector-truncated")?.textContent).toContain("2");
    // The search box appears without being asked for: it is the only way to reach a
    // volume that is not on the page.
    expect(document.querySelector(".volume-selector-search")).toBeTruthy();
  });

  it("shows no partial-list note when the list is complete", async () => {
    dispatch.mockResolvedValue({ data: { volumes: [VOL1, VOL2], truncated: false } });
    renderUi(<VolumeSelector onSelect={vi.fn()} />);

    await waitFor(() => expect(screen.getByText(/vol2 \(100 GiB, unix\)/)).toBeTruthy());
    expect(document.querySelector(".volume-selector-truncated")).toBeNull();
    expect(document.querySelector(".volume-selector-search")).toBeNull();
  });

  it("requests the list again for the new SVM instead of serving the cached one", async () => {
    listPerSvm({ "": [VOL1], fsxsvm02: [OTHER_SVM_VOL1] });
    renderUi(<VolumeSelector onSelect={vi.fn()} />);

    await waitFor(() => expect(dispatch).toHaveBeenCalledTimes(1));

    await switchSvm("fsxsvm02");

    await waitFor(() => expect(dispatch.mock.calls.length).toBeGreaterThan(1));
    await waitFor(() => expect(screen.getByText(/vol1 \(100 GiB, unix\)/)).toBeTruthy());
  });
});
