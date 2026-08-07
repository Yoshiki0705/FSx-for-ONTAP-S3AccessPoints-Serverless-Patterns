import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { generateClient } from "aws-amplify/data";
import type { Schema } from "../../amplify/data/resource";
import { fileQuery } from "../lib/dispatch";
import { errorMessage } from "../lib/portalQuery";
import { useTranslation } from "../i18n";

const client = generateClient<Schema>();

interface Watch {
  id: string;
  folderPrefix: string;
  notifyOnCreate?: boolean | null;
  notifyOnModify?: boolean | null;
  notifyOnDelete?: boolean | null;
  createdAt?: string | null;
}

interface Notification {
  id: string;
  source: string;
  eventType: string;
  fileKey: string;
  fileName: string;
  fileSize: number;
  clientIp: string;
  userName: string;
  timestamp: string;
}

interface InboxResponse {
  notifications?: Notification[];
  /** False when no notification table is wired, i.e. the feature is not deployed. */
  configured?: boolean;
  error?: string | null;
}

/** Event types a watch can subscribe to, and the field each maps to. */
const EVENT_KINDS = [
  { field: "notifyOnCreate", labelKey: "fwCreate" },
  { field: "notifyOnModify", labelKey: "fwModify" },
  { field: "notifyOnDelete", labelKey: "fwDelete" },
] as const;

/**
 * Folder watch: subscribe to prefixes, and read the events that arrived.
 *
 * The events do not originate in the portal. FPolicy on the SVM (or Transfer
 * Family for SFTP uploads) publishes to EventBridge, a bridge Lambda turns each
 * event into a record, and this reads them. Nothing here makes ONTAP emit
 * anything, which is why an empty inbox is reported as "no events have arrived"
 * with what to check, rather than as a working feature with nothing to show.
 *
 * Watches are stored per user (`allow.owner()`), so one person's subscriptions
 * are invisible to another. The inbox is filtered server-side by the same
 * Cognito-group path prefixes that scope file access, then narrowed to the
 * caller's own watches — a watch on "/" therefore still cannot widen what the
 * group boundary allows.
 */
