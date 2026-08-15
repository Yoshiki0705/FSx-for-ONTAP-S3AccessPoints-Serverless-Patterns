import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClientProvider } from "@tanstack/react-query";

const fileQuery = vi.fn();
const fileMutate = vi.fn();
vi.mock("../../src/lib/dispatch", () => ({
  fileQuery: (call: unknown) => fileQuery(call),
  fileMutate: (call: unknown) => fileMutate(call),
}));

// The row and header controls each reach AWS on their own. Stubbed so this file
// tests the explorer's own behaviour — ordering, filtering, selection — rather
// than re-testing components that have their own suites.
vi.mock("../../src/components/FilePreview", () => ({ FilePreview: () => null }));
vi.mock("../../src/components/ShareLink", () => ({ ShareLink: () => null }));
vi.mock("../../src/components/Favorites", () => ({ FavoriteButton: () => null }));
vi.mock("../../src/components/FolderDownload", () => ({ FolderDownload: () => null }));
vi.mock("../../src/components/RestoreFromSnapshot", () => ({ RestoreFromSnapshot: () => null }));
vi.mock("../../src/components/SnapshotCompare", () => ({ SnapshotCompare: () => null }));
vi.mock("../../src/components/FileTags", () => ({
  FileTagsBadges: () => null,
  FileTagsEditor: () => null,
}));
vi.mock("../../src/components/AiMetadataBadges", () => ({
  AiMetadataBadges: () => null,
  useAiMetadata: () => ({ data: new Map() }),
}));

import { FileExplorer } from "../../src/components/FileExplorer";
import { I18nProvider } from "../../src/i18n";
import { createPortalQueryClient } from "../../src/lib/queryClient";
import { ToastProvider } from "../../src/lib/toast";

interface Row {
  key: string;
  size: number | null;
  lastModified: string | null;
  storageClass: string | null;
}

const file = (key: string, size: number, lastModified: string): Row => ({
  key,
  size,
  lastModified,
  storageClass: "STANDARD",
});

const folder = (key: string): Row => ({
  key,
  size: null,
  lastModified: null,
  storageClass: "DIRECTORY",
});

/** Rows the listing returns, by the prefix asked for. */
let listing: Record<string, Row[]>;
/** Whether the listing claims a further page. */
let truncated: boolean;

function renderExplorer(props: Partial<Parameters<typeof FileExplorer>[0]> = {}) {
  return render(
    <QueryClientProvider client={createPortalQueryClient()}>
      <I18nProvider>
        <ToastProvider>
          <FileExplorer onSelectPrefix={vi.fn()} {...props} />
        </ToastProvider>
      </I18nProvider>
    </QueryClientProvider>
  );
}

/** The row names as displayed, in order. */
const rowNames = (container: HTMLElement): string[] =>
  [...container.querySelectorAll(".file-item .name")].map((n) => n.textContent ?? "");

