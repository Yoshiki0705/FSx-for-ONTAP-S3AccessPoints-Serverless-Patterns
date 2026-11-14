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
  portalSettings: { processingEnabled: false },
}));

import { JobSubmitForm } from "../../src/components/JobSubmitForm";
import { I18nProvider } from "../../src/i18n";

describe("JobSubmitForm", () => {
  const mockOnJobStarted = vi.fn();

  // JobSubmitForm calls useTranslation(), which throws outside I18nProvider.
  function renderForm(initialPrefix: string) {
    return render(
      <I18nProvider>
        <JobSubmitForm initialPrefix={initialPrefix} onJobStarted={mockOnJobStarted} />
      </I18nProvider>
    );
  }

  it("renders the form with pattern selector", () => {
    renderForm("");
    expect(screen.getByLabelText(/Processing Pattern/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/Input Prefix/i)).toBeInTheDocument();
  });

  it("shows 'not configured' message when processing is disabled", () => {
    renderForm("");
    expect(screen.getByRole("alert")).toHaveTextContent(/Processing is not configured/i);
  });

  it("disables submit button when processing is disabled", () => {
    renderForm("docs/");
    expect(screen.getByRole("button", { name: /Start Processing/i })).toBeDisabled();
  });

  it("disables pattern select when processing is disabled", () => {
    renderForm("");
    expect(screen.getByLabelText(/Processing Pattern/i)).toBeDisabled();
  });

  it("pre-fills the prefix from props", () => {
    renderForm("documents/contracts/");
    expect(screen.getByLabelText(/Input Prefix/i)).toHaveValue("documents/contracts/");
  });

  it("lists UC1 to UC28 and OPS1 with the industry and task text", () => {
    renderForm("");
    const options = screen.getAllByRole("option");
    expect(options).toHaveLength(29);
    // The test locale is English (jsdom). UC15 is defense, UC3 is manufacturing: the old list had them mislabeled.
    expect(options[2]).toHaveTextContent(/^UC3 Manufacturing: /);
    expect(options[14]).toHaveTextContent(/^UC15 Defense: /);
    expect(options[28]).toHaveTextContent(/^OPS1 /);
  });
});
