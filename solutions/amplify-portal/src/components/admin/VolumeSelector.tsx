import { useState, useEffect, useRef } from "react";
import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "../../i18n";
import { errorMessage, unwrap } from "../../lib/portalQuery";
import { dispatch } from "../../lib/dispatch";
import { useActiveSvm } from "../../hooks/useActiveSvm";
import type { VolumeUuid } from "../../lib/dispatchActions";

export interface VolumeInfo {
  name: string;
  /**
   * ONTAP's UUID for the volume, branded here.
   *
   * This selector is where four panels get the identifier they then pass to
   * resize, delete, quota, qtree and locking actions. Branding it once here is
   * what stops any of them handing a volume *name* to one of those.
   */
  uuid: VolumeUuid;
  sizeGiB: number;
  state: string;
  securityStyle: string;
  snaplockType: string;
  /**
   * Quota enforcement as ONTAP reports it: "off", "initializing", "on" or "mixed".
   *
   * From `quota.state`, not `quota.enabled` -- the second is the request and the first
   * is what the volume is doing. A volume with quotas switched on reports `state: "on"`
   * and `enabled: false`, so reading `enabled` says the opposite of the truth.
   */
  quotaState?: string;
  /**
   * The QoS policy in effect on this volume, or "" for none.
   *
   * A policy that is assigned cannot be deleted, so the QoS panel needs to see the
   * assignment before it offers a delete.
   */
  qosPolicyName?: string;
  /**
   * "none" | "cache" | "origin", from ONTAP's `flexcache_endpoint_type`.
   *
   * A FlexCache volume supports none of snapshots, quotas, qtrees, cloning,
   * SnapRestore, SnapMirror or ARP. Panels that offer one of those pass
   * `excludeFlexCache` so the volume cannot be chosen in the first place; the
   * handlers refuse it as well, because the selector is not the only caller.
   */
  flexcacheEndpointType?: "none" | "cache" | "origin";
}

interface VolumeSelectorProps {
  /**
   * Called when the user picks a volume, and with `null` when a pick stops being
   * valid because the active SVM changed under it.
   *
   * The null case is not a formality. A volume name is unique within an SVM, not
   * within a file system, and same-named volumes across SVMs are ordinary; an action
   * that resolves a name -- creating a qtree, adding a quota rule -- would resolve a
   * leftover name against the new SVM and land on a different volume that happens to
   * share it. Panels keying off `uuid` are safe either way, but they read the same
   * prop, so the signal is delivered to all of them rather than to the ones that
   * remembered to ask.
   */
  onSelect: (volume: VolumeInfo | null) => void;
  /** Label displayed above the selector */
  label?: string;
  /** Show UUID in the dropdown */
  showUuid?: boolean;
  /** Auto-select first volume on load */
  autoSelectFirst?: boolean;
  /** Enable search/filter for large environments */
  enableSearch?: boolean;
  /**
   * Drop FlexCache volumes from the list.
   *
   * For panels whose operation ONTAP does not support at a cache. Offering the
   * volume and then failing is worse than not offering it: the ONTAP-side error
   * does not mention FlexCache, so the refusal looks arbitrary.
   */
  excludeFlexCache?: boolean;
}

/**
 * Shared Volume Selector — dropdown populated from ONTAP REST API.
 *
 * Used by: QuotaManager, SnaplockManager, SnapshotAdminManager, QtreeManager
 * Replaces manual volume name/UUID input with a pre-populated dropdown.
 *
 * P4 enhancement: Optional search mode with debounce (300ms) for large environments.
 * Uses listVolumesFiltered action with ONTAP REST wildcard filter (name=*keyword*).
 */
