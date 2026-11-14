import { describe, it, expect, vi, beforeEach } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";

const dispatch = vi.fn();
vi.mock("../../src/lib/dispatch", () => ({
  dispatch: (endpoint: string, call: unknown) => dispatch(endpoint, call),
}));

import { AgentCreator } from "../../src/components/AgentCreator";
import { AGENT_INDUSTRY_TEMPLATES } from "../../src/lib/agentIndustryTemplates";
import { I18nProvider } from "../../src/i18n";

describe("AgentCreator industry templates", () => {
  beforeEach(() => {
    dispatch.mockReset();
    dispatch.mockResolvedValue({ data: { success: true, agentId: "new-agent" } });
  });

  const renderCreator = (onCreated = vi.fn()) =>
    render(
      <I18nProvider>
        <AgentCreator onCreated={onCreated} />
      </I18nProvider>
    );

  it("offers every template", () => {
    renderCreator();
    const select = screen.getByLabelText(/industry template/i) as HTMLSelectElement;
    expect(select.options).toHaveLength(AGENT_INDUSTRY_TEMPLATES.length + 1);
  });

  it("fills the form from a template and creates the agent with its tools and prompt", async () => {
    const onCreated = vi.fn();
    renderCreator(onCreated);
    fireEvent.change(screen.getByLabelText(/industry template/i), { target: { value: "healthcare" } });

    const prompt = document.querySelector("textarea") as HTMLTextAreaElement;
    expect(prompt.value).toContain("You never diagnose");
    expect(prompt.value).toContain("answer only from files");

    fireEvent.click(screen.getByRole("button", { name: /create agent/i }));
    await waitFor(() => expect(onCreated).toHaveBeenCalledWith("new-agent"));
    const [endpoint, call] = dispatch.mock.calls[0] as [string, { params: Record<string, unknown> }];
    expect(endpoint).toBe("agentQuery");
    expect(call.params.tools).toEqual(["list_files", "read_file", "search_files", "kb_search"]);
    expect(call.params.category).toBe("knowledge");
    expect(String(call.params.name)).toMatch(/Clinical Procedure Reference/);
  });
});
