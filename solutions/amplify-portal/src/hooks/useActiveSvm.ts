import { useSyncExternalStore } from "react";

import { getActiveSvm, subscribeActiveSvm } from "../lib/activeSvm";

/**
 * The SVM the portal is currently scoped to, or "" for the backend's default.
 *
 * `dispatch` already fills this into every request that reads an SVM, so a panel does
 * not need it to make a correct call. It needs it to notice a change: a volume chosen
 * on one SVM does not exist on another, and a name held across a switch would be sent
 * to a scope where it resolves to nothing -- or, if the same name exists on both, to a
 * different volume.
 *
 * Subscribing rather than reading once: the selector lives outside React, so a
 * component that read the value at mount would keep the value it was mounted with.
 */
export function useActiveSvm(): string {
  return useSyncExternalStore(subscribeActiveSvm, getActiveSvm);
}
