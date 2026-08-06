import { describe, it, expect, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import type { ReactElement } from "react";

// fireEvent rather than user-event: the interactions here are a controlled text
// input, a checkbox and two buttons, all of which fireEvent covers, so the suite
// does not need another dev dependency to express them.

import { SnaplockConfirmDialog } from "../../src/components/SnaplockConfirmDialog";
import { I18nProvider } from "../../src/i18n";
import type { SnaplockIntent } from "../../src/utils/snaplockConsequences";

/** Fixed clock so the rendered date is a literal. */
const NOW = new Date("2026-08-06T00:00:00.000Z");

const renderDialog = (ui: ReactElement) => render(<I18nProvider>{ui}</I18nProvider>);

const createVolume: SnaplockIntent = {
  kind: "createSnaplockVolume",
  volumeName: "worm_vol",
  snaplockType: "enterprise",
  retentionDefault: "P30D",
  retentionMax: "P1Y",
};

const lockSnapshot: SnaplockIntent = {
  kind: "lockSnapshot",
  snapshotName: "snap1",
  retentionDays: 7,
};

describe("SnaplockConfirmDialog", () => {
  it("names the resource being changed", () => {
    renderDialog(
      <SnaplockConfirmDialog
        intent={createVolume}
        onConfirm={vi.fn()}
        onCancel={vi.fn()}
        now={NOW}
      />
    );
    expect(screen.getByText(/worm_vol/)).toBeInTheDocument();
  });

  it("shows an absolute date rather than only a duration", () => {
    // A duration ("P1Y") cannot be checked against the console; a date can.
    renderDialog(
      <SnaplockConfirmDialog
        intent={createVolume}
        onConfirm={vi.fn()}
        onCancel={vi.fn()}
        now={NOW}
      />
    );
    // The headline carries the date and the consequence list repeats it, so the
    // assertion targets the headline instead of expecting a single match.
    const headline = document.querySelector(".slc-until");
    expect(headline).not.toBeNull();
    // A year is enough: the exact wording is locale-dependent, but a formatted
    // absolute date is the point, and "P1Y" alone would not contain it.
    expect(headline?.textContent).toMatch(/2027/);
  });

  it("keeps the confirm button disabled until the keyword is typed", () => {
    const onConfirm = vi.fn();
    renderDialog(
      <SnaplockConfirmDialog
        intent={createVolume}
        onConfirm={onConfirm}
        onCancel={vi.fn()}
        now={NOW}
      />
    );

    const proceed = screen.getByRole("button", { name: /apply/i });
    expect(proceed).toBeDisabled();

    fireEvent.change(screen.getByRole("textbox"), { target: { value: "LOCK" } });
    expect(proceed).toBeEnabled();

    fireEvent.click(proceed);
    expect(onConfirm).toHaveBeenCalledOnce();
  });

  it("does not accept a near-miss keyword", () => {
    renderDialog(
      <SnaplockConfirmDialog
        intent={createVolume}
        onConfirm={vi.fn()}
        onCancel={vi.fn()}
        now={NOW}
      />
    );

    // Lower case is the obvious near miss, and accepting it would make the
    // typed word a formality rather than a deliberate act.
    fireEvent.change(screen.getByRole("textbox"), { target: { value: "lock" } });
    expect(screen.getByRole("button", { name: /apply/i })).toBeDisabled();
  });

  it("asks for a checkbox rather than a keyword on a snapshot lock", () => {
    const onConfirm = vi.fn();
    renderDialog(
      <SnaplockConfirmDialog
        intent={lockSnapshot}
        onConfirm={onConfirm}
        onCancel={vi.fn()}
        now={NOW}
      />
    );

    expect(screen.queryByRole("textbox")).toBeNull();
    const proceed = screen.getByRole("button", { name: /apply/i });
    expect(proceed).toBeDisabled();

    fireEvent.click(screen.getByRole("checkbox"));
    expect(proceed).toBeEnabled();
    fireEvent.click(proceed);
    expect(onConfirm).toHaveBeenCalledOnce();
  });

  it("cancels without confirming", () => {
    const onConfirm = vi.fn();
    const onCancel = vi.fn();
    renderDialog(
      <SnaplockConfirmDialog
        intent={createVolume}
        onConfirm={onConfirm}
        onCancel={onCancel}
        now={NOW}
      />
    );

    fireEvent.click(screen.getByRole("button", { name: /cancel/i }));
    expect(onCancel).toHaveBeenCalledOnce();
    expect(onConfirm).not.toHaveBeenCalled();
  });

  it("is a labelled modal dialog", () => {
    renderDialog(
      <SnaplockConfirmDialog
        intent={createVolume}
        onConfirm={vi.fn()}
        onCancel={vi.fn()}
        now={NOW}
      />
    );
    const dialog = screen.getByRole("dialog");
    expect(dialog).toHaveAttribute("aria-modal", "true");
    expect(dialog).toHaveAttribute("aria-labelledby", "slc-title");
  });

  it("states that the lock reaches the file system", () => {
    // The wording that matters most: the operator is not only locking a volume.
    renderDialog(
      <SnaplockConfirmDialog
        intent={createVolume}
        onConfirm={vi.fn()}
        onCancel={vi.fn()}
        now={NOW}
      />
    );
    // Said in more than one place, so this asserts presence rather than a
    // single match: the SVM and file system line, and the billing line.
    expect(screen.getAllByText(/file system/i).length).toBeGreaterThan(0);
    expect(screen.getByText(/its SVM and the file system cannot be deleted/i)).toBeInTheDocument();
  });

  it("substitutes placeholders instead of leaving them visible", () => {
    renderDialog(
      <SnaplockConfirmDialog
        intent={createVolume}
        onConfirm={vi.fn()}
        onCancel={vi.fn()}
        now={NOW}
      />
    );
    // A missed substitution renders as literal braces, which is easy to ship
    // and easy to miss by eye.
    expect(document.body.textContent).not.toMatch(/\{(date|period|name|keyword|type|days)\}/);
  });
});