beforeEach(() => {
  fileQuery.mockReset();
  fileMutate.mockReset();
  truncated = false;
  listing = {
    "": [
      file("beta.txt", 500, "2026-08-10T09:00:00Z"),
      file("alpha.txt", 30_000, "2026-01-02T09:00:00Z"),
      file("part10.txt", 100, "2026-08-11T09:00:00Z"),
      file("part2.txt", 7_000, "2026-05-05T09:00:00Z"),
      folder("reports/"),
    ],
    "reports/": [file("reports/q3.pdf", 12, "2026-08-01T09:00:00Z")],
  };
  fileQuery.mockImplementation((call: { params?: { prefix?: string } }) => {
    const prefix = call.params?.prefix ?? "";
    return Promise.resolve({
      files: listing[prefix] ?? [],
      isTruncated: truncated,
      nextContinuationToken: truncated ? "next" : undefined,
    });
  });
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe("ordering", () => {
  it("lists by name ascending, with numbers in numeric order", async () => {
    const { container } = renderExplorer();
    // part2 before part10: the listing arrives in the Access Point's lexicographic
    // order, where "part10" precedes "part2".
    await waitFor(() =>
      expect(rowNames(container)).toEqual([
        "reports",
        "alpha.txt",
        "beta.txt",
        "part2.txt",
        "part10.txt",
      ])
    );
  });

  it("orders by size, and reverses when the column is chosen again", async () => {
    const { container } = renderExplorer();
    await waitFor(() => expect(rowNames(container)).toHaveLength(5));

    fireEvent.click(screen.getByRole("button", { name: /^Size/ }));
    expect(rowNames(container)).toEqual([
      "reports",
      "part10.txt",
      "beta.txt",
      "part2.txt",
      "alpha.txt",
    ]);

    fireEvent.click(screen.getByRole("button", { name: /^Size/ }));
    expect(rowNames(container)).toEqual([
      "reports",
      "alpha.txt",
      "part2.txt",
      "beta.txt",
      "part10.txt",
    ]);
  });

  it("keeps folders above files whichever column orders the listing", async () => {
    const { container } = renderExplorer();
    await waitFor(() => expect(rowNames(container)).toHaveLength(5));
    fireEvent.click(screen.getByRole("button", { name: /^Modified/ }));
    expect(rowNames(container)[0]).toBe("reports");
  });

  it("says which rows an ordering applied to only while pages remain", async () => {
    truncated = true;
    const { container } = renderExplorer();
    await waitFor(() => expect(rowNames(container)).toHaveLength(5));

    // The default order is the listing's own, so it makes no claim to qualify.
    expect(container.querySelector(".file-scope-note")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: /^Size/ }));
    expect(container.querySelector(".file-scope-note")?.textContent).toContain("5");
  });

  it("makes no such claim when the whole folder is loaded", async () => {
    const { container } = renderExplorer();
    await waitFor(() => expect(rowNames(container)).toHaveLength(5));
    fireEvent.click(screen.getByRole("button", { name: /^Size/ }));
    expect(container.querySelector(".file-scope-note")).toBeNull();
  });
});

describe("filtering", () => {
  const filterFor = (text: string) => {
    fireEvent.change(screen.getByLabelText(/Filter this folder by name/i), {
      target: { value: text },
    });
  };

  it("narrows the listing to matching names, ignoring case", async () => {
    const { container } = renderExplorer();
    await waitFor(() => expect(rowNames(container)).toHaveLength(5));
    filterFor("PART");
    expect(rowNames(container)).toEqual(["part2.txt", "part10.txt"]);
  });

  it("matches folders too", async () => {
    const { container } = renderExplorer();
    await waitFor(() => expect(rowNames(container)).toHaveLength(5));
    filterFor("repo");
    expect(rowNames(container)).toEqual(["reports"]);
  });

  it("distinguishes an empty folder from one the filter emptied", async () => {
    const { container } = renderExplorer();
    await waitFor(() => expect(rowNames(container)).toHaveLength(5));
    filterFor("nothing matches this");
    expect(rowNames(container)).toEqual([]);
    // Reporting "no files in this directory" here would name the wrong cause.
    expect(screen.getByText(/No files match/i)).toBeInTheDocument();
    expect(screen.queryByText(/No files in this directory/i)).toBeNull();
  });
});

