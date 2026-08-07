import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactElement } from "react";

const { getFileMetadata } = vi.hoisted(() => ({ getFileMetadata: vi.fn() }));
vi.mock("aws-amplify/data", () => ({
  generateClient: () => ({ queries: { getFileMetadata } }),
}));

import { AiMetadataBadges, useAiMetadata } from "../../src/components/AiMetadataBadges";
import { I18nProvider } from "../../src/i18n";

const renderUi = (ui: ReactElement) => {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <I18nProvider>{ui}</I18nProvider>
    </QueryClientProvider>,
  );
};

/** Exercises the hook the explorer uses, without rendering the explorer. */
function Probe({ keys }: { keys: string[] }) {
  const { data } = useAiMetadata(keys);
  return (
    <div>
      <span data-testid="size">{data ? String(data.size) : "none"}</span>
      {keys.map((k) => (
        <AiMetadataBadges key={k} metadata={data?.get(k)} />
      ))}
    </div>
  );
}

beforeEach(() => {
  getFileMetadata.mockReset();
});

describe("useAiMetadata", () => {
  it("asks for every key on the page in one call", async () => {
    getFileMetadata.mockResolvedValue({ data: { metadata: [] } });
    renderUi(<Probe keys={["a.pdf", "b.pdf", "c.pdf"]} />);

    await waitFor(() => expect(getFileMetadata).toHaveBeenCalledTimes(1));
    expect(getFileMetadata).toHaveBeenCalledWith({ fileKeys: ["a.pdf", "b.pdf", "c.pdf"] });
  });

  it("does not call the backend for an empty folder", () => {
    renderUi(<Probe keys={[]} />);
    expect(getFileMetadata).not.toHaveBeenCalled();
  });

  it("accepts the metadata list as a JSON string", async () => {
    // The schema types `metadata` as a.json(), which arrives as a string.
    getFileMetadata.mockResolvedValue({
      data: { metadata: JSON.stringify([{ fileKey: "a.pdf", classification: "INTERNAL" }]) },
    });
    renderUi(<Probe keys={["a.pdf"]} />);

    await waitFor(() => expect(screen.getByText("INTERNAL")).toBeTruthy());
  });

  it("treats an unconfigured metadata table as nothing processed, not an error", async () => {
    getFileMetadata.mockResolvedValue({
      data: { metadata: [], error: "AI metadata table not configured" },
    });
    renderUi(<Probe keys={["a.pdf"]} />);

    await waitFor(() => expect(screen.getByTestId("size").textContent).toBe("0"));
    // No badges and no error: a deployment that never ran a pattern is normal.
    expect(screen.queryByText(/not configured/)).toBeNull();
  });
});

describe("AiMetadataBadges", () => {
  it("renders nothing when a file has no metadata", () => {
    const { container } = renderUi(<AiMetadataBadges metadata={undefined} />);
    expect(container.querySelector(".ai-meta-badges")).toBeNull();
  });

  it("renders nothing when the record exists but is empty", () => {
    // A row processed by a pattern that recorded no findings should not sprout an
    // empty chip.
    const { container } = renderUi(<AiMetadataBadges metadata={{ fileKey: "a.pdf" }} />);
    expect(container.querySelector(".ai-meta-badges")).toBeNull();
  });

  it("marks a sensitive classification differently from a neutral one", () => {
    const { container: sensitive } = renderUi(
      <AiMetadataBadges metadata={{ fileKey: "a", classification: "CONFIDENTIAL" }} />,
    );
    expect(sensitive.querySelector(".ai-meta-badge.sensitive")).not.toBeNull();

    const { container: neutral } = renderUi(
      <AiMetadataBadges metadata={{ fileKey: "b", classification: "INTERNAL" }} />,
    );
    expect(neutral.querySelector(".ai-meta-badge.sensitive")).toBeNull();
  });

  it("omits zero counts rather than showing a badge reading 0", () => {
    renderUi(
      <AiMetadataBadges
        metadata={{ fileKey: "a", rekognitionLabels: 0, comprehendEntities: 4 }}
      />,
    );
    expect(screen.getByText(/4/)).toBeTruthy();
    expect(screen.queryByText(/🏞/)).toBeNull();
  });

  it("offers the summary as a tooltip rather than inline text", () => {
    renderUi(
      <AiMetadataBadges metadata={{ fileKey: "a", bedrockSummary: "A lease agreement." }} />,
    );
    expect(screen.getByTitle("A lease agreement.")).toBeTruthy();
    expect(screen.queryByText("A lease agreement.")).toBeNull();
  });
});
