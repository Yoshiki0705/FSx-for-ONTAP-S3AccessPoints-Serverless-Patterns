/**
 * FlexClone status display for Results tab.
 *
 * When a processing workflow uses FlexClone (point-in-time copy of volume),
 * the Step Functions output includes clone metadata. This component renders
 * that metadata in a human-readable format.
 *
 * Expected output shape (from UC patterns that use FlexClone):
 * {
 *   flexClone: {
 *     volumeName: "clone-uc6-20260718-abc123",
 *     parentVolume: "vol_data",
 *     createdAt: "2026-07-18T15:00:00Z",
 *     status: "online" | "creating" | "deleted",
 *     sizeUsed: "128 MB",
 *     s3ApAlias: "clone-uc6-abc123-s3alias"
 *   }
 * }
 */

interface FlexCloneInfo {
  volumeName?: string;
  parentVolume?: string;
  createdAt?: string;
  status?: string;
  sizeUsed?: string;
  s3ApAlias?: string;
}

interface FlexCloneStatusProps {
  cloneInfo: FlexCloneInfo;
}

export function FlexCloneStatus({ cloneInfo }: FlexCloneStatusProps) {
  const statusIcon = (status: string | undefined) => {
    switch (status) {
      case "online": return "🟢";
      case "creating": return "🟡";
      case "deleted": return "⚫";
      default: return "⚪";
    }
  };

  return (
    <div className="flexclone-status" aria-label="FlexClone information">
      <h4>🔄 FlexClone Volume</h4>
      <dl className="clone-details">
        <dt>Volume</dt>
        <dd>{cloneInfo.volumeName || "-"}</dd>

        <dt>Parent</dt>
        <dd>{cloneInfo.parentVolume || "-"}</dd>

        <dt>Status</dt>
        <dd>
          {statusIcon(cloneInfo.status)} {cloneInfo.status || "unknown"}
        </dd>

        {cloneInfo.createdAt && (
          <>
            <dt>Created</dt>
            <dd>{new Date(cloneInfo.createdAt).toLocaleString()}</dd>
          </>
        )}

        {cloneInfo.sizeUsed && (
          <>
            <dt>Size Used</dt>
            <dd>{cloneInfo.sizeUsed}</dd>
          </>
        )}

        {cloneInfo.s3ApAlias && (
          <>
            <dt>S3 AP Alias</dt>
            <dd className="arn">{cloneInfo.s3ApAlias}</dd>
          </>
        )}
      </dl>
    </div>
  );
}
