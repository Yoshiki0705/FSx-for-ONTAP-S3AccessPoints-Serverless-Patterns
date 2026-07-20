import { useState, useEffect } from "react";
import { generateClient } from "aws-amplify/data";
import type { Schema } from "../../amplify/data/resource";

const client = generateClient<Schema>();

interface Snapshot {
  name: string;
  createTime: string | null;
  snapshotId: string | null;
  state: string | null;
  comment: string | null;
}

/**
 * Version History component.
 *
 * Displays ONTAP snapshots for the current volume, enabling users to:
 * 1. See when snapshots were taken (point-in-time history)
 * 2. Trigger a FlexClone restore from a selected snapshot
 * 3. Browse past file states (via FlexClone + S3 AP)
 *
 * Architecture:
 *   AppSync query → VPC Lambda → ONTAP REST API → Snapshot list
 *
 * Note: Snapshot access requires ONTAP management LIF connectivity.
 * If ONTAP is not configured, this component shows an info message.
 */
export function VersionHistory() {
  const [snapshots, setSnapshots] = useState<Snapshot[]>([]);
  const [volumeName, setVolumeName] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadSnapshots = async () => {
    setLoading(true);
    setError(null);

    try {
      const response = await client.queries.listSnapshots({
        maxResults: 20,
      });

      if (response.data) {
        setSnapshots((response.data.snapshots || []) as Snapshot[]);
        setVolumeName(response.data.volumeName || "");
        if (response.data.error) {
          setError(response.data.error);
        }
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load snapshots");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadSnapshots();
  }, []);

  const formatDate = (isoString: string | null) => {
    if (!isoString) return "—";
    try {
      return new Date(isoString).toLocaleString();
    } catch {
      return isoString;
    }
  };

  const getSnapshotType = (name: string): string => {
    if (name.startsWith("daily.")) return "Daily";
    if (name.startsWith("hourly.")) return "Hourly";
    if (name.startsWith("weekly.")) return "Weekly";
    if (name.startsWith("snapmirror.")) return "SnapMirror";
    return "Manual";
  };

  return (
    <div className="version-history">
      <div className="version-history-header">
        <h3>Version History (Snapshots)</h3>
        {volumeName && (
          <span className="volume-badge" title="Source volume">
            Volume: {volumeName}
          </span>
        )}
        <button
          onClick={loadSnapshots}
          disabled={loading}
          className="refresh-btn"
          title="Refresh snapshot list"
        >
          {loading ? "Loading..." : "Refresh"}
        </button>
      </div>

      {error && (
        <div className="info-message">
          <p>{error}</p>
          <small>
            To enable Version History, configure ONTAP_MGMT_IP, ONTAP_SECRET_NAME,
            and VOLUME_NAME environment variables on the ListSnapshots Lambda.
          </small>
        </div>
      )}

      {!error && snapshots.length === 0 && !loading && (
        <p className="empty-state">No snapshots found for this volume.</p>
      )}

      {snapshots.length > 0 && (
        <table className="snapshot-table" role="grid" aria-label="Volume snapshots">
          <thead>
            <tr>
              <th scope="col">Snapshot Name</th>
              <th scope="col">Type</th>
              <th scope="col">Created</th>
              <th scope="col">State</th>
              <th scope="col">Actions</th>
            </tr>
          </thead>
          <tbody>
            {snapshots.map((snap) => (
              <tr key={snap.snapshotId || snap.name}>
                <td className="snapshot-name" title={snap.comment || undefined}>
                  {snap.name}
                </td>
                <td>
                  <span className={`type-badge type-${getSnapshotType(snap.name).toLowerCase()}`}>
                    {getSnapshotType(snap.name)}
                  </span>
                </td>
                <td>{formatDate(snap.createTime)}</td>
                <td>
                  <span className={`state-badge state-${snap.state}`}>
                    {snap.state || "valid"}
                  </span>
                </td>
                <td>
                  <button
                    className="action-btn"
                    title="Create FlexClone from this snapshot to browse past files"
                    onClick={() => {
                      // This triggers the existing RestoreFromSnapshot flow
                      // with the snapshot name pre-filled
                      window.dispatchEvent(
                        new CustomEvent("restore-snapshot", {
                          detail: { snapshotName: snap.name },
                        })
                      );
                    }}
                  >
                    Browse this version
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      <div className="version-history-footer">
        <small>
          Each snapshot is a point-in-time view of the volume. "Browse this version"
          creates a FlexClone with its own S3 Access Point for isolated access.
        </small>
      </div>
    </div>
  );
}