describe("selection", () => {
  const selectRow = (name: string) =>
    fireEvent.click(screen.getByLabelText(`Select ${name}`));

  it("offers no checkbox for a folder", async () => {
    renderExplorer();
    await waitFor(() => expect(screen.getByText("alpha.txt")).toBeInTheDocument());
    // trashFile copies and deletes a single object, so a prefix sent to it would
    // leave the folder's contents behind.
    expect(screen.queryByLabelText("Select reports")).toBeNull();
  });

  it("says why select-all is unavailable in a folder-only listing", async () => {
    // Reported from an iPhone: the header box "did nothing" when tapped. It was
    // already disabled, but a disabled checkbox looked identical to an enabled one
    // and carried no reason for it.
    listing[""] = [folder("reports/"), folder("archive/")];
    renderExplorer();
    const selectAll = await waitFor(
      () => screen.getByLabelText("Select all listed files") as HTMLInputElement,
    );
    expect(selectAll.disabled).toBe(true);
    expect(selectAll.title).toMatch(/No selectable files/i);
  });

  it("leaves select-all usable, and unexplained, when files are present", async () => {
    renderExplorer();
    await waitFor(() => expect(screen.getByText("alpha.txt")).toBeInTheDocument());
    const selectAll = screen.getByLabelText("Select all listed files") as HTMLInputElement;
    expect(selectAll.disabled).toBe(false);
    expect(selectAll.title).not.toMatch(/No selectable files/i);
  });

  it("counts the selection and clears it on request", async () => {
    renderExplorer();
    await waitFor(() => expect(screen.getByText("alpha.txt")).toBeInTheDocument());

    selectRow("alpha.txt");
    selectRow("beta.txt");
    expect(screen.getByText("2 selected")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /Clear selection/i }));
    expect(screen.queryByText(/selected/)).toBeNull();
  });

  it("selects the run between the anchor and a shift-click", async () => {
    const { container } = renderExplorer();
    await waitFor(() => expect(rowNames(container)).toHaveLength(5));

    selectRow("alpha.txt");
    fireEvent.click(screen.getByLabelText("Select part2.txt"), { shiftKey: true });
    // alpha, beta, part2 — the run as displayed, not an interval of keys.
    expect(screen.getByText("3 selected")).toBeInTheDocument();
  });

  it("selects every listed file at once", async () => {
    const { container } = renderExplorer();
    await waitFor(() => expect(rowNames(container)).toHaveLength(5));
    fireEvent.click(screen.getByLabelText(/Select all listed files/i));
    // Four files; the folder is not selectable.
    expect(screen.getByText("4 selected")).toBeInTheDocument();
  });

  it("selects only what the filter leaves visible", async () => {
    const { container } = renderExplorer();
    await waitFor(() => expect(rowNames(container)).toHaveLength(5));
    fireEvent.change(screen.getByLabelText(/Filter this folder by name/i), {
      target: { value: "part" },
    });
    fireEvent.click(screen.getByLabelText(/Select all listed files/i));
    expect(screen.getByText("2 selected")).toBeInTheDocument();
  });

  it("drops a selection made in another folder", async () => {
    const { container } = renderExplorer();
    await waitFor(() => expect(rowNames(container)).toHaveLength(5));
    selectRow("alpha.txt");
    expect(screen.getByText("1 selected")).toBeInTheDocument();

    fireEvent.click(screen.getByText("reports"));

    // The selection must not survive the move: acting on it here would trash a
    // file the user can no longer see.
    await waitFor(() => expect(rowNames(container)).toEqual(["..", "q3.pdf"]));
    expect(screen.queryByText(/selected/)).toBeNull();
  });
});

