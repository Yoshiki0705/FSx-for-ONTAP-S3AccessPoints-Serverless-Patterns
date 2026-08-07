import { describe, it, expect, vi, beforeEach } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactElement } from "react";

const dispatch = vi.fn();
vi.mock("../../src/lib/dispatch", () => ({
  dispatch: (endpoint: string, call: unknown) => dispatch(endpoint, call),
}));

const currentUserId = vi.fn<() => string | null>();
vi.mock("../../src/hooks/useCurrentUserId", () => ({
  useCurrentUserId: () => currentUserId(),
}));

import { AgentDirectory } from "../../src/components/AgentDirectory";
import { I18nProvider } from "../../src/i18n";

const AGENT = {
  agentId: "a1",
  name: "Contract reader",
  description: "Reads contracts",
  icon: "📄",
  category: "legal",
  tools: ["list_files"],
  isShared: false,
  createdBy: "owner-sub",
  createdAt: 1,
  systemPrompt: "You read contracts.",
  updatedAt: 1,
};

/** Each test gets its own cache so one test's agents do not leak into the next. */
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

/** Route each action to a canned response. */
const respondWith = (overrides: Record<string, unknown> = {}) => {
  dispatch.mockImplementation((_endpoint: string, call: { action: string }) => {
    if (call.action in overrides) return Promise.resolve({ data: overrides[call.action] });
    if (call.action === "listAgents") return Promise.resolve({ data: { agents: [AGENT] } });
    if (call.action === "getAgent") return Promise.resolve({ data: { agent: AGENT } });
    return Promise.resolve({ data: { success: true } });
  });
};

const openDetail = async () => {
  renderUi(<AgentDirectory />);
  await waitFor(() => expect(screen.getByText("Contract reader")).toBeTruthy());
  fireEvent.click(screen.getByText("Contract reader"));
  // "Back to list" appears only in the detail panel, so it marks the transition.
  // The "System Prompt" heading would not: the editor's field label differs from
  // it only by case, which is exactly the kind of near-match worth avoiding here.
  await waitFor(() => expect(screen.getByText(/Back to list/)).toBeTruthy());
};

beforeEach(() => {
  dispatch.mockReset();
  currentUserId.mockReturnValue("owner-sub");
  respondWith();
});

describe("AgentDirectory ownership", () => {
  it("offers edit and delete to the creator", async () => {
    await openDetail();
    expect(screen.getByText(/Edit/)).toBeTruthy();
    expect(screen.getByText(/Delete/)).toBeTruthy();
  });

  it("hides edit and delete from everyone else", async () => {
    // A shared agent is visible to others but is not theirs to change; the
    // registry refuses it server-side, so the buttons would only produce errors.
    currentUserId.mockReturnValue("someone-else");
    await openDetail();
    expect(screen.queryByText(/Edit/)).toBeNull();
    expect(screen.queryByText(/Delete/)).toBeNull();
  });

  it("hides them while the session is still loading", async () => {
    currentUserId.mockReturnValue(null);
    await openDetail();
    expect(screen.queryByText(/Edit/)).toBeNull();
  });
});

describe("AgentDirectory edit", () => {
  const openEditor = async () => {
    await openDetail();
    fireEvent.click(screen.getByText(/Edit/));
    await waitFor(() => expect(screen.getByLabelText("System prompt")).toBeTruthy());
  };

  it("prefills the stored definition", async () => {
    await openEditor();
    expect((screen.getByLabelText("Name") as HTMLInputElement).value).toBe("Contract reader");
    expect((screen.getByLabelText("System prompt") as HTMLTextAreaElement).value).toBe(
      "You read contracts.",
    );
  });

  it("sends every editable field with the agentId", async () => {
    await openEditor();
    fireEvent.change(screen.getByLabelText("Name"), { target: { value: "Lease reader" } });
    fireEvent.click(screen.getByText("Save"));

    await waitFor(() =>
      expect(dispatch.mock.calls.some((c) => c[1].action === "updateAgent")).toBe(true),
    );
    const call = dispatch.mock.calls.find((c) => c[1].action === "updateAgent")![1];
    expect(call.params).toEqual({
      agentId: "a1",
      name: "Lease reader",
      description: "Reads contracts",
      systemPrompt: "You read contracts.",
      category: "legal",
      icon: "📄",
      isShared: false,
    });
  });

  it("shows the new name in the grid without refetching the directory", async () => {
    await openEditor();
    fireEvent.change(screen.getByLabelText("Name"), { target: { value: "Lease reader" } });
    fireEvent.click(screen.getByText("Save"));

    await waitFor(() => expect(screen.getByText("Lease reader")).toBeTruthy());
    // One listAgents on mount, and no second one to learn what was just sent.
    expect(dispatch.mock.calls.filter((c) => c[1].action === "listAgents")).toHaveLength(1);
  });

  it("keeps the form open and reports the error when the save is refused", async () => {
    respondWith({ updateAgent: { error: "Only the creator can update this agent" } });
    await openEditor();
    fireEvent.click(screen.getByText("Save"));

    await waitFor(() =>
      expect(screen.getByText("Only the creator can update this agent")).toBeTruthy(),
    );
    expect(screen.getByLabelText("System prompt")).toBeTruthy();
  });

  it("refuses to save an empty name", async () => {
    await openEditor();
    fireEvent.change(screen.getByLabelText("Name"), { target: { value: "   " } });

    expect((screen.getByText("Save") as HTMLButtonElement).disabled).toBe(true);
  });

  it("discards the draft on cancel", async () => {
    await openEditor();
    fireEvent.change(screen.getByLabelText("Name"), { target: { value: "Discarded" } });
    fireEvent.click(screen.getByText("Cancel"));

    await waitFor(() => expect(screen.queryByLabelText("System prompt")).toBeNull());
    expect(screen.queryByText("Discarded")).toBeNull();
    expect(dispatch.mock.calls.some((c) => c[1].action === "updateAgent")).toBe(false);
  });
});
