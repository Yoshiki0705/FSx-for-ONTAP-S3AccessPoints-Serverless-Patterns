/**
 * Which SVM the admin panels are looking at.
 *
 * A file system can hold several SVMs, and the portal was pinned to one: the backend
 * defaults every action to `SVM_NAME`, and nothing in the UI ever sent a different
 * value. That is invisible until it is not -- a volume created on another SVM does not
 * appear in the volume list, and deleting it meant naming its UUID by hand.
 *
 * Kept in a module rather than in React state because `dispatch` needs to read it, and
 * `dispatch` is not a component. The subscription exists so a selector can render the
 * current value; the value itself is the source of truth for the request.
 *
 * An empty string means "whatever the backend defaults to", which is what every call
 * did before this existed and what the first render still does until the SVM list
 * arrives. It is deliberately not a guess at a name.
 *
 * The choice survives a reload through `sessionStorage`, not `localStorage`, and the
 * difference is the point: an operator working on one SVM reloads the page and keeps
 * their place, while a new tab or a later session starts from the configured default
 * rather than from a scope somebody chose days ago and has forgotten about.
 */

const STORAGE_KEY = "portal.activeSvm";

/**
 * Storage is read through a guard because it is not always there: Safari in private
 * browsing throws on access, and the portal is served over a tunnel in some setups
 * where storage is partitioned. Losing the selection is a smaller failure than the
 * panel not rendering, so every path here degrades to the default.
 */
function readStored(): string {
  try {
    return sessionStorage.getItem(STORAGE_KEY) ?? "";
  } catch {
    return "";
  }
}

let activeSvm = readStored();
const listeners = new Set<() => void>();

/** The selected SVM, or "" for the backend's default. */
export function getActiveSvm(): string {
  return activeSvm;
}

/** Select an SVM. Notifies subscribers only when the value actually changes. */
export function setActiveSvm(name: string): void {
  if (name === activeSvm) return;
  activeSvm = name;
  try {
    if (name) sessionStorage.setItem(STORAGE_KEY, name);
    else sessionStorage.removeItem(STORAGE_KEY);
  } catch {
    // The selection still applies to this page; it just will not survive a reload.
  }
  for (const listener of listeners) listener();
}

/** Subscribe to changes, for `useSyncExternalStore`. Returns the unsubscribe. */
export function subscribeActiveSvm(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}