describe("bulk operations", () => {
  it("trashes each selected file and reloads the listing", async () => {
    vi.spyOn(window, "confirm").mockReturnValue(true);
    fileMutate.mockResolvedValue({ success: true });
    const { container } = renderExplorer();
    await waitFor(() => expect(rowNames(container)).toHaveLength(5));

    fireEvent.click(screen.getByLabelText("Select alpha.txt"));
    fireEvent.click(screen.getByLabelText("Select beta.txt"));
    fireEvent.click(screen.getByRole("button", { name: /selected files to trash/i }));

    await waitFor(() => expect(fileMutate).toHaveBeenCalledTimes(2));
    expect(fileMutate.mock.calls.map((c) => c[0])).toEqual([
      { action: "trashFile", params: { key: "alpha.txt" } },
      { action: "trashFile", params: { key: "beta.txt" } },
    ]);
    await waitFor(() => expect(screen.queryByText(/selected/)).toBeNull());
  });

  it("does nothing when the confirmation is declined", async () => {
    vi.spyOn(window, "confirm").mockReturnValue(false);
    const { container } = renderExplorer();
    await waitFor(() => expect(rowNames(container)).toHaveLength(5));

    fireEvent.click(screen.getByLabelText("Select alpha.txt"));
    fireEvent.click(screen.getByRole("button", { name: /selected files to trash/i }));

    expect(fileMutate).not.toHaveBeenCalled();
    expect(screen.getByText("1 selected")).toBeInTheDocument();
  });

  it("names the files that failed rather than only counting them", async () => {
    vi.spyOn(window, "confirm").mockReturnValue(true);
    fileMutate.mockImplementation((call: { params: { key: string } }) =>
      Promise.resolve(
        call.params.key === "beta.txt"
          ? { success: false, error: "AccessDenied" }
          : { success: true }
      )
    );
    const { container } = renderExplorer();
    await waitFor(() => expect(rowNames(container)).toHaveLength(5));

    fireEvent.click(screen.getByLabelText(/Select all listed files/i));
    fireEvent.click(screen.getByRole("button", { name: /selected files to trash/i }));

    // "1 of 4 failed" does not say which one to retry; the name does. Scoped to
    // the report, since the row for that file is still in the listing behind it.
    await waitFor(() => expect(screen.getByText(/1 of 4 failed/i)).toBeInTheDocument());
    const report = container.querySelector(".file-bulk-failures") as HTMLElement;
    expect(report.textContent).toContain("beta.txt");
    expect(report.textContent).toContain("AccessDenied");
    // And only that one: the three that succeeded must not be listed.
    expect(report.querySelectorAll("li")).toHaveLength(1);
  });

  it("offers to put the whole run back", async () => {
    vi.spyOn(window, "confirm").mockReturnValue(true);
    fileMutate.mockImplementation((call: { params: { key: string } }) =>
      Promise.resolve({ success: true, trashKey: `.trash/${call.params.key}` })
    );
    const { container } = renderExplorer();
    await waitFor(() => expect(rowNames(container)).toHaveLength(5));

    fireEvent.click(screen.getByLabelText("Select alpha.txt"));
    fireEvent.click(screen.getByLabelText("Select beta.txt"));
    fireEvent.click(screen.getByRole("button", { name: /selected files to trash/i }));

    await waitFor(() => expect(screen.getByText(/Moved 2 files to the trash/i)).toBeInTheDocument());
    fileMutate.mockClear();
    fireEvent.click(screen.getByRole("button", { name: "Undo" }));

    await waitFor(() => expect(fileMutate).toHaveBeenCalledTimes(2));
    expect(fileMutate.mock.calls.map((c) => c[0])).toEqual([
      { action: "restoreFromTrash", params: { trashKey: ".trash/alpha.txt" } },
      { action: "restoreFromTrash", params: { trashKey: ".trash/beta.txt" } },
    ]);
  });

  it("offers to put back only what actually moved", async () => {
    vi.spyOn(window, "confirm").mockReturnValue(true);
    fileMutate.mockImplementation((call: { params: { key: string } }) =>
      Promise.resolve(
        call.params.key === "beta.txt"
          ? { success: false, error: "AccessDenied" }
          : { success: true, trashKey: `.trash/${call.params.key}` }
      )
    );
    const { container } = renderExplorer();
    await waitFor(() => expect(rowNames(container)).toHaveLength(5));

    fireEvent.click(screen.getByLabelText("Select alpha.txt"));
    fireEvent.click(screen.getByLabelText("Select beta.txt"));
    fireEvent.click(screen.getByRole("button", { name: /selected files to trash/i }));

    // One of the two moved, so the notice and the undo speak for that one. Undoing
    // what was asked for rather than what happened would try to restore an object
    // that never left.
    await waitFor(() => expect(screen.getByText(/Moved 1 files? to the trash/i)).toBeInTheDocument());
    fileMutate.mockClear();
    fireEvent.click(screen.getByRole("button", { name: "Undo" }));

    await waitFor(() => expect(fileMutate).toHaveBeenCalledTimes(1));
    expect(fileMutate.mock.calls[0][0]).toEqual({
      action: "restoreFromTrash",
      params: { trashKey: ".trash/alpha.txt" },
    });
  });

  it("offers no notice when nothing moved", async () => {
    vi.spyOn(window, "confirm").mockReturnValue(true);
    fileMutate.mockResolvedValue({ success: false, error: "AccessDenied" });
    const { container } = renderExplorer();
    await waitFor(() => expect(rowNames(container)).toHaveLength(5));

    fireEvent.click(screen.getByLabelText("Select alpha.txt"));
    fireEvent.click(screen.getByRole("button", { name: /selected files to trash/i }));

    await waitFor(() => expect(screen.getByText(/1 of 1 failed/i)).toBeInTheDocument());
    expect(screen.queryByRole("button", { name: "Undo" })).toBeNull();
  });

  it("restores instead of trashing while inside the trash", async () => {
    vi.spyOn(window, "confirm").mockReturnValue(true);
    fileMutate.mockResolvedValue({ success: true });
    listing[".trash/"] = [file(".trash/gone.txt", 5, "2026-08-01T09:00:00Z")];

    const { container } = renderExplorer({ initialPrefix: ".trash/" });
    await waitFor(() => expect(rowNames(container)).toEqual(["..", "gone.txt"]));

    fireEvent.click(screen.getByLabelText("Select gone.txt"));
    fireEvent.click(screen.getByRole("button", { name: /Restore the 1 selected/i }));

    await waitFor(() => expect(fileMutate).toHaveBeenCalledTimes(1));
    expect(fileMutate.mock.calls[0][0]).toEqual({
      action: "restoreFromTrash",
      params: { trashKey: ".trash/gone.txt" },
    });
  });
});

