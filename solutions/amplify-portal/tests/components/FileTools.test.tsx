import { describe, it, expect, vi, beforeEach } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";

const { toolsQuery, toolsMutation } = vi.hoisted(() => ({ toolsQuery: vi.fn(), toolsMutation: vi.fn() }));
vi.mock("aws-amplify/data", () => ({
  generateClient: () => ({ queries: { toolsQuery }, mutations: { toolsMutation } }),
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
      <FileTools selectedFileKey="team-a/policy.md" selectedFolder="team-a/" canWrite={false} {...props} />
    </I18nProvider>,
  );
}

beforeEach(() => {
  toolsQuery.mockReset();
  toolsMutation.mockReset();
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
});
