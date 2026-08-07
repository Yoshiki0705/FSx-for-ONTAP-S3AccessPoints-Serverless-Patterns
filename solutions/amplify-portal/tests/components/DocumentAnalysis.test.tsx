import { describe, it, expect, vi, beforeEach } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ReactElement } from "react";

const { extractText, analyzeText } = vi.hoisted(() => ({
  extractText: vi.fn(),
  analyzeText: vi.fn(),
}));
vi.mock("aws-amplify/data", () => ({
  generateClient: () => ({ mutations: { extractText, analyzeText } }),
}));

import { DocumentAnalysis } from "../../src/components/DocumentAnalysis";
import { isRegulatedPath } from "../../src/utils/regulatedPath";
import { I18nProvider } from "../../src/i18n";

const renderUi = (ui: ReactElement) => render(<I18nProvider>{ui}</I18nProvider>);

const open = (props: Partial<Parameters<typeof DocumentAnalysis>[0]> = {}) => {
  renderUi(
    <DocumentAnalysis fileKey="contracts/lease.pdf" fileName="lease.pdf" {...props} />,
  );
  fireEvent.click(screen.getByText(/Analyze document/));
};

beforeEach(() => {
  extractText.mockReset();
  analyzeText.mockReset();
});

describe("DocumentAnalysis", () => {
  it("extracts text and reports the page and block counts", async () => {
    extractText.mockResolvedValue({ data: { text: "LEASE", blockCount: 12, pageCount: 3 } });
    open();
    fireEvent.click(screen.getByText("Extract text"));

    await waitFor(() => expect(screen.getByText("LEASE")).toBeTruthy());
    expect(extractText).toHaveBeenCalledWith({ key: "contracts/lease.pdf", mode: "text" });
    // The counts are how a reader tells a whole document from its first page.
    expect(screen.getByText(/Pages: 3/)).toBeTruthy();
    expect(screen.getByText(/Blocks: 12/)).toBeTruthy();
  });

  it("says so when Textract found no text", async () => {
    extractText.mockResolvedValue({ data: { text: "", blockCount: 0, pageCount: 1 } });
    open();
    fireEvent.click(screen.getByText("Extract text"));

    await waitFor(() => expect(screen.getByText("No text detected")).toBeTruthy());
  });

  it("passes the chosen analysis type", async () => {
    analyzeText.mockResolvedValue({ data: { results: { Entities: [] } } });
    open();
    fireEvent.change(screen.getByLabelText("Analysis type"), { target: { value: "sentiment" } });
    fireEvent.click(screen.getByText("Run analysis"));

    await waitFor(() => expect(analyzeText).toHaveBeenCalledTimes(1));
    expect(analyzeText).toHaveBeenCalledWith({
      key: "contracts/lease.pdf",
      analysisType: "sentiment",
    });
  });

  it("accepts Comprehend results as a JSON string", async () => {
    // The schema types `results` as a.json(), which arrives as a string.
    analyzeText.mockResolvedValue({ data: { results: JSON.stringify({ Sentiment: "NEUTRAL" }) } });
    open();
    fireEvent.click(screen.getByText("Run analysis"));

    await waitFor(() => expect(screen.getByText(/NEUTRAL/)).toBeTruthy());
  });

  it("reports an extraction error rather than an empty result box", async () => {
    extractText.mockResolvedValue({ data: { error: "UnsupportedDocumentException" } });
    open();
    fireEvent.click(screen.getByText("Extract text"));

    await waitFor(() => expect(screen.getByText("UnsupportedDocumentException")).toBeTruthy());
    expect(screen.queryByText("Extracted text")).toBeNull();
  });

  it("refuses to send a regulated document to a managed service", async () => {
    open({ blocked: true });

    // The guard is about where the bytes go, and both of these send them out.
    expect(screen.queryByText("Extract text")).toBeNull();
    expect(screen.queryByText("Run analysis")).toBeNull();
    expect(extractText).not.toHaveBeenCalled();
  });
});

describe("isRegulatedPath", () => {
  it("matches the folders the AI guard is about", () => {
    expect(isRegulatedPath("phi/patient.pdf")).toBe(true);
    expect(isRegulatedPath("DICOM/scan.dcm")).toBe(true);
    expect(isRegulatedPath("research/hipaa-2024/notes.txt")).toBe(true);
    expect(isRegulatedPath("team/pii/list.csv")).toBe(true);
  });

  it("does not match a folder that merely contains those letters", () => {
    // "phishing" starts with "phi" but is not a regulated folder.
    expect(isRegulatedPath("phishing-reports/2024.pdf")).toBe(false);
    expect(isRegulatedPath("contracts/lease.pdf")).toBe(false);
  });
});
