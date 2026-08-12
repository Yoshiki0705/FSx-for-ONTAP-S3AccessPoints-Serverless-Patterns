/**
 * The overflow menu for one listing row.
 *
 * Every row used to carry its whole set of controls at once: a checkbox, a star,
 * a preview, a share button, a tag button, rename and trash. Seven glyphs on
 * every line of a file list, repeated down the page, and the reader has to
 * discount all of them to read a filename. File managers keep two or three in the
 * row and put the rest behind one button, which is what this is.
 *
 * The button is always rendered rather than appearing on hover. Hover is not a
 * state a touch screen has, and a control that exists only while the pointer is
 * over it cannot be reached by tabbing either.
 *
 * Children are the existing controls, unchanged. Two of them open panels of their
 * own, so nothing here may clip its contents — see the note on overflow in the
 * stylesheet.
 */
import { useEffect, useId, useRef, useState, type ReactNode } from "react";
import { useTranslation } from "../i18n";

interface RowMenuProps {
  /** Names the row, so the button is distinguishable from the one on every other. */
  fileName: string;
  children: ReactNode;
}

export function RowMenu({ fileName, children }: RowMenuProps) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const wrapper = useRef<HTMLSpanElement>(null);
  const trigger = useRef<HTMLButtonElement>(null);
  const menuId = useId();

  useEffect(() => {
    if (!open) return;

    // Pointerdown rather than click: a click closing the menu would also land on
    // whatever is underneath, so the first click outside would activate a control
    // the user was only dismissing the menu to see.
    const onPointerDown = (event: PointerEvent) => {
      if (!wrapper.current?.contains(event.target as Node)) setOpen(false);
    };
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key !== "Escape") return;
      setOpen(false);
      // Focus goes back to the button that opened it; leaving focus inside a
      // removed subtree drops the caret to the top of the document.
      trigger.current?.focus();
    };
    document.addEventListener("pointerdown", onPointerDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("pointerdown", onPointerDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [open]);

  return (
    <span className="row-menu" ref={wrapper}>
      <button
        ref={trigger}
        className={`row-menu-trigger ${open ? "active" : ""}`}
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        aria-controls={open ? menuId : undefined}
        aria-haspopup="true"
        aria-label={t("rowMenuLabel").replace("{name}", fileName)}
      >
        ⋮
      </button>
      {open && (
        // Not role="menu": the contents are a share panel and a tag editor as well
        // as plain buttons, and a menu role promises arrow-key navigation between
        // menuitems that these are not. A group with a name describes what is
        // actually here.
        <span className="row-menu-panel" id={menuId} role="group" aria-label={t("rowMenuLabel").replace("{name}", fileName)}>
          {/* On a phone this panel is a sheet pinned to the bottom of the screen
              rather than a dropdown under its trigger, so it can sit a long way
              from the row it acts on. The group is named for assistive tech either
              way; this is the same name, shown, for everyone else. Hidden at widths
              where the panel is still attached to its row and the name would be
              noise. */}
          <span className="row-menu-subject" aria-hidden="true">{fileName}</span>
          {children}
        </span>
      )}
    </span>
  );
}
