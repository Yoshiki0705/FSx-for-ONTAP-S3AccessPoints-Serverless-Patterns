import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "../../i18n";
import { errorMessage } from "../../lib/portalQuery";
import { adminMutate, adminQuery } from "../../lib/dispatch";

interface ObjectStoreBucket {
  name: string;
  uuid: string;
  svm: string;
  volumeName: string;
  type: string;
  sizeBytes: number;
}

/**
 * ONTAP object-store bucket manager.
 *
 * These are ONTAP's own object-store buckets, a different namespace from the
 * account's AWS S3 buckets. The backend has listed and removed them for a while
 * with no UI; this panel exposes that. Delete is inline-confirmed and the
 * confirmation names the consequence the handler enforces: an S3 access point
 * still reading through the bucket loses its data path.
 */
export function ObjectStoreBucketManager() {
  const { t } = useTranslation();
  const [actionError, setActionError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  /** Bucket awaiting delete confirmation, by name. */
  const [confirmFor, setConfirmFor] = useState<string | null>(null);

  const {
    data: buckets = [],
    isPending: loading,
    error: queryError,
    refetch,
  } = useQuery({
    queryKey: ["admin", "listObjectStoreBuckets"],
    queryFn: async () => {
      const parsed = await adminQuery<{ buckets?: ObjectStoreBucket[] }>({ action: "listObjectStoreBuckets" });
      if (parsed?.error && !parsed.error.includes("Unknown action") && !parsed.error.includes("not configured")) {
        throw new Error(parsed.error);
      }
      return parsed?.buckets ?? [];
    },
  });

  const loadData = () => void refetch();
  const error = actionError ?? errorMessage(queryError, "Load failed");

  const runDelete = async (bucket: ObjectStoreBucket) => {
    setBusy(true);
    setActionError(null);
    setSuccess(null);
    try {
      const result = await adminMutate<{ success?: boolean }>({
        action: "deleteObjectStoreBucket",
        params: { name: bucket.name, confirm: true },
      });
      if (result?.success) {
        setSuccess(t("osbDeleted").replace("{name}", bucket.name));
        setConfirmFor(null);
        setTimeout(() => setSuccess(null), 4000);
        loadData();
      } else {
        setActionError(result?.error || "Delete failed");
      }
    } catch (e) {
      setActionError(e instanceof Error ? e.message : "Delete failed");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="objectstore-manager">
      {error && <div className="rm-error">⚠️ {error}</div>}
      {success && <div className="rm-success">✅ {success}</div>}

      <p className="rm-hint">{t("osbIntro")}</p>

      {loading ? (
        <div className="rm-loading">{t("ontapConnecting")}</div>
      ) : buckets.length === 0 ? (
        <p className="rm-empty">{t("osbNone")}</p>
      ) : (
        <table className="rm-table">
          <thead><tr><th>{t("osbName")}</th><th>{t("osbVolume")}</th><th>{t("osbType")}</th><th>{t("rmActions")}</th></tr></thead>
          <tbody>
            {buckets.map(b => (
              <tr key={b.uuid || b.name}>
                <td className="lu-username">{b.name}</td>
                <td>{b.volumeName || "—"}</td>
                <td>{b.type || "—"}</td>
                <td>
                  <button className="rm-btn-danger-sm" disabled={busy} onClick={() => setConfirmFor(b.name)}>
                    {t("delete")}
                  </button>
                  {confirmFor === b.name && (
                    <span className="peer-accept-row" role="alertdialog">
                      <span className="sm-confirm-text">{t("osbConfirmDelete").replace("{name}", b.name)}</span>
                      <button className="rm-btn-danger-sm" disabled={busy} onClick={() => runDelete(b)}>
                        {t("rmExecute")}
                      </button>
                      <button className="rm-btn-sm" onClick={() => setConfirmFor(null)}>
                        {t("cancel")}
                      </button>
                    </span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