describe("row overflow menu", () => {
  const openMenuFor = async (name: string) => {
    await waitFor(() => expect(screen.getByText(name)).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: new RegExp(`More actions for ${name}`) }));
  };

  it("keeps the secondary controls out of the row until asked", async () => {
    renderExplorer();
    await waitFor(() => expect(screen.getByText("alpha.txt")).toBeInTheDocument());

    // Seven controls on every line are read before the filename is. Rename and
    // trash are behind the overflow button; selecting and previewing are not.
    expect(screen.queryByLabelText("Rename")).toBeNull();
    expect(screen.queryByLabelText("Move to trash")).toBeNull();
    expect(screen.getByLabelText("Select alpha.txt")).toBeInTheDocument();

    await openMenuFor("alpha.txt");
    expect(screen.getByLabelText("Rename")).toBeInTheDocument();
    expect(screen.getByLabelText("Move to trash")).toBeInTheDocument();
  });

  it("still reaches the action through the menu", async () => {
    fileMutate.mockResolvedValue({ success: true, trashKey: ".trash/alpha.txt" });
    const { container } = renderExplorer();
    await waitFor(() => expect(rowNames(container)).toHaveLength(5));

    await openMenuFor("alpha.txt");
    fireEvent.click(screen.getByLabelText("Move to trash"));

    await waitFor(() => expect(fileMutate).toHaveBeenCalledTimes(1));
    expect(fileMutate.mock.calls[0][0]).toEqual({
      action: "trashFile",
      params: { key: "alpha.txt" },
    });
  });

  it("offers restore instead of trash while inside the trash", async () => {
    listing[".trash/"] = [file(".trash/gone.txt", 5, "2026-08-01T09:00:00Z")];
    renderExplorer({ initialPrefix: ".trash/" });

    await openMenuFor("gone.txt");
    expect(screen.getByLabelText("Restore")).toBeInTheDocument();
    expect(screen.queryByLabelText("Move to trash")).toBeNull();
  });

  it("closes on Escape and hands focus back to its button", async () => {
    renderExplorer();
    await openMenuFor("alpha.txt");

    fireEvent.keyDown(document, { key: "Escape" });

    await waitFor(() => expect(screen.queryByLabelText("Rename")).toBeNull());
    // Focus left inside a removed subtree drops the caret to the top of the page.
    expect(screen.getByRole("button", { name: /More actions for alpha\.txt/ })).toHaveFocus();
  });

  it("closes when a pointer goes down outside it", async () => {
    const { container } = renderExplorer();
    await openMenuFor("alpha.txt");

    // Pointerdown, not click: a click that closes the menu would also land on
    // whatever is beneath, activating a control the user only wanted to see.
    fireEvent.pointerDown(container);

    await waitFor(() => expect(screen.queryByLabelText("Rename")).toBeNull());
  });

  it("names each button by its row", async () => {
    const { container } = renderExplorer();
    await waitFor(() => expect(rowNames(container)).toHaveLength(5));

    // Four identical "More actions" buttons would be indistinguishable read aloud.
    const triggers = screen.getAllByRole("button", { name: /More actions for/ });
    const names = triggers.map((b) => b.getAttribute("aria-label"));
    expect(new Set(names).size).toBe(triggers.length);
  });
});

