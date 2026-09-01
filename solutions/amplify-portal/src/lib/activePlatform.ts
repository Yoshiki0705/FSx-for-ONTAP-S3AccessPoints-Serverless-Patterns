/**
 * Which data platform the portal is scoped to, above the SVM.
 *
 * The layer exists because narrowing by SVM first is the wrong entry point in an
 * estate with several file systems: an SVM name carries no indication of which
 * system it belongs to, so the list is noise, and reading it costs an ONTAP call
 * that needs the management LIF reachable and a credential accepted before
 * anything can be shown at all.
 *
 * Held in a module rather than in React state for the same reason as the SVM: it
 * has to be readable from outside a component. Unlike the SVM it is *not* sent as
 * a request parameter -- the handlers reach one cluster, configured in their
 * environment, so a platform cannot be selected by naming it in a payload. What
 * this value does is scope the lists the browser draws, and mark when a chosen
 * platform is not the one the actions address.
 *
 * "" means no explicit choice, which is what every panel did before this existed.
 * It is deliberately not a guess at the connected platform: that would claim a
 * scope the operator did not pick, and the inventory arrives asynchronously so
 * the guess would also change under them on first load.
 *
 * `sessionStorage`, matching the SVM: a reload keeps the operator's place, while
 * a new tab starts from the default rather than from a scope chosen days ago.
 */

const STORAGE_KEY = "portal.activePlatform";

/**
 * Storage is read through a guard because it is not always there: Safari in
 * private browsing throws on access, and the portal is served over a tunnel in
 * some setups where storage is partitioned. Losing the selection is a smaller
 * failure than the panel not rendering.
 */
function readStored(): string {
  try {
    return sessionStorage.getItem(STORAGE_KEY) ?? "";
  } catch {
    return "";
  }
}

let activePlatform = readStored();
const listeners = new Set<() => void>();

/** The selected platform's system ID, or "" for no explicit choice. */
export function getActivePlatform(): string {
  return activePlatform;
}

/** Select a platform. Notifies subscribers only when the value changes. */
export function setActivePlatform(systemId: string): void {
  if (systemId === activePlatform) return;
  activePlatform = systemId;
  try {
    if (systemId) sessionStorage.setItem(STORAGE_KEY, systemId);
    else sessionStorage.removeItem(STORAGE_KEY);
  } catch {
    // The selection still applies to this page; it just will not survive a reload.
  }
  for (const listener of listeners) listener();
}

/** Subscribe to changes, for `useSyncExternalStore`. Returns the unsubscribe. */
export function subscribeActivePlatform(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}
