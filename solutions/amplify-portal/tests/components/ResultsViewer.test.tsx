import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import type { ReactElement } from "react";

vi.mock("aws-amplify/data", () => ({
  generateClient: () => ({
    queries: { getJobStatus: vi.fn() },
  }),
}));

vi.mock("../../../amplify/data/resource", () => ({}));

import { ResultsViewer } from "../../src/components/ResultsViewer";
import { I18nProvider } from "../../src/i18n";

/** The component reads its copy through useTranslation, which needs the provider. */
const renderWithI18n = (ui: ReactElement) => render(<I18nProvider>{ui}</I18nProvider>);

describe("ResultsViewer", () => {
  it("shows empty state when no execution ARN is provided", () => {
    renderWithI18n(<ResultsViewer executionArn={null} />);
    expect(screen.getByText(/No active job/i)).toBeInTheDocument();
  });

  it("renders the Results heading", () => {
    renderWithI18n(<ResultsViewer executionArn={null} />);
    expect(screen.getByRole("heading", { name: /Results/i })).toBeInTheDocument();
  });

  it("shows loading state when execution ARN is provided", () => {
    renderWithI18n(
      <ResultsViewer executionArn="arn:aws:states:ap-northeast-1:123:execution:test:run-1" />,
    );
    // Component should attempt to fetch and show loading
    expect(screen.getByText(/Loading/i) || screen.getByRole("status")).toBeTruthy();
  });
});
