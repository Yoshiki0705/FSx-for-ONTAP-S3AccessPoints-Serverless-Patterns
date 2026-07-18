import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";

vi.mock("aws-amplify/data", () => ({
  generateClient: () => ({
    queries: { getJobStatus: vi.fn() },
  }),
}));

vi.mock("../../../amplify/data/resource", () => ({}));

import { ResultsViewer } from "../../src/components/ResultsViewer";

describe("ResultsViewer", () => {
  it("shows empty state when no execution ARN is provided", () => {
    render(<ResultsViewer executionArn={null} />);
    expect(screen.getByText(/No active job/i)).toBeInTheDocument();
  });

  it("renders the Results heading", () => {
    render(<ResultsViewer executionArn={null} />);
    expect(screen.getByRole("heading", { name: /Results/i })).toBeInTheDocument();
  });

  it("shows loading state when execution ARN is provided", () => {
    render(<ResultsViewer executionArn="arn:aws:states:ap-northeast-1:123:execution:test:run-1" />);
    // Component should attempt to fetch and show loading
    expect(screen.getByText(/Loading/i) || screen.getByRole("status")).toBeTruthy();
  });
});
