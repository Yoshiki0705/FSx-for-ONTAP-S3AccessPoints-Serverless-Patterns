import { describe, it, expect, vi, beforeEach } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactElement } from "react";

// The component calls generateClient at module scope, so the spy has to exist
// before the mock factory runs. vi.mock is hoisted above plain const declarations;
// vi.hoisted is not.
const { browseCatalog } = vi.hoisted(() => ({ browseCatalog: vi.fn() }));
vi.mock("aws-amplify/data", () => ({
  generateClient: () => ({ queries: { browseCatalog } }),
}));

import { CatalogBrowser } from "../../src/components/CatalogBrowser";
import { I18nProvider } from "../../src/i18n";

const renderUi = (ui: ReactElement) => {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <I18nProvider>{ui}</I18nProvider>
    </QueryClientProvider>,
  );
};

/** Answer each catalog action, so the three levels can be walked in a test. */
const catalog = (overrides: Record<string, unknown> = {}) => {
  browseCatalog.mockImplementation((args: { action: string }) => {
    if (args.action in overrides) return Promise.resolve({ data: overrides[args.action] });
    if (args.action === "listDatabases") {
      return Promise.resolve({ data: { databases: [{ name: "analytics", description: "" }] } });
    }
    if (args.action === "listTables") {
      return Promise.resolve({
        data: { tables: [{ name: "s3_objects", description: "", columns: 3, location: "s3://x/" }] },
      });
    }
    return Promise.resolve({
      data: {
        schema: [{ name: "key", type: "string" }],
        partitionKeys: [{ name: "dt", type: "string" }],
        location: "s3://x/",
      },
    });
  });
};

beforeEach(() => {
  browseCatalog.mockReset();
  catalog();
});

describe("CatalogBrowser", () => {
  it("reads nothing until it is opened", () => {
    renderUi(<CatalogBrowser onSelectTable={vi.fn()} />);
    // Three Glue calls on every visit to the analytics tab would be three calls
    // for nothing on a deployment with no crawler.
    expect(browseCatalog).not.toHaveBeenCalled();
  });

  it("lists databases once opened", async () => {
    renderUi(<CatalogBrowser onSelectTable={vi.fn()} />);
    fireEvent.click(screen.getByText(/Browse data catalog/));

    await waitFor(() => expect(screen.getByText("analytics")).toBeTruthy());
    expect(browseCatalog).toHaveBeenCalledWith({ action: "listDatabases" });
  });

  it("walks database to table to schema", async () => {
    renderUi(<CatalogBrowser onSelectTable={vi.fn()} />);
    fireEvent.click(screen.getByText(/Browse data catalog/));
    await waitFor(() => expect(screen.getByText("analytics")).toBeTruthy());

    fireEvent.click(screen.getByText("analytics"));
    await waitFor(() => expect(screen.getByText("s3_objects")).toBeTruthy());
    expect(browseCatalog).toHaveBeenCalledWith({ action: "listTables", database: "analytics" });

    fireEvent.click(screen.getByText("s3_objects"));
    await waitFor(() => expect(screen.getByText("key")).toBeTruthy());
    expect(browseCatalog).toHaveBeenCalledWith({
      action: "getSchema",
      database: "analytics",
      table: "s3_objects",
    });
  });

  it("labels partition keys, which are not ordinary columns", async () => {
    renderUi(<CatalogBrowser onSelectTable={vi.fn()} />);
    fireEvent.click(screen.getByText(/Browse data catalog/));
    await waitFor(() => expect(screen.getByText("analytics")).toBeTruthy());
    fireEvent.click(screen.getByText("analytics"));
    await waitFor(() => expect(screen.getByText("s3_objects")).toBeTruthy());
    fireEvent.click(screen.getByText("s3_objects"));

    await waitFor(() => expect(screen.getByText("dt")).toBeTruthy());
    expect(screen.getByText("partition")).toBeTruthy();
  });

  it("hands the chosen table back to the query editor", async () => {
    const onSelectTable = vi.fn();
    renderUi(<CatalogBrowser onSelectTable={onSelectTable} />);
    fireEvent.click(screen.getByText(/Browse data catalog/));
    await waitFor(() => expect(screen.getByText("analytics")).toBeTruthy());
    fireEvent.click(screen.getByText("analytics"));
    await waitFor(() => expect(screen.getByText("s3_objects")).toBeTruthy());
    fireEvent.click(screen.getByText("s3_objects"));
    await waitFor(() => expect(screen.getByText(/Query this table/)).toBeTruthy());

    fireEvent.click(screen.getByText(/Query this table/));
    expect(onSelectTable).toHaveBeenCalledWith("analytics", "s3_objects");
  });

  it("explains an empty catalog instead of showing a blank column", async () => {
    catalog({ listDatabases: { databases: [] } });
    renderUi(<CatalogBrowser onSelectTable={vi.fn()} />);
    fireEvent.click(screen.getByText(/Browse data catalog/));

    await waitFor(() => expect(screen.getByText(/once a Glue crawler has run/)).toBeTruthy());
  });

  it("surfaces a Glue error rather than an empty list", async () => {
    catalog({ listDatabases: { databases: [], error: "AccessDeniedException" } });
    renderUi(<CatalogBrowser onSelectTable={vi.fn()} />);
    fireEvent.click(screen.getByText(/Browse data catalog/));

    await waitFor(() => expect(screen.getByText("AccessDeniedException")).toBeTruthy());
  });

  it("clears the chosen table when the database changes", async () => {
    catalog({
      listDatabases: {
        databases: [
          { name: "analytics", description: "" },
          { name: "archive", description: "" },
        ],
      },
    });
    renderUi(<CatalogBrowser onSelectTable={vi.fn()} />);
    fireEvent.click(screen.getByText(/Browse data catalog/));
    await waitFor(() => expect(screen.getByText("analytics")).toBeTruthy());
    fireEvent.click(screen.getByText("analytics"));
    await waitFor(() => expect(screen.getByText("s3_objects")).toBeTruthy());
    fireEvent.click(screen.getByText("s3_objects"));
    await waitFor(() => expect(screen.getByText("key")).toBeTruthy());

    // Otherwise the schema of a table from the previous database stays on screen
    // next to the new database's table list.
    fireEvent.click(screen.getByText("archive"));
    await waitFor(() => expect(screen.getByText(/Choose a table/)).toBeTruthy());
  });
});
