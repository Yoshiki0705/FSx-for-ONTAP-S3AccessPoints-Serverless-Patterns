import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactElement } from "react";

const dispatch = vi.fn();
vi.mock("../../src/lib/dispatch", () => ({
  dispatch: (endpoint: string, call: unknown) => dispatch(endpoint, call),
  // The real `adminMutate` puts the response through `parseResponse`, so callers
  // receive the payload rather than the `{ data: ... }` envelope. Returning the
  // envelope here made `data.success` undefined, so every mutation in this file
  // took the failure branch and no test could reach the code after a successful
  // create or delete.
  adminMutate: async (call: unknown) => {
    const response = (await dispatch("adminMutation", call)) as { data?: unknown } | null;
    return response?.data ?? null;
  },
}));

import { QtreeManager } from "../../src/components/admin/QtreeManager";
import { I18nProvider } from "../../src/i18n";

const VOLUME = { name: "vol1", uuid: "u-vol1", state: "online", size: 1, type: "rw" };
const QTREE = {
  id: "1",
  name: "team_share",
  volumeName: "vol1",
  securityStyle: "unix",
  exportPolicy: "default",
};

const renderUi = (ui: ReactElement) => {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <I18nProvider>{ui}</I18nProvider>
    </QueryClientProvider>,
  );
};

const respondWith = (overrides: Record<string, unknown> = {}) => {
  dispatch.mockImplementation((_endpoint: string, call: { action: string }) => {
    if (call.action in overrides) return Promise.resolve({ data: overrides[call.action] });
    if (call.action === "listVolumes") return Promise.resolve({ data: { volumes: [VOLUME] } });
    if (call.action === "listQtrees") return Promise.resolve({ data: { qtrees: [QTREE] } });
    return Promise.resolve({ data: { success: true } });
  });
};

/** Actions the component asked for, in order. */
const actionsCalled = () =>
  dispatch.mock.calls.map(([, call]) => (call as { action: string }).action);

/**
 * The panel-level spinner, which is the one that used to stick.
 *
 * Not `getByText("Loading...")`: the volume dropdown shows that same word in an
 * `<option>` while volumes load, and that one is correct. Matching on the text
 * alone would pass on the bug and fail on the fix.
 */
const panelSpinner = () => document.querySelector("p.loading");

beforeEach(() => {
  dispatch.mockReset();
  respondWith();
});

describe("QtreeManager", () => {
  // The panel lists qtrees for one volume, so its query is disabled until a
  // volume is chosen — and the control that chooses one lives inside the panel.
  // Treating "no volume yet" as "loading" replaced the panel with a spinner,
  // which removed the volume control, which meant no volume was ever chosen.
  // Nothing was ever requested and the spinner never cleared.
  it("renders the volume control before a volume is chosen", () => {
    renderUi(<QtreeManager />);

    expect(screen.getByRole("heading", { name: "Qtrees" })).toBeTruthy();
    expect(screen.getByRole("combobox")).toBeTruthy();
    expect(panelSpinner()).toBeNull();
  });

  it("says a volume is needed rather than reporting none found", () => {
    // No volumes to auto-select, so the panel stays on the empty state.
    respondWith({ listVolumes: { volumes: [] } });
    renderUi(<QtreeManager />);

    expect(screen.getByText("— Select a volume —")).toBeTruthy();
    expect(screen.queryByText("No qtrees found")).toBeNull();
  });

  it("requests qtrees for the auto-selected volume", async () => {
    renderUi(<QtreeManager />);

    await waitFor(() => expect(actionsCalled()).toContain("listQtrees"));

    const call = dispatch.mock.calls.find(
      ([, c]) => (c as { action: string }).action === "listQtrees",
    );
    expect((call?.[1] as { params: { volumeName: string } }).params.volumeName).toBe("vol1");
    await waitFor(() => expect(screen.getByText("team_share")).toBeTruthy());
  });

  // ONTAP reports the volume's own root as a qtree with an empty name, so every volume
  // has one. Rendered plainly it was a blank cell with a delete button beside it, which
  // reads as a record whose name failed to load and offers an action ONTAP refuses.
  describe("the volume's root qtree", () => {
    const ROOT = { ...QTREE, id: "0", name: "" };

    it("is named rather than left blank", async () => {
      respondWith({ listQtrees: { qtrees: [ROOT] } });
      renderUi(<QtreeManager />);

      await waitFor(() => expect(screen.getByText("(volume root)")).toBeTruthy());
    });

    it("offers no delete button", async () => {
      respondWith({ listQtrees: { qtrees: [ROOT, QTREE] } });
      renderUi(<QtreeManager />);

      await waitFor(() => expect(screen.getByText("team_share")).toBeTruthy());
      // One button for the real qtree, none for the root.
      expect(screen.getAllByRole("button", { name: "✕" })).toHaveLength(1);
    });
  });

  // The form used to carry a volume selector of its own, independent of the one
  // filtering the list. Creating a qtree could therefore put it in a volume the
  // table was not showing: "Qtree created" appeared above an unchanged table,
  // which reads as a create that quietly failed. The volume is now the one
  // selected in the panel header, as in the quota, snaplock and snapshot panels.
  describe("the create form", () => {
    const openForm = async () => {
      renderUi(<QtreeManager />);
      // Wait for the auto-selected volume, which is what the form will target.
      await waitFor(() => expect(actionsCalled()).toContain("listQtrees"));
      fireEvent.click(screen.getByRole("button", { name: "+ Create Qtree" }));
    };

    it("has no volume selector of its own", async () => {
      await openForm();

      // The panel header's selector, and no second one inside the form.
      expect(document.querySelectorAll(".volume-selector")).toHaveLength(1);
    });

    it("states which volume the qtree will be created in", async () => {
      await openForm();

      const shown = document.querySelector(".form-static-value");
      expect(shown?.textContent).toBe("vol1");
    });

    it("creates in the volume the list is filtered to", async () => {
      await openForm();

      fireEvent.change(screen.getByPlaceholderText("qtree_name"), {
        target: { value: "new_share" },
      });
      fireEvent.click(screen.getByRole("button", { name: "Create" }));

      await waitFor(() => expect(actionsCalled()).toContain("createQtree"));
      const call = dispatch.mock.calls.find(
        ([, c]) => (c as { action: string }).action === "createQtree",
      );
      expect((call?.[1] as { params: Record<string, unknown> }).params).toMatchObject({
        volumeName: "vol1",
        name: "new_share",
      });
    });

    it("reloads the list after creating, so the new qtree is visible", async () => {
      await openForm();
      const before = actionsCalled().filter((a) => a === "listQtrees").length;

      fireEvent.change(screen.getByPlaceholderText("qtree_name"), {
        target: { value: "new_share" },
      });
      fireEvent.click(screen.getByRole("button", { name: "Create" }));

      await waitFor(() =>
        expect(actionsCalled().filter((a) => a === "listQtrees").length).toBeGreaterThan(before),
      );
    });

    it("cannot be opened before a volume is chosen", () => {
      respondWith({ listVolumes: { volumes: [] } });
      renderUi(<QtreeManager />);

      const button = screen.getByRole("button", { name: "+ Create Qtree" });
      expect((button as HTMLButtonElement).disabled).toBe(true);
    });
  });

  it("reports a listing failure instead of loading forever", async () => {
    respondWith({ listQtrees: { qtrees: [], error: "ONTAP rejected the credentials" } });
    renderUi(<QtreeManager />);

    await waitFor(() =>
      expect(screen.getByText(/ONTAP rejected the credentials/)).toBeTruthy(),
    );
    expect(panelSpinner()).toBeNull();
  });
});
