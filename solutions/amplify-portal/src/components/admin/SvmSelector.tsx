import { useSyncExternalStore } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "../../i18n";
import { arpQuery } from "../../lib/dispatch";
import { getActiveSvm, setActiveSvm, subscribeActiveSvm } from "../../lib/activeSvm";

interface Svm {
  name: string;
  state: string;
}

/**
 * Which SVM the portal acts on.
 *
 * A file system can hold several SVMs and the portal was pinned to one, which is
 * invisible until a volume created on another SVM does not appear in the volume list.
 *
 * The value lives outside React, in `lib/activeSvm`, because `dispatch` fills it into
 * every request that takes one -- that is what makes the whole panel set follow the
 * choice without each panel threading it through its own queries. This component only
 * renders it and offers the alternatives.
 *
 * Switching invalidates every admin query rather than adding the SVM to twenty
 * different query keys. A key that was missed would serve another SVM's data under the
 * new selection, which is worse than refetching more than strictly necessary.
 */
export function SvmSelector() {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const active = useSyncExternalStore(subscribeActiveSvm, getActiveSvm);

  const { data: svms = [] } = useQuery({
    queryKey: ["admin", "svmList"],
    queryFn: async () => {
      const data = await arpQuery<{ svms?: Svm[] }>({ action: "listSvms" });
      return (data?.svms ?? []).filter(
        // Running, and not one of FSx's own. A file system that supports multipart
        // upload through an S3 access point carries an internal SVM named after the
        // file system with an `-fsx-mpu-svm` suffix; it holds nothing an operator
        // manages, so offering it is a scope that answers with an empty list.
        s => s.state === "running" && !s.name.endsWith("-fsx-mpu-svm"),
      );
    },
  });

  // One SVM is the common case and there is nothing to choose, so the control stays
  // out of the way rather than presenting a decision that does not exist.
  if (svms.length < 2) return null;

  return (
    <label className="rm-svm-selector">
      <span className="rm-svm-label">{t("rmSvmScope")}</span>
      <select
        value={active}
        onChange={e => {
          setActiveSvm(e.target.value);
          // Every scope the choice reaches, not only the admin panels. The
          // data-protection pages read `protection` and the containment panel reads
          // `arp`, and both now take an SVM -- a key left out here would keep serving
          // the previous SVM's answer under the new selection.
          for (const scope of ["admin", "protection", "arp"]) {
            void queryClient.invalidateQueries({ queryKey: [scope] });
          }
        }}
      >
        {/* "" is the backend's own default, which is what every call sent before this
            selector existed. Naming it keeps that reachable. */}
        <option value="">{t("rmSvmDefault")}</option>
        {svms.map(s => (
          <option key={s.name} value={s.name}>
            {s.name}
          </option>
        ))}
      </select>
    </label>
  );
}
