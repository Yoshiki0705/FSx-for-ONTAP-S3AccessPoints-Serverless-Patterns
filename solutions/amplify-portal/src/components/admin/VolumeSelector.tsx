import { useState, useEffect, useRef, useCallback } from "react";
import { generateClient } from "aws-amplify/data";
import type { Schema } from "../../../amplify/data/resource";
import { useTranslation } from "../../i18n";
import { parseResponse } from "../../utils/parseResponse";

const client = generateClient<Schema>();

export interface VolumeInfo {
  name: string;
  uuid: string;
  sizeGiB: number;
  state: string;
  securityStyle: string;
  snaplockType: string;
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
export function VolumeSelector({ onSelect, label, showUuid = false, autoSelectFirst = false, enableSearch = false }: VolumeSelectorProps) {
  const { t } = useTranslation();
  const [volumes, setVolumes] = useState<VolumeInfo[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedUuid, setSelectedUuid] = useState("");
  const [searchTerm, setSearchTerm] = useState("");
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const loadVolumes = useCallback(async (nameFilter?: string) => {
    setLoading(true);
    try {
      const action = nameFilter !== undefined ? "listVolumesFiltered" : "listVolumes";
      const params: Record<string, unknown> = {};
      if (nameFilter !== undefined) {
        params.nameFilter = nameFilter;
        params.maxRecords = 20;
      }
      const response = await client.queries.adminQuery({
        action,
        params: JSON.stringify(params),
      });
      const data = parseResponse<{ volumes?: VolumeInfo[]; error?: string }>(response);
      if (data) {
        if (data.error) setError(data.error);
        else {
          // Filter out internal volumes (root volumes)
          const userVolumes = (data.volumes || []).filter(
            (v) => !v.name.endsWith("_root") && v.state === "online"
          );
          setVolumes(userVolumes);
          // Auto-select first if requested and no filter active
          if (autoSelectFirst && userVolumes.length > 0 && !nameFilter) {
            setSelectedUuid(userVolumes[0].uuid);
            onSelect(userVolumes[0]);
          }
        }
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load volumes");
    } finally {
      setLoading(false);
    }
  }, [autoSelectFirst, onSelect]);

  // Initial load (no filter)
  useEffect(() => {
    loadVolumes();
  }, []);

  // Debounced search (300ms) for enableSearch mode
  const handleSearchChange = (value: string) => {
    setSearchTerm(value);
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => {
      loadVolumes(value || undefined);
    }, 300);
  };

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
          value={selectedUuid}
          onChange={(e) => handleChange(e.target.value)}
          className="volume-selector-dropdown"
        >
          <option value="">{t("rmSelectVolumePlaceholder")}</option>
          {volumes.map((vol) => (
            <option key={vol.uuid} value={vol.uuid}>
              {vol.name} ({vol.sizeGiB} GiB, {vol.securityStyle})
              {showUuid ? ` [${vol.uuid.slice(0, 8)}...]` : ""}
              {vol.snaplockType !== "non_snaplock" ? " 🔒" : ""}
            </option>
          ))}
        </select>
      )}
      {enableSearch && volumes.length === 20 && (
        <small style={{ color: "#666" }}>{t("rmVolumeSearchHint")}</small>
      )}
    </div>
  );
}
