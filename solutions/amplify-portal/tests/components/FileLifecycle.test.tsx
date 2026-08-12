import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ReactElement } from "react";

// fireEvent rather than user-event: these are text inputs and buttons, which
// fireEvent covers without adding a dev dependency.

const fileMutate = vi.fn();
vi.mock("../../src/lib/dispatch", () => ({
  fileMutate: (call: unknown) => fileMutate(call),
}));

import {
  FileRowActions,
  RestoreFromTrashButton,
  UploadLink,
  TRASH_PREFIX,
} from "../../src/components/FileLifecycle";
import { I18nProvider } from "../../src/i18n";
import { ToastProvider } from "../../src/lib/toast";

const renderUi = (ui: ReactElement) =>
  render(
    <I18nProvider>
      <ToastProvider>{ui}</ToastProvider>
    </I18nProvider>
  );

beforeEach(() => {
  fileMutate.mockReset();
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe("FileRowActions rename", () => {
  const props = {
    fileKey: "reports/q3.pdf",
    fileName: "q3.pdf",
    currentPrefix: "reports/",
  };

  const openRename = () => {
    renderUi(<FileRowActions {...props} onChanged={vi.fn()} />);
    fireEvent.click(screen.getByLabelText("Rename"));
    return screen.getByLabelText("Rename") as HTMLInputElement;
  };

  it("keeps the file in the current folder", async () => {
    fileMutate.mockResolvedValue({ success: true, newKey: "reports/q4.pdf" });
    const input = openRename();
    fireEvent.change(input, { target: { value: "q4.pdf" } });
    fireEvent.click(screen.getByText("Save"));

    await waitFor(() => expect(fileMutate).toHaveBeenCalledTimes(1));
    expect(fileMutate.mock.calls[0][0]).toEqual({
      action: "renameFile",
      // The destination is prefixed, so a rename does not move the file to the root.
      params: { sourceKey: "reports/q3.pdf", destinationKey: "reports/q4.pdf" },
    });
  });

  it("refuses a name containing a slash instead of moving the file", async () => {
    const input = openRename();
    fireEvent.change(input, { target: { value: "../elsewhere/q4.pdf" } });
    fireEvent.click(screen.getByText("Save"));

    await waitFor(() =>
      expect(screen.getByText(/cannot contain/i)).toBeTruthy()
    );
    expect(fileMutate).not.toHaveBeenCalled();
  });

  it("treats renaming to the same name as a no-op", async () => {
    const input = openRename();
    fireEvent.change(input, { target: { value: "q3.pdf" } });
    fireEvent.click(screen.getByText("Save"));

    expect(fileMutate).not.toHaveBeenCalled();
  });

  it("reports the backend error rather than claiming success", async () => {
    fileMutate.mockResolvedValue({ success: false, error: "AccessDenied" });
    const onChanged = vi.fn();
    renderUi(<FileRowActions {...props} onChanged={onChanged} />);
    fireEvent.click(screen.getByLabelText("Rename"));
    fireEvent.change(screen.getByLabelText("Rename"), { target: { value: "q4.pdf" } });
    fireEvent.click(screen.getByText("Save"));

    await waitFor(() => expect(screen.getByText("AccessDenied")).toBeTruthy());
    expect(onChanged).not.toHaveBeenCalled();
  });
});

describe("FileRowActions trash", () => {
  const props = {
    fileKey: "reports/q3.pdf",
    fileName: "q3.pdf",
    currentPrefix: "reports/",
  };

  it("asks nothing beforehand and offers to undo instead", async () => {
    const confirm = vi.spyOn(window, "confirm");
    fileMutate.mockResolvedValue({ success: true, trashKey: ".trash/reports/q3.pdf" });
    renderUi(<FileRowActions {...props} onChanged={vi.fn()} />);
    fireEvent.click(screen.getByLabelText("Move to trash"));

    // A dialog asks before the fact and asks every time. The undo answers after,
    // when a mistake is visible, and the object is still there to put back.
    await waitFor(() => expect(screen.getByText(/Moved q3.pdf to the trash/i)).toBeInTheDocument());
    expect(confirm).not.toHaveBeenCalled();
    expect(screen.getByRole("button", { name: "Undo" })).toBeInTheDocument();
  });

  it("reloads the listing after a successful move", async () => {
    fileMutate.mockResolvedValue({ success: true, trashKey: ".trash/reports/q3.pdf" });
    const onChanged = vi.fn();
    renderUi(<FileRowActions {...props} onChanged={onChanged} />);
    fireEvent.click(screen.getByLabelText("Move to trash"));

    await waitFor(() => expect(onChanged).toHaveBeenCalledTimes(1));
    expect(fileMutate.mock.calls[0][0]).toEqual({
      action: "trashFile",
      params: { key: "reports/q3.pdf" },
    });
  });

  it("puts the file back when the undo is taken", async () => {
    fileMutate.mockResolvedValue({ success: true, trashKey: ".trash/reports/q3.pdf" });
    const onChanged = vi.fn();
    renderUi(<FileRowActions {...props} onChanged={onChanged} />);
    fireEvent.click(screen.getByLabelText("Move to trash"));

    const undo = await waitFor(() => screen.getByRole("button", { name: "Undo" }));
    fireEvent.click(undo);

    await waitFor(() => expect(fileMutate).toHaveBeenCalledTimes(2));
    // The key the backend reported, not one recomputed at the call site: only the
    // response knows where the object actually landed.
    expect(fileMutate.mock.calls[1][0]).toEqual({
      action: "restoreFromTrash",
      params: { trashKey: ".trash/reports/q3.pdf" },
    });
    await waitFor(() => expect(screen.queryByRole("button", { name: "Undo" })).toBeNull());
  });

  it("offers no undo when the backend did not say where the file went", async () => {
    // Without a trash key there is nothing to restore, and an undo button that
    // cannot work is worse than none.
    fileMutate.mockResolvedValue({ success: true });
    renderUi(<FileRowActions {...props} onChanged={vi.fn()} />);
    fireEvent.click(screen.getByLabelText("Move to trash"));

    await waitFor(() => expect(screen.getByText(/Moved q3.pdf to the trash/i)).toBeInTheDocument());
    expect(screen.queryByRole("button", { name: "Undo" })).toBeNull();
  });

  it("reports a failed undo on the notice rather than losing it", async () => {
    fileMutate.mockResolvedValueOnce({ success: true, trashKey: ".trash/reports/q3.pdf" });
    fileMutate.mockResolvedValueOnce({ success: false, error: "AccessDenied" });
    renderUi(<FileRowActions {...props} onChanged={vi.fn()} />);
    fireEvent.click(screen.getByLabelText("Move to trash"));

    fireEvent.click(await waitFor(() => screen.getByRole("button", { name: "Undo" })));

    await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent("AccessDenied"));
    // The offer is withdrawn: retrying the same call would fail the same way.
    expect(screen.queryByRole("button", { name: "Undo" })).toBeNull();
  });
});

describe("RestoreFromTrashButton", () => {
  it("sends the trash key the backend expects", async () => {
    fileMutate.mockResolvedValue({ success: true, restoredKey: "reports/q3.pdf" });
    const onChanged = vi.fn();
    renderUi(
      <RestoreFromTrashButton trashKey={`${TRASH_PREFIX}reports/q3.pdf`} onChanged={onChanged} />
    );
    fireEvent.click(screen.getByLabelText("Restore"));

    await waitFor(() => expect(onChanged).toHaveBeenCalledTimes(1));
    expect(fileMutate.mock.calls[0][0]).toEqual({
      action: "restoreFromTrash",
      // The handler rejects anything not under this prefix, so the key is passed whole.
      params: { trashKey: ".trash/reports/q3.pdf" },
    });
  });

  it("surfaces a failed restore", async () => {
    fileMutate.mockResolvedValue({ success: false, error: "Invalid trash key" });
    const onChanged = vi.fn();
    renderUi(<RestoreFromTrashButton trashKey=".trash/x" onChanged={onChanged} />);
    fireEvent.click(screen.getByLabelText("Restore"));

    await waitFor(() => expect(screen.getByText("Invalid trash key")).toBeTruthy());
    expect(onChanged).not.toHaveBeenCalled();
  });
});

describe("UploadLink", () => {
  const open = () => {
    renderUi(<UploadLink destinationPrefix="inbox/" />);
    fireEvent.click(screen.getByText(/Upload link/));
  };

  it("sends the expiry as a number, which the handler clamps arithmetically", async () => {
    fileMutate.mockResolvedValue({
      uploadUrl: "https://example.invalid/put",
      destinationKey: "inbox/a.txt",
    });
    open();
    fireEvent.change(screen.getByLabelText("File name"), { target: { value: "a.txt" } });
    fireEvent.click(screen.getByText("Create link"));

    await waitFor(() => expect(fileMutate).toHaveBeenCalledTimes(1));
    const params = fileMutate.mock.calls[0][0].params;
    expect(params.destinationPrefix).toBe("inbox/");
    expect(params.fileName).toBe("a.txt");
    // A string here would raise a TypeError inside min() in the handler.
    expect(typeof params.expiresIn).toBe("number");
    expect(params.expiresIn).toBe(3600);
  });

  it("uses the chosen expiry", async () => {
    fileMutate.mockResolvedValue({ uploadUrl: "https://example.invalid/put" });
    open();
    fireEvent.click(screen.getByText("24 hours"));
    fireEvent.click(screen.getByText("Create link"));

    await waitFor(() => expect(fileMutate).toHaveBeenCalledTimes(1));
    expect(fileMutate.mock.calls[0][0].params.expiresIn).toBe(86400);
  });

  it("states the destination and the warning alongside the link", async () => {
    fileMutate.mockResolvedValue({
      uploadUrl: "https://example.invalid/put",
      destinationKey: "inbox/generated",
    });
    open();
    fireEvent.click(screen.getByText("Create link"));

    await waitFor(() => expect(screen.getByText("inbox/generated")).toBeTruthy());
    // The URL is a bearer credential; saying so is the point of showing it here.
    expect(screen.getByText(/the credential/i)).toBeTruthy();
  });

  it("reports a failure instead of showing an empty link box", async () => {
    fileMutate.mockResolvedValue({ uploadUrl: "", error: "NoSuchBucket" });
    open();
    fireEvent.click(screen.getByText("Create link"));

    await waitFor(() => expect(screen.getByText("NoSuchBucket")).toBeTruthy());
    expect(screen.queryByText(/the credential/i)).toBeNull();
  });
});