describe("create folder", () => {
  it("creates it inside the folder on screen", async () => {
    fileMutate.mockResolvedValue({ success: true, key: "reports/2026/" });
    renderExplorer({ initialPrefix: "reports/" });
    await waitFor(() => expect(screen.getByText("q3.pdf")).toBeInTheDocument());

    fireEvent.click(screen.getByRole("button", { name: /New folder/i }));
    fireEvent.change(screen.getByLabelText("Folder name"), { target: { value: "2026" } });
    fireEvent.click(screen.getByRole("button", { name: "Create" }));

    await waitFor(() => expect(fileMutate).toHaveBeenCalledTimes(1));
    // Relative to where the user is, not the root.
    expect(fileMutate.mock.calls[0][0]).toEqual({
      action: "createFolder",
      params: { key: "reports/2026" },
    });
  });

  it("is not offered inside the trash", async () => {
    listing[".trash/"] = [file(".trash/gone.txt", 5, "2026-08-01T09:00:00Z")];
    const { container } = renderExplorer({ initialPrefix: ".trash/" });
    await waitFor(() => expect(rowNames(container)).toEqual(["..", "gone.txt"]));

    expect(screen.queryByRole("button", { name: /New folder/i })).toBeNull();
  });
});

describe("copy and move", () => {
  const openCopyMove = async (name: string) => {
    await waitFor(() => expect(screen.getByText(name)).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: new RegExp(`More actions for ${name}`) }));
    fireEvent.click(screen.getByLabelText(/Copy or move/i));
  };

  it("shows the key the file would land on", async () => {
    renderExplorer();
    await openCopyMove("alpha.txt");

    fireEvent.change(screen.getByLabelText("Destination folder"), { target: { value: "archive/2026" } });

    // A destination box on its own leaves the reader guessing whether the filename
    // is appended.
    expect(screen.getByText("archive/2026/alpha.txt")).toBeInTheDocument();
  });

  it("copies without touching the original", async () => {
    fileMutate.mockResolvedValue({ success: true, newKey: "archive/alpha.txt" });
    renderExplorer();
    await openCopyMove("alpha.txt");

    fireEvent.change(screen.getByLabelText("Destination folder"), { target: { value: "archive/" } });
    fireEvent.click(screen.getByRole("button", { name: "Copy" }));

    await waitFor(() => expect(fileMutate).toHaveBeenCalledTimes(1));
    expect(fileMutate.mock.calls[0][0]).toEqual({
      action: "copyFile",
      params: { sourceKey: "alpha.txt", destinationKey: "archive/alpha.txt" },
    });
  });

  it("offers to undo a move by moving it back", async () => {
    fileMutate.mockResolvedValue({ success: true, newKey: "archive/alpha.txt" });
    renderExplorer();
    await openCopyMove("alpha.txt");

    fireEvent.change(screen.getByLabelText("Destination folder"), { target: { value: "archive/" } });
    fireEvent.click(screen.getByRole("button", { name: "Move" }));

    const undo = await waitFor(() => screen.getByRole("button", { name: "Undo" }));
    fileMutate.mockClear();
    fireEvent.click(undo);

    await waitFor(() => expect(fileMutate).toHaveBeenCalledTimes(1));
    expect(fileMutate.mock.calls[0][0]).toEqual({
      action: "moveFile",
      params: { sourceKey: "archive/alpha.txt", destinationKey: "alpha.txt" },
    });
  });

  it("offers no undo for a copy", async () => {
    // Undoing a copy means deleting the new file, which is a destruction rather
    // than a reversal. The copy is visible and can be trashed.
    fileMutate.mockResolvedValue({ success: true, newKey: "archive/alpha.txt" });
    renderExplorer();
    await openCopyMove("alpha.txt");

    fireEvent.change(screen.getByLabelText("Destination folder"), { target: { value: "archive/" } });
    fireEvent.click(screen.getByRole("button", { name: "Copy" }));

    await waitFor(() => expect(screen.getByText(/Copied alpha\.txt/)).toBeInTheDocument());
    expect(screen.queryByRole("button", { name: "Undo" })).toBeNull();
  });

  it("does not overwrite until told to, and then says so plainly", async () => {
    fileMutate.mockResolvedValueOnce({
      success: false,
      error: "archive/alpha.txt already exists. Pass overwrite to replace it",
    });
    renderExplorer();
    await openCopyMove("alpha.txt");

    fireEvent.change(screen.getByLabelText("Destination folder"), { target: { value: "archive/" } });
    fireEvent.click(screen.getByRole("button", { name: "Move" }));

    // The offer to replace appears after the refusal: that is when the person knows
    // there is something there to replace.
    const replace = await waitFor(() => screen.getByRole("button", { name: /Replace what is there/i }));
    fileMutate.mockResolvedValue({ success: true, newKey: "archive/alpha.txt" });
    fireEvent.click(replace);

    await waitFor(() => expect(fileMutate).toHaveBeenCalledTimes(2));
    expect(fileMutate.mock.calls[1][0]).toEqual({
      action: "moveFile",
      params: { sourceKey: "alpha.txt", destinationKey: "archive/alpha.txt", overwrite: true },
    });
  });

  it("is not offered inside the trash", async () => {
    listing[".trash/"] = [file(".trash/gone.txt", 5, "2026-08-01T09:00:00Z")];
    renderExplorer({ initialPrefix: ".trash/" });
    await waitFor(() => expect(screen.getByText("gone.txt")).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: /More actions for gone\.txt/ }));

    expect(screen.queryByLabelText(/Copy or move/i)).toBeNull();
  });
});