export function FolderWatch() {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const [draftPrefix, setDraftPrefix] = useState("");
  const [draftKinds, setDraftKinds] = useState({
    notifyOnCreate: true,
    notifyOnModify: true,
    notifyOnDelete: true,
  });
  const [busy, setBusy] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  const WATCHES_KEY = ["folderWatches"];

  const watches = useQuery({
    queryKey: WATCHES_KEY,
    queryFn: async () => {
      const { data } = await client.models.FolderWatch.list();
      return (data ?? []) as unknown as Watch[];
    },
  });

  const watchedPrefixes = (watches.data ?? []).map((w) => w.folderPrefix).filter(Boolean);

  const inbox = useQuery({
    // Re-reads when the watch set changes, since the filter is part of the request.
    queryKey: ["folderWatchInbox", watchedPrefixes.slice().sort().join("\u0000")],
    queryFn: async () => {
      const data = await fileQuery<InboxResponse>({
        action: "listNotifications",
        params: { maxResults: 50, watchedPrefixes: watchedPrefixes.join(",") },
      });
      if (data?.error) throw new Error(data.error);
      return data ?? {};
    },
  });

  const addWatch = async () => {
    const prefix = draftPrefix.trim();
    if (!prefix) return;
    setBusy(true);
    setFormError(null);
    try {
      // Stored with a trailing slash so a prefix match cannot match a sibling
      // folder that merely starts with the same letters.
      const normalised = prefix.endsWith("/") ? prefix : `${prefix}/`;
      const { errors } = await client.models.FolderWatch.create({
        folderPrefix: normalised,
        ...draftKinds,
        createdAt: new Date().toISOString(),
      });
      if (errors?.length) {
        setFormError(errors[0].message);
      } else {
        setDraftPrefix("");
        await queryClient.invalidateQueries({ queryKey: WATCHES_KEY });
      }
    } catch (e) {
      setFormError(e instanceof Error ? e.message : t("fwAddFailed"));
    } finally {
      setBusy(false);
    }
  };

  const removeWatch = async (id: string) => {
    try {
      await client.models.FolderWatch.delete({ id });
      await queryClient.invalidateQueries({ queryKey: WATCHES_KEY });
    } catch {
      /* The list refresh below is the feedback; a failed delete leaves the row. */
    }
  };

  const notifications = inbox.data?.notifications ?? [];
  const notDeployed = inbox.data?.configured === false;

  const formatSize = (bytes: number) => {
    if (!bytes) return "—";
    if (bytes < 1024 ** 2) return `${Math.round(bytes / 1024)} KB`;
    if (bytes < 1024 ** 3) return `${(bytes / 1024 ** 2).toFixed(1)} MB`;
    return `${(bytes / 1024 ** 3).toFixed(2)} GB`;
  };

  return (
    <div className="folder-watch">
      <div className="fw-header">
        <h2>🔔 {t("fwTitle")}</h2>
        <p className="rm-hint">{t("fwIntro")}</p>
      </div>

      <section className="fw-section">
        <h3>{t("fwWatchesTitle")}</h3>
        <div className="fw-add">
          <label htmlFor="fw-prefix">{t("fwPrefix")}</label>
          <input
            id="fw-prefix"
            type="text"
            value={draftPrefix}
            placeholder="engineering/cad/"
            onChange={(e) => setDraftPrefix(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") void addWatch();
            }}
          />
          <div className="fw-kinds">
            {EVENT_KINDS.map((k) => (
              <label key={k.field}>
                <input
                  type="checkbox"
                  checked={draftKinds[k.field]}
                  onChange={(e) =>
                    setDraftKinds({ ...draftKinds, [k.field]: e.target.checked })
                  }
                />
                {t(k.labelKey)}
              </label>
            ))}
          </div>
          <button
            className="rm-btn-primary"
            onClick={() => void addWatch()}
            disabled={busy || !draftPrefix.trim()}
          >
            {busy ? t("loading") : t("fwAdd")}
          </button>
          {formError && <div className="error-message">{formError}</div>}
        </div>

        {watches.isPending ? (
          <p className="rm-loading-sm">…</p>
        ) : watches.error ? (
          <div className="error-message">
            {errorMessage(watches.error, "Failed to load watches")}
          </div>
        ) : watchedPrefixes.length === 0 ? (
          <p className="rm-empty-sm">{t("fwNoWatches")}</p>
        ) : (
          <table className="rm-table">
            <thead>
              <tr>
                <th>{t("fwPrefix")}</th>
                <th>{t("fwEvents")}</th>
                <th>{t("rmActions")}</th>
              </tr>
            </thead>
            <tbody>
              {(watches.data ?? []).map((w) => (
                <tr key={w.id}>
                  <td><code>{w.folderPrefix}</code></td>
                  <td>
                    {EVENT_KINDS.filter((k) => w[k.field]).map((k) => (
                      <span key={k.field} className="fw-kind-badge">{t(k.labelKey)}</span>
                    ))}
                  </td>
                  <td>
                    <button className="rm-btn-danger-sm" onClick={() => void removeWatch(w.id)}>
                      ✕ {t("fwRemove")}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>

      <section className="fw-section">
        <h3>{t("fwInboxTitle")}</h3>
        {notDeployed ? (
          // The switch is on but no notification store is wired, so nothing could
          // ever arrive. Saying so beats an empty table.
          <div className="fw-notice">{t("fwNotDeployed")}</div>
        ) : inbox.isPending ? (
          <p className="rm-loading-sm">…</p>
        ) : inbox.error ? (
          <div className="error-message">{errorMessage(inbox.error, "Failed to load events")}</div>
        ) : notifications.length === 0 ? (
          <div className="fw-notice">
            <p>{t("fwNoEvents")}</p>
            {/* Three things have to be true for an event to land, and only the
                third is inside the portal. Listing them is the difference between
                "broken" and "not wired up yet". */}
            <ol>
              <li>{t("fwCheck1")}</li>
              <li>{t("fwCheck2")}</li>
              <li>{t("fwCheck3")}</li>
            </ol>
          </div>
        ) : (
          <table className="rm-table">
            <thead>
              <tr>
                <th>{t("fwWhen")}</th>
                <th>{t("fwSource")}</th>
                <th>{t("fwEvent")}</th>
                <th>{t("fwFile")}</th>
                <th>{t("smSize")}</th>
                <th>{t("fwWho")}</th>
              </tr>
            </thead>
            <tbody>
              {notifications.map((n) => (
                <tr key={n.id}>
                  <td>{n.timestamp ? new Date(n.timestamp).toLocaleString() : "—"}</td>
                  <td><span className="fw-source-badge">{n.source}</span></td>
                  <td>{n.eventType}</td>
                  <td title={n.fileKey}>{n.fileName || n.fileKey}</td>
                  <td>{formatSize(n.fileSize)}</td>
                  <td>
                    {n.userName || "—"}
                    {n.clientIp ? ` (${n.clientIp})` : ""}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
    </div>
  );
}
