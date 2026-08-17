/**
 * Copy text to the clipboard, including where the clipboard API does not exist.
 *
 * `navigator.clipboard` is only defined in a secure context, so on a page served
 * over plain HTTP — which is how the portal is reached from a phone on the LAN
 * before `npm run phone` sets up a tunnel — it is `undefined` rather than a
 * function that fails. A copy button written against it alone does nothing there,
 * and does nothing silently.
 *
 * Returns whether the text was copied, so a caller can show the outcome instead of
 * assuming it.
 *
 * Note: `ShareLink.tsx` and `FileLifecycle.tsx` still carry their own inline
 * copies of this. They predate this helper and are left alone here rather than
 * refactored alongside an unrelated change; new call sites should use this one.
 */
export async function copyText(text: string): Promise<boolean> {
  if (!text) return false;

  if (navigator.clipboard?.writeText) {
    try {
      await navigator.clipboard.writeText(text);
      return true;
    } catch {
      // Permission refused, or the document lost focus mid-write. Fall through to
      // the selection-based path, which needs neither.
    }
  }

  try {
    const area = document.createElement("textarea");
    area.value = text;
    // Off-screen rather than hidden: `display: none` and `visibility: hidden`
    // cannot be selected, so the copy would report success having copied nothing.
    area.style.position = "fixed";
    area.style.left = "-9999px";
    area.setAttribute("readonly", "");
    document.body.appendChild(area);
    area.select();
    const copied = document.execCommand("copy");
    document.body.removeChild(area);
    return copied;
  } catch {
    return false;
  }
}
