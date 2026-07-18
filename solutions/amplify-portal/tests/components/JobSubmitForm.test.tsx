import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";

vi.mock("aws-amplify/data", () => ({
  generateClient: () => ({
    mutations: { startProcessing: vi.fn() },
  }),
}));

vi.mock("../../../amplify/data/resource", () => ({}));

// Mock portal-settings to test disabled state
vi.mock("../../src/portal-settings", () => ({
  portalSettings: { processingEnabled: false, fileListingEnabled: true },
}));

import { JobSubmitForm } from "../../src/components/JobSubmitForm";

describe("JobSubmitForm", () => {
  const mockOnJobStarted = vi.fn();

  it("renders the form with pattern selector", () => {
    render(<JobSubmitForm initialPrefix="" onJobStarted={mockOnJobStarted} />);
    expect(screen.getByLabelText(/Processing Pattern/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/Input Prefix/i)).toBeInTheDocument();
  });

  it("shows 'not configured' message when processing is disabled", () => {
    render(<JobSubmitForm initialPrefix="" onJobStarted={mockOnJobStarted} />);
    expect(screen.getByRole("alert")).toHaveTextContent(/Processing is not configured/i);
  });

  it("disables submit button when processing is disabled", () => {
    render(<JobSubmitForm initialPrefix="docs/" onJobStarted={mockOnJobStarted} />);
    expect(screen.getByRole("button", { name: /Start Processing/i })).toBeDisabled();
  });

  it("disables pattern select when processing is disabled", () => {
    render(<JobSubmitForm initialPrefix="" onJobStarted={mockOnJobStarted} />);
    expect(screen.getByLabelText(/Processing Pattern/i)).toBeDisabled();
  });

  it("pre-fills the prefix from props", () => {
    render(<JobSubmitForm initialPrefix="documents/contracts/" onJobStarted={mockOnJobStarted} />);
    expect(screen.getByLabelText(/Input Prefix/i)).toHaveValue("documents/contracts/");
  });
});
