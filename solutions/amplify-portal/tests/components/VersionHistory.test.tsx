import { describe, it, expect, vi, beforeEach } from "vitest";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

const { dispatchMock } = vi.hoisted(() => ({ dispatchMock: vi.fn() }));
vi.mock("../../src/lib/dispatch", () => ({ dispatch: (...a: unknown[]) => dispatchMock(...a) }));
vi.mock("../../src/hooks/useStorageAdmin", () => ({ useStorageAdmin: () => false }));
import { VersionHistory } from "../../src/components/VersionHistory";
import { I18nProvider } from "../../src/i18n";

const snapshot = {
  name: "hourly.2026-11-22_0205",
  createTime: "2026-11-22T02:05:00Z",
  snapshotId: "snap-uuid-1",
  state: "valid",
  comment: null,
  expiryTime: null,
  snaplockExpiryTime: null,
  isLocked: false,
};

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <I18nProvider>
        <VersionHistory />
      </I18nProvider>
    </QueryClientProvider>,
  );
}

describe("VersionHistory lock dialog", () => {
  beforeEach(() => dispatchMock.mockReset());

  it("shows a refused lock inside the dialog, where the user is looking", async () => {
    dispatchMock.mockImplementation(async (op: string, args: { action: string }) => {
      if (op === "protectionQuery" && args.action === "listSnapshots") {
        return { data: JSON.stringify({ snapshots: [snapshot], volumeName: "vol1" }) };
      }
      // The handler refuses before it sends anything to ONTAP when snapshot locking is off.
      return { data: JSON.stringify({ success: false, error: "Snapshot locking is not enabled on this volume." }) };
    });
    renderPage();
    const lockButton = await screen.findByRole("button", { name: /ロック|Lock/ });
    fireEvent.click(lockButton);
    const dialog = await screen.findByRole("dialog");
    fireEvent.click(within(dialog).getAllByRole("button")[0]);
    // The consequence dialog opens on top. Acknowledge and apply.
    const checkbox = await screen.findByRole("checkbox");
    fireEvent.click(checkbox);
    const top = checkbox.closest("[role=dialog]") as HTMLElement;
    const buttons = within(top).getAllByRole("button");
    fireEvent.click(buttons[buttons.length - 1]);
    await waitFor(() => expect(dispatchMock).toHaveBeenCalledWith("protectionMutation", expect.objectContaining({ action: "lockSnapshot" })));
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("Snapshot locking is not enabled");
    // The message sits in the lock dialog, not in the page behind it.
    expect(screen.getAllByRole("dialog").some((d) => d.contains(alert))).toBe(true);
  });
});
