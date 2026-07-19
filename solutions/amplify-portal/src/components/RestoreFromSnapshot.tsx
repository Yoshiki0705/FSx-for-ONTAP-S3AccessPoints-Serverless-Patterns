import { useState } from "react";
import { generateClient } from "aws-amplify/data";
import type { Schema } from "../../amplify/data/resource";
import { portalSettings } from "../portal-settings";

const client = generateClient<Schema>();

interface RestoreFromSnapshotProps {
  currentPrefix: string;
}

/**
 * Restore from Snapshot action button for Files tab.
 *
 * Triggers a FlexClone creation workflow:
 * 1. Creates a FlexClone of the volume at a point-in-time snapshot
 * 2. Attaches an S3 Access Point to the cloned volume
 * 3. Returns the clone details (shown in Results tab via FlexCloneStatus)
 *
 * This uses the FC7 (devops-cicd) or FC2 (dynamic-render-workflow) pattern
 * under the hood, triggered via the same Step Functions mechanism.
 *
 * Note: Requires a configured state machine that supports FlexClone operations.
 * The button is disabled when processing is not configured.
 */
export function RestoreFromSnapshot({ currentPrefix }: RestoreFromSnapshotProps) {
  const [showDialog, setShowDialog] = useState(false);
  const [snapshotName, setSnapshotName] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [result, setResult] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const handleRestore = async () => {
    if (!snapshotName.trim()) {
      setError("Snapshot name is required");
      return;
    }

    setSubmitting(true);
    setError(null);
    setResult(null);

    try {
      const response = await client.mutations.startProcessing({
        pattern: "UC1_LEGAL_COMPLIANCE", // Placeholder — in production, use a dedicated FlexClone pattern
        inputPrefix: currentPrefix,
        parameters: JSON.stringify({
          action: "RESTORE_FROM_SNAPSHOT",
          snapshotName: snapshotName.trim(),
          source: "amplify-portal",
          requestedAt: new Date().toISOString(),
        }),
      });

      if (response.data?.executionArn) {
        setResult(`Restore initiated: ${response.data.executionArn}`);
        setShowDialog(false);
        setSnapshotName("");
      } else if (response.errors) {
        setError(response.errors.map((e) => e.message).join(", "));
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to initiate restore");
    } finally {
      setSubmitting(false);
    }
  };

  if (!portalSettings.processingEnabled) {
    return null; // Don't show restore button when processing is not configured
  }

  return (
    <div className="restore-snapshot">
      <button
        className="restore-btn"
        onClick={() => setShowDialog(true)}
        title="Create a FlexClone from a snapshot for point-in-time recovery"
      >
        📸 Restore from Snapshot
      </button>

      {result && <div className="success-message">{result}</div>}

      {showDialog && (
        <div className="restore-dialog" role="dialog" aria-labelledby="restore-title">
          <div className="dialog-content">
            <h3 id="restore-title">Restore from Snapshot</h3>
            <p className="dialog-description">
              Creates a FlexClone volume from the specified snapshot.
              The clone will have its own S3 Access Point for isolated access.
            </p>

            <div className="form-group">
              <label htmlFor="snapshot-name">Snapshot Name</label>
              <input
                id="snapshot-name"
                type="text"
                value={snapshotName}
                onChange={(e) => setSnapshotName(e.target.value)}
                placeholder="e.g., daily.2026-07-18_0010"
                disabled={submitting}
              />
              <small>Enter the ONTAP snapshot name to restore from.</small>
            </div>

            <div className="form-group">
              <label>Target Prefix</label>
              <input type="text" value={currentPrefix || "/"} disabled />
            </div>

            {error && <div className="error-message">{error}</div>}

            <div className="dialog-actions">
              <button
                onClick={handleRestore}
                disabled={submitting || !snapshotName.trim()}
                className="confirm-btn"
              >
                {submitting ? "Initiating..." : "Create FlexClone"}
              </button>
              <button
                onClick={() => { setShowDialog(false); setError(null); }}
                disabled={submitting}
                className="cancel-btn"
              >
                Cancel
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
