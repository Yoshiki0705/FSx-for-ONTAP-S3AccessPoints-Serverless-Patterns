/**
 * Shared TanStack Query client for the portal.
 *
 * Kept in its own module so the tests can build an isolated client with the same
 * defaults instead of importing the app's singleton, which would let cached data
 * leak between test files.
 */

import { QueryClient } from "@tanstack/react-query";

/**
 * Defaults chosen for an admin console over ONTAP, not a public web app.
 *
 * `staleTime` of 30s: these panels list volumes, shares, policies and snapshots.
 * Re-reading them on every remount would put avoidable load on the ONTAP
 * management LIF, which is shared with the NFS/SMB data path. Thirty seconds is
 * short enough that an operator who changes something elsewhere sees it on the
 * next navigation.
 *
 * `refetchOnWindowFocus` off: the previous behaviour fetched once on mount and on
 * an explicit refresh press. Refetching whenever the operator alt-tabs back would
 * be a new, unrequested behaviour, and on these endpoints it is not free.
 *
 * `retry` of 1: ONTAP REST calls go through a VPC Lambda, so a failure is usually
 * a real error (permissions, unreachable management IP, misconfigured SVM) rather
 * than a blip worth hammering. One retry covers a transient network fault without
 * turning a genuine failure into four.
 */
export function createPortalQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: {
        staleTime: 30_000,
        refetchOnWindowFocus: false,
        retry: 1,
      },
    },
  });
}

export const queryClient = createPortalQueryClient();