describe("permanent deletion", () => {
  const openTrashMenu = async () => {
    listing[".trash/"] = [file(".trash/gone.txt", 5, "2026-08-01T09:00:00Z")];
    renderExplorer({ initialPrefix: ".trash/" });
    await waitFor(() => expect(screen.getByText("gone.txt")).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: /More actions for gone\.txt/ }));
  };

  it("is offered only inside the trash", async () => {
    renderExplorer();
    await waitFor(() => expect(screen.getByText("alpha.txt")).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: /More actions for alpha\.txt/ }));

    // A file has to be trashed first, which the backend also enforces.
    expect(screen.queryByLabelText(/Delete permanently/i)).toBeNull();
  });

  it("names the consequence and sends the acknowledgement", async () => {
    const confirm = vi.spyOn(window, "confirm").mockReturnValue(true);
    fileMutate.mockResolvedValue({ success: true });
    await openTrashMenu();

    fireEvent.click(screen.getByLabelText(/Delete permanently/i));

    expect(confirm.mock.calls[0][0]).toContain("not versioned");
    await waitFor(() => expect(fileMutate).toHaveBeenCalledTimes(1));
    expect(fileMutate.mock.calls[0][0]).toEqual({
      action: "deleteFileForever",
      params: { key: ".trash/gone.txt", acknowledgeIrreversible: true },
    });
  });

  it("does nothing when the confirmation is declined", async () => {
    vi.spyOn(window, "confirm").mockReturnValue(false);
    await openTrashMenu();

    fireEvent.click(screen.getByLabelText(/Delete permanently/i));

    expect(fileMutate).not.toHaveBeenCalled();
  });

  it("offers no undo, because there is none", async () => {
    vi.spyOn(window, "confirm").mockReturnValue(true);
    fileMutate.mockResolvedValue({ success: true });
    await openTrashMenu();

    fireEvent.click(screen.getByLabelText(/Delete permanently/i));

    await waitFor(() => expect(screen.getByText(/Deleted gone\.txt permanently/)).toBeInTheDocument());
    expect(screen.queryByRole("button", { name: "Undo" })).toBeNull();
  });
});

