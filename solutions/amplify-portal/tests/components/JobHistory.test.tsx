import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";

const list = vi.fn();
const update = vi.fn();
const getJobStatus = vi.fn();
vi.mock("aws-amplify/data", () => ({
  generateClient: () => ({
    models: { JobExecution: { list: (...a: unknown[]) => list(...a), update: (...a: unknown[]) => update(...a) } },
    queries: { getJobStatus: (...a: unknown[]) => getJobStatus(...a) },
  }),
}));
vi.mock("../../../amplify/data/resource", () => ({}));

import { JobHistory } from "../../src/components/JobHistory";
import { I18nProvider } from "../../src/i18n";

const row = (id: string, status: string, pattern: string) => ({
  id, executionArn: `arn:${id}`, pattern, inputPrefix: "p/", status, startDate: `2026-11-14T0${id}:00:00Z`,
});

describe("JobHistory", () => {
  beforeEach(() => {
    list.mockReset(); update.mockReset(); getJobStatus.mockReset();
  });

  it("stores the final state of rows that still say RUNNING", async () => {
    list.mockResolvedValue({ data: [row("1", "RUNNING", "OPS1_CAPACITY_RIGHTSIZING"), row("2", "SUCCEEDED", "UC10_CONSTRUCTION_BIM")] });
    getJobStatus.mockResolvedValue({ data: { status: "SUCCEEDED", stopDate: "1794639727" } });
    update.mockResolvedValue({ data: {} });
    render(<I18nProvider><JobHistory onSelectExecution={() => {}} /></I18nProvider>);

    await waitFor(() => expect(update).toHaveBeenCalledWith({ id: "1", status: "SUCCEEDED", stopDate: "1794639727" }));
    // Only the RUNNING row is asked about.
    expect(getJobStatus).toHaveBeenCalledTimes(1);
    await waitFor(() => expect(screen.queryByText("RUNNING")).toBeNull());
    // Patterns are shown with their translated industry and task.
    expect(screen.getByText(/^UC10 Construction: /)).toBeInTheDocument();
  });

  it("keeps a row as RUNNING when the status cannot be read", async () => {
    list.mockResolvedValue({ data: [row("1", "RUNNING", "OPS1_CAPACITY_RIGHTSIZING")] });
    getJobStatus.mockRejectedValue(new Error("network"));
    render(<I18nProvider><JobHistory onSelectExecution={() => {}} /></I18nProvider>);
    await waitFor(() => expect(getJobStatus).toHaveBeenCalled());
    expect(update).not.toHaveBeenCalled();
    expect(screen.getByText("RUNNING")).toBeInTheDocument();
  });
});
