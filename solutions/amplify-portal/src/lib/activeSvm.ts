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
 */

let activeSvm = "";
const listeners = new Set<() => void>();

/** The selected SVM, or "" for the backend's default. */
export function getActiveSvm(): string {
  return activeSvm;
}

/** Select an SVM. Notifies subscribers only when the value actually changes. */
export function setActiveSvm(name: string): void {
  if (name === activeSvm) return;
  activeSvm = name;
  for (const listener of listeners) listener();
}

/** Subscribe to changes, for `useSyncExternalStore`. Returns the unsubscribe. */
export function subscribeActiveSvm(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}
