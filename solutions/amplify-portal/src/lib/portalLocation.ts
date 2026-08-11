/**
 * The portal's address: what the URL hash means, in one place.
 *
 * There is no router. Navigation state lives in `App`, and the hash mirrors it so
 * a reload lands where the session was. Panels also navigate by assigning to the
 * hash directly (see `SnaplockStatus`), which makes the hash a contract between
 * parts of the portal rather than a private detail of the shell — so it is written
 * and read here, and nowhere else.
 *
 * The folder is part of the address for the file explorer. Held only in the
 * explorer's state, as it was, a folder had no address at all: sending someone
 * "the contracts folder" meant telling them which rows to click, a bookmark
 * returned to the root, and the back button left the section instead of going up
 * one level.
 */

/** A pane of the portal. */
export type Section =
  | "files" | "favorites" | "recent" | "watch" | "upload"
  | "process" | "agent" | "search" | "history" | "analytics"
  | "snapshots" | "arp" | "lock"
  | "versions" | "audit" | "resources" | "agentDir";

/**
 * Sections that may appear in the URL hash.
 *
 * A hash naming anything else is ignored rather than trusted, so a typed or stale
 * address cannot put the shell into a section that no longer exists.
 *
 * `watch` is absent, and has been since this list was introduced. The consequence
 * is that folder watch can be opened from the sidebar but not restored by reload:
 * its hash is written and then not recognised. Before adding it, note that the
 * section is gated on a portal setting and, unlike `resources` and `analytics`,
 * has no second guard in `App` against arrival by hash — so admitting it here
 * would make a disabled section reachable by address.
 */
export const SECTIONS: Section[] = [
  "files", "favorites", "recent", "upload", "process", "agent", "search",
  "history", "analytics", "snapshots", "arp", "lock", "versions", "audit",
  "resources", "agentDir",
];

/** Where the hash points. */
export interface PortalLocation {
  section: Section;
  /** The explorer's folder, with a trailing slash. Empty for other sections. */
  prefix: string;
}

/**
 * The hash body (no leading "#") for a section and folder.
 *
 * Segments are percent-encoded one at a time so the separators stay readable as
 * separators — `#files/dept/legal` rather than `#files/dept%2Flegal` — while a
 * folder name that itself contains a slash or a "#" cannot forge an extra level.
 */
export function hashFor(section: Section, prefix: string): string {
  if (section !== "files" || prefix === "") return section;
  const path = prefix.split("/").filter(Boolean).map(encodeURIComponent).join("/");
  return `${section}/${path}`;
}

/**
 * The section and folder a hash body names, or null if it names no section.
 *
 * Accepts a hash with or without its "#", so a caller may pass
 * `window.location.hash` unchanged.
 */
export function locationFromHash(hash: string): PortalLocation | null {
  const raw = hash.replace(/^#/, "");
  if (!raw) return null;
  const [head, ...rest] = raw.split("/");
  if (!SECTIONS.includes(head as Section)) return null;
  const segments = rest.filter(Boolean).map(decodeURIComponent);
  // A prefix always ends in "/", which is the form the listing call expects; the
  // address leaves the trailing separator off so it has no dangling slash.
  return {
    section: head as Section,
    prefix: segments.length > 0 ? `${segments.join("/")}/` : "",
  };
}

/** Where the browser currently is, by the portal's reckoning. */
export function currentLocation(): PortalLocation | null {
  return locationFromHash(window.location.hash);
}
