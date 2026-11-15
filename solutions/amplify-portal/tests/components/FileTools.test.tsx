import { describe, it, expect, vi, beforeEach } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";

const { toolsQuery, toolsMutation, toolsUseCaseMutation } = vi.hoisted(() => ({
  toolsQuery: vi.fn(),
  toolsMutation: vi.fn(),
  toolsUseCaseMutation: vi.fn(),
}));
vi.mock("aws-amplify/data", () => ({
  generateClient: () => ({ queries: { toolsQuery }, mutations: { toolsMutation, toolsUseCaseMutation } }),
}));

import { FileTools } from "../../src/components/FileTools";
import { I18nProvider } from "../../src/i18n";

const config = (image: boolean) => ({
  data: JSON.stringify({
    success: true,
    tools: { webExtract: true, image, useCases: true },
    image: image ? { region: "us-west-2", modelId: "stability.stable-image-core-v1:1", crossRegion: true } : null,
  }),
});

function renderTools(props: Partial<Parameters<typeof FileTools>[0]> = {}) {
  return render(
    <I18nProvider>
      <FileTools selectedFileKey="team-a/policy.md" selectedFolder="team-a/" canWrite={false} canSaveUseCases={false} {...props} />
    </I18nProvider>,
  );
}

beforeEach(() => {
  toolsQuery.mockReset();
  toolsMutation.mockReset();
  toolsUseCaseMutation.mockReset();
  localStorage.setItem("portal-locale", "en");
});

describe("FileTools", () => {
  it("hides image generation while it is disabled", async () => {
    toolsQuery.mockResolvedValue(config(false));
    renderTools();
    await waitFor(() => expect(toolsQuery).toHaveBeenCalled());
    expect(screen.getByRole("tab", { name: /Translate/ })).toBeTruthy();
    expect(screen.queryByRole("tab", { name: /Image generation/ })).toBeNull();
  });

  it("states that image generation runs outside Japan when it is cross-Region", async () => {
    toolsQuery.mockResolvedValue(config(true));
    renderTools({ canWrite: true, initialTab: "image" });
    await screen.findByRole("note");
    expect(screen.getByRole("note").textContent).toContain("us-west-2");
    expect(screen.getByRole("note").textContent).toContain("outside Japan");
  });

  it("sends only the file key, through the query, when translating the selected file", async () => {
    toolsQuery.mockImplementation(async ({ action }: { action: string }) =>
      action === "config" ? config(false) : { data: JSON.stringify({ success: true, result: "translated text" }) },
    );
    renderTools();
    fireEvent.click(await screen.findByRole("button", { name: /^Translate$/ }));
    await screen.findByText("translated text");
    const call = toolsQuery.mock.calls.find((c) => c[0].action === "translate")![0];
    expect(JSON.parse(call.params)).toMatchObject({ key: "team-a/policy.md", target: "en" });
    expect(JSON.parse(call.params).text).toBeUndefined();
    expect(toolsMutation).not.toHaveBeenCalled();
  });

  it("offers no folder writes without write permission", async () => {
    toolsQuery.mockImplementation(async ({ action }: { action: string }) =>
      action === "config" ? config(false) : { data: JSON.stringify({ success: true, result: "translated text" }) },
    );
    renderTools({ canWrite: false });
    fireEvent.click(await screen.findByRole("button", { name: /^Translate$/ }));
    await screen.findByText("translated text");
    expect(screen.queryByRole("button", { name: /Save to the folder/ })).toBeNull();
  });

  it("lets a viewer save a use case, through the use-case mutation only", async () => {
    toolsQuery.mockImplementation(async ({ action }: { action: string }) =>
      action === "config" ? config(false) : { data: JSON.stringify({ success: true, useCases: [] }) },
    );
    toolsUseCaseMutation.mockResolvedValue({ data: JSON.stringify({ success: true, useCase: {} }) });
    renderTools({ canWrite: false, canSaveUseCases: true, initialTab: "useCases" });
    fireEvent.click(await screen.findByRole("button", { name: /New use case/ }));
    fireEvent.change(screen.getByLabelText("Name"), { target: { value: "Brief" } });
    fireEvent.click(screen.getByRole("button", { name: /^Save$/ }));
    await waitFor(() => expect(toolsUseCaseMutation).toHaveBeenCalled());
    expect(toolsUseCaseMutation.mock.calls[0][0].action).toBe("saveUseCase");
    expect(toolsMutation).not.toHaveBeenCalled();
  });

  it("says a portal role is needed when the account cannot save use cases", async () => {
    toolsQuery.mockImplementation(async ({ action }: { action: string }) =>
      action === "config" ? config(false) : { data: JSON.stringify({ success: true, useCases: [] }) },
    );
    renderTools({ canWrite: false, canSaveUseCases: false, initialTab: "useCases" });
    expect(await screen.findByText(/needs a portal role/)).toBeTruthy();
    expect(screen.queryByRole("button", { name: /New use case/ })).toBeNull();
  });
});
