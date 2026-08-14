import { useState, useEffect, useRef } from "react";
import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "../../i18n";
import { errorMessage, unwrap } from "../../lib/portalQuery";
import { dispatch } from "../../lib/dispatch";
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
  /** Called when user selects a volume */
  onSelect: (volume: VolumeInfo) => void;
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
  const [selectedUuid, setSelectedUuid] = useState("");
  const [searchTerm, setSearchTerm] = useState("");
  // The committed filter, updated after the debounce. It is part of the query
  // key, so typing does not fire a request per keystroke.
  const [nameFilter, setNameFilter] = useState<string | undefined>(undefined);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const {
    data: volumes = [],
    isFetching: loading,
    error: queryError,
  } = useQuery({
    queryKey: ["admin", "volumeSelector", nameFilter ?? null, excludeFlexCache],
    queryFn: async () => {
      // Two calls rather than one with a computed action name. The filtered form
      // takes parameters the unfiltered one does not, and building the action and a
      // `Record<string, unknown>` together hid that from both the compiler and the
      // parameter check, which could not read a call whose action was a variable.
      const data = await unwrap<{ volumes?: VolumeInfo[] }>(
        nameFilter !== undefined
          ? dispatch("adminQuery", {
              action: "listVolumesFiltered",
              params: { nameFilter, maxRecords: 20 },
            })
          : dispatch("adminQuery", { action: "listVolumes" }),
      );
      // Internal root volumes are not selectable targets, and neither is a
      // FlexCache when the caller's operation is unsupported there.
      return (data?.volumes ?? []).filter(
        (v) =>
          !v.name.endsWith("_root") &&
          v.state === "online" &&
          !(excludeFlexCache && v.flexcacheEndpointType === "cache")
      );
    },
  });
  const error = errorMessage(queryError, "Failed to load volumes");

  // The auto-selected volume is derived, not stored: an effect that wrote it to
  // state would be the same extra render pass the old loader had. State only
  // holds an explicit user choice.
  const autoPick =
    autoSelectFirst && nameFilter === undefined ? volumes[0] : undefined;
  const effectiveUuid = selectedUuid || autoPick?.uuid || "";

  // The parent still has to be told which volume is in effect. This notifies it
  // once per auto-picked volume; it sets no local state.
  const notifiedRef = useRef<string | null>(null);
  useEffect(() => {
    if (!autoPick || selectedUuid) return;
    if (notifiedRef.current === autoPick.uuid) return;
    notifiedRef.current = autoPick.uuid;
    onSelect(autoPick);
  }, [autoPick, selectedUuid, onSelect]);

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
    setSelectedUuid(uuid);
    const vol = volumes.find((v) => v.uuid === uuid);
    if (vol) onSelect(vol);
  };

  if (error) {
    return <div className="error-message">{error}</div>;
  }

  return (
    <div className="volume-selector">
      <label className="volume-selector-label">
        {label || t("rmSelectVolume")}
      </label>

      {enableSearch && (
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
        <small style={{ color: "var(--color-text-secondary)" }}>{t("rmVolumeSearchHint")}</small>
      )}
    </div>
  );
}