describe("addressing", () => {
  it("reports the folder it moved to, so the shell can put it in the URL", async () => {
    const onNavigate = vi.fn();
    renderExplorer({ onNavigate });
    await waitFor(() => expect(screen.getByText("reports")).toBeInTheDocument());

    fireEvent.click(screen.getByText("reports"));
    expect(onNavigate).toHaveBeenCalledWith("reports/");

    await waitFor(() => expect(screen.getByText("q3.pdf")).toBeInTheDocument());
    fireEvent.click(screen.getByLabelText(/Go to parent folder/i));
    expect(onNavigate).toHaveBeenLastCalledWith("");
  });

  it("opens the folder the caller addressed on mount", async () => {
    const { container } = renderExplorer({ initialPrefix: "reports/" });
    await waitFor(() => expect(rowNames(container)).toEqual(["..", "q3.pdf"]));
  });
});

describe("keyboard access", () => {
  it("puts the control on the name, not on the row", async () => {
    renderExplorer();
    await waitFor(() => expect(screen.getByText("reports")).toBeInTheDocument());

    // A row that was itself a button nested the favourite star inside another
    // control, and the star's label became part of the row's accessible name
    // ("Add to favourites 📁 reports - -"). The name is the button instead.
    const name = screen.getByRole("button", { name: "reports" });
    expect(name).toHaveClass("file-name-btn");

    const row = name.closest(".file-item") as HTMLElement;
    expect(row).not.toHaveAttribute("role");
    expect(row).not.toHaveAttribute("tabindex");
  });

  it("opens a folder from the keyboard", async () => {
    const onNavigate = vi.fn();
    renderExplorer({ onNavigate });
    await waitFor(() => expect(screen.getByText("reports")).toBeInTheDocument());

    // A button is reached by Tab and activated by Enter or Space without a key
    // handler of its own, which is why there is none to test separately.
    fireEvent.click(screen.getByRole("button", { name: "reports" }));
    expect(onNavigate).toHaveBeenCalledWith("reports/");
    // Once, not twice: the name stops the click before the row handler repeats it.
    expect(onNavigate).toHaveBeenCalledTimes(1);
  });

  it("names the parent-folder control by what it does", async () => {
    const onNavigate = vi.fn();
    renderExplorer({ onNavigate, initialPrefix: "reports/" });
    // ".." tells a screen reader nothing on its own.
    const up = await waitFor(() => screen.getByRole("button", { name: /Go to parent folder/i }));
    fireEvent.click(up);
    expect(onNavigate).toHaveBeenCalledWith("");
  });
});
