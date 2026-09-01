import { useSyncExternalStore } from "react";
import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "../../i18n";
import { dispatch } from "../../lib/dispatch";
import { parseResponse } from "../../utils/parseResponse";
import {
  getActivePlatform,
  setActivePlatform,
  subscribeActivePlatform,
} from "../../lib/activePlatform";

export interface DataPlatform {
  platform: string;
  systemId: string;
  name: string;
  svms: string[];
  manageable: boolean;
  discoveredBy: string;
  resourceType: string;
  connected: boolean;
  account: string;
  region: string;
}

/**
 * Which data platform the panels are scoped to, above the SVM.
 *
 * Narrowing by SVM first is the wrong entry point once an account holds more than
 * one file system: an SVM name says nothing about which system it belongs to, and
 * reading the list costs an ONTAP call that needs the management LIF reachable and
 * a credential accepted before anything appears. This inventory comes from the AWS
 * control plane instead -- two read-only calls, no ONTAP credential -- so it can
 * still answer when the ONTAP path cannot, which is exactly when an operator needs
 * to know what exists.
 *
 * A platform other than the connected one is listed but not selectable. The
 * handlers read one management address from their environment, so no request can
 * be routed elsewhere; offering it would present a scope that every action then
 * fails against. Listing it is still worth doing -- an estate is visible from one
 * portal rather than hidden behind whichever cluster this deployment points at --
 * and the disabled option carries the reason.
 */
export function PlatformSelector() {
  const { t } = useTranslation();
  const active = useSyncExternalStore(subscribeActivePlatform, getActivePlatform);

  const { data } = useQuery({
    queryKey: ["platform", "inventory"],
    queryFn: async () => {
      const raw = await dispatch("platformQuery", { action: "listDataPlatforms" });
      return parseResponse<{ platforms?: DataPlatform[]; error?: string }>(raw);
    },
    // The estate does not change while a panel is open, and every panel that shows
    // a scope chain mounts this. Without a stale time each of them refetches the
    // same account-wide listing on mount.
    staleTime: 5 * 60 * 1000,
  });

  const platforms = data?.platforms ?? [];

  // Where a platform was found, shown only when the inventory spans more than one
  // place. A name is unique within an account, not across them, so two teams that
  // both call a file system after their project are indistinguishable in a single
  // list -- and appending the origin to every entry in the common single-account
  // case is noise that says nothing.
  const origins = new Set(platforms.map(p => `${p.account}/${p.region}`));
  const showOrigin = origins.size > 1;

  // One platform is nothing to choose between, and the SVM selector below already
  // says which SVM. Two is where the grouping starts to carry information.
  if (platforms.length < 2) return null;

  return (
    <label className="rm-platform-selector">
      <span className="rm-platform-label">{t("rmPlatformScope")}</span>
      <select
        value={active}
        onChange={e => setActivePlatform(e.target.value)}
        aria-describedby="rm-platform-hint"
      >
        {/* "" is what every panel did before this existed: no explicit choice. */}
        <option value="">{t("rmPlatformAll")}</option>
        {platforms.map(p => (
          <option
            key={p.systemId}
            value={p.systemId}
            disabled={!p.connected}
            title={p.connected ? undefined : t("rmPlatformNotConnected")}
          >
            {p.name}
            {showOrigin && p.region ? ` (${[p.account, p.region].filter(Boolean).join(" · ")})` : ""}
            {p.connected ? "" : ` — ${t("rmPlatformNotConnectedShort")}`}
          </option>
        ))}
      </select>
      <span id="rm-platform-hint" className="rm-platform-hint">
        {t("rmPlatformHint")}
      </span>
    </label>
  );
}
