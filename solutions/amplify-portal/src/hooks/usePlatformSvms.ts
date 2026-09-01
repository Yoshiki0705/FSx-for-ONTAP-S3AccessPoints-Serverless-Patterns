import { useQuery } from "@tanstack/react-query";
import { dispatch } from "../lib/dispatch";
import { parseResponse } from "../utils/parseResponse";
import type { DataPlatform } from "../components/admin/PlatformSelector";

/**
 * The SVMs belonging to one data platform, or null when that is not known.
 *
 * Null and an empty set are different answers and the caller has to tell them
 * apart: null means there is nothing to narrow by, so the full list stands, while
 * an empty set would mean the platform genuinely has no SVMs. Filtering a correct
 * list against an inventory that has not arrived yet empties the control the
 * operator is looking at, which reads as a broken panel.
 *
 * Shares the query key with the platform selector, so the account-wide listing is
 * fetched once for a page that renders both.
 */
export function usePlatformSvms(systemId: string): Set<string> | null {
  const { data } = useQuery({
    queryKey: ["platform", "inventory"],
    queryFn: async () => {
      const raw = await dispatch("platformQuery", { action: "listDataPlatforms" });
      return parseResponse<{ platforms?: DataPlatform[]; error?: string }>(raw);
    },
    staleTime: 5 * 60 * 1000,
    // Nothing is narrowed until a platform is chosen, so there is no reason to
    // hold the account-wide listing for a panel that is not going to use it.
    enabled: Boolean(systemId),
  });

  if (!systemId) return null;
  const platform = (data?.platforms ?? []).find(p => p.systemId === systemId);
  if (!platform || platform.svms.length === 0) return null;
  return new Set(platform.svms);
}