export function VolumeSelector({ onSelect, label, showUuid = false, autoSelectFirst = false, enableSearch = false, excludeFlexCache = false }: VolumeSelectorProps) {
  const { t } = useTranslation();
  // The pick carries the SVM it was made in, so the pair can be checked rather than
  // trusted. A bare UUID could not say which scope it came from.
  const [picked, setPicked] = useState<{ uuid: string; svm: string } | null>(null);
  const [searchTerm, setSearchTerm] = useState("");
  // The committed filter, updated after the debounce. It is part of the query
  // key, so typing does not fire a request per keystroke.
  const [nameFilter, setNameFilter] = useState<string | undefined>(undefined);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  // The scope the list is of. In the key rather than left to the invalidation the SVM
  // switcher fires: a key that omits a value the response depends on can serve the other
  // SVM's volumes while it refetches, and with `autoSelectFirst` that list is not just
  // displayed -- one of its volumes is handed to the parent as the chosen one.
  const activeSvm = useActiveSvm();

  const {
    data,
    isFetching: loading,
    error: queryError,
  } = useQuery({
    queryKey: [
      "admin",
      "volumeSelector",
      activeSvm || null,
      nameFilter ?? null,
      excludeFlexCache,
    ],
    queryFn: async () => {
      // Two calls rather than one with a computed action name. The filtered form
      // takes parameters the unfiltered one does not, and building the action and a
      // `Record<string, unknown>` together hid that from both the compiler and the
      // parameter check, which could not read a call whose action was a variable.
      const data = await unwrap<{ volumes?: VolumeInfo[]; truncated?: boolean }>(
        nameFilter !== undefined
          ? dispatch("adminQuery", {
              action: "listVolumesFiltered",
              params: { nameFilter, maxRecords: 20 },
            })
          : dispatch("adminQuery", { action: "listVolumes" }),
      );
      // Internal root volumes are not selectable targets, and neither is a
      // FlexCache when the caller's operation is unsupported there.
      const volumes = (data?.volumes ?? []).filter(
        (v) =>
          !v.name.endsWith("_root") &&
          v.state === "online" &&
          !(excludeFlexCache && v.flexcacheEndpointType === "cache")
      );
      // Whether ONTAP had more than this page. Carried alongside rather than dropped:
      // a dropdown of the first fifty volumes on a file system with hundreds looks
      // exactly like a complete list, and the operator's volume may simply not be in
      // it. Reported below, and search is the way past it.
      return { volumes, truncated: data?.truncated === true };
    },
  });
  const volumes = data?.volumes ?? [];
  const truncated = data?.truncated === true;
  const error = errorMessage(queryError, "Failed to load volumes");

  // A pick outside the active SVM is not dropped from state, it is read as void. The
  // alternative was clearing it in an effect, which is state written from an effect --
  // and the pass in between renders the stale pair.
  const selectedUuid = picked && picked.svm === activeSvm ? picked.uuid : "";

  // The auto-selected volume is derived, not stored: an effect that wrote it to
  // state would be the same extra render pass the old loader had. State only
  // holds an explicit user choice.
  const autoPick =
    autoSelectFirst && nameFilter === undefined ? volumes[0] : undefined;
  const effectiveUuid = selectedUuid || autoPick?.uuid || "";
  // What the parent should be acting on, which is not always what it was last told:
  // a scope change can void a pick without anyone clicking anything.
  const effectiveVolume = volumes.find((v) => v.uuid === effectiveUuid) ?? null;

  // One notification path for every way the effective volume can change -- an explicit
  // pick, an auto-pick arriving with the list, or a scope change voiding one. Keyed by
  // UUID so a refetch that returns an equal list does not re-report, and seeded with ""
  // because "no volume" is what the parent already assumes at mount.
  const reportedRef = useRef<string>("");
  useEffect(() => {
    const key = effectiveVolume?.uuid ?? "";
    if (reportedRef.current === key) return;
    reportedRef.current = key;
    onSelect(effectiveVolume);
  }, [effectiveVolume, onSelect]);

  // Debounced search (300ms) for enableSearch mode
  const handleSearchChange = (value: string) => {
    setSearchTerm(value);
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => {
      setNameFilter(value || undefined);
    }, 300);
  };

  // The select's value is a plain string; the branded UUID comes from the volume it
  // identifies, not from the DOM.
  const handleChange = (uuid: string) => {
    setPicked(uuid ? { uuid, svm: activeSvm } : null);
    const vol = volumes.find((v) => v.uuid === uuid) ?? null;
    // Reported here as well as from the effect so the click lands in the same commit,
    // and recorded so the effect does not repeat it. The placeholder is a choice too:
    // it means "no volume", and a parent still holding the previous one would act on it.
    reportedRef.current = vol?.uuid ?? "";
    onSelect(vol);
  };

  if (error) {
    return <div className="error-message">{error}</div>;
  }

  return (
    <div className="volume-selector">
      <label className="volume-selector-label">
        {label || t("rmSelectVolume")}
      </label>

      {(enableSearch || truncated) && (
        <input
          type="text"
          className="volume-selector-search"
          value={searchTerm}
          onChange={(e) => handleSearchChange(e.target.value)}
          placeholder={t("rmVolumeSearchPlaceholder")}
          style={{ marginBottom: "0.25rem", width: "100%" }}
        />
      )}

      {loading ? (
        <select disabled>
          <option>{t("loading")}</option>
        </select>
      ) : (
        <select
          value={effectiveUuid}
          onChange={(e) => handleChange(e.target.value)}
          className="volume-selector-dropdown"
        >
          <option value="">{t("rmSelectVolumePlaceholder")}</option>
          {volumes.map((vol) => (
            <option key={vol.uuid} value={vol.uuid}>
              {vol.name} ({vol.sizeGiB} GiB, {vol.securityStyle})
              {vol.flexcacheEndpointType === "cache" ? " ⚡FlexCache" : ""}
              {vol.flexcacheEndpointType === "origin" ? " 📦origin" : ""}
              {showUuid ? ` [${vol.uuid.slice(0, 8)}...]` : ""}
              {vol.snaplockType !== "non_snaplock" ? " 🔒" : ""}
            </option>
          ))}
        </select>
      )}
      {enableSearch && volumes.length === 20 && (
        <small className="volume-selector-note">{t("rmVolumeSearchHint")}</small>
      )}
      {/* Said plainly rather than left to be inferred from a list that ends. */}
      {truncated && nameFilter === undefined && (
        <small className="volume-selector-note volume-selector-truncated">
          {t("rmVolumeListTruncated").replace("{count}", String(volumes.length))}
        </small>
      )}
    </div>
  );
}
