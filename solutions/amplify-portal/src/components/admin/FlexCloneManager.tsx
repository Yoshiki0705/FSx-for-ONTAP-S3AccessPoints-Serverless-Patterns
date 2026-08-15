import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { errorMessage } from "../../lib/portalQuery";
import { adminMutate, adminQuery } from "../../lib/dispatch";
import type { VolumeUuid } from "../../lib/dispatchActions";
import { useTranslation } from "../../i18n";

interface FlexClone {
  name: string;
  /** The clone's own volume UUID, branded where it arrives. */
  uuid: VolumeUuid;
  sizeGiB: number;
  state: string;
  parentVolume: string;
  parentSnapshot: string;
  splitInitiated: boolean;
  splitCompletePercent: number;
  usedGiB: number;
}

export function FlexCloneManager() {
  const { t } = useTranslation();
  // Errors raised by the create/split handlers, kept separate from the query's own
  // error so a failed action does not read as a failed load, and vice versa.
  const [actionError, setActionError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [showCreate, setShowCreate] = useState(false);

  const [cloneName, setCloneName] = useState("");
  const [parentVolume, setParentVolume] = useState("");
  const [parentSnapshot, setParentSnapshot] = useState("");

  const clearSuccess = () => setTimeout(() => setSuccess(null), 3000);

  // Deliberately not using `unwrap` here. This action tolerates two payload errors
  // — "Unknown action" and "not configured" — and shows an empty list instead,
  // because FlexClone is optional and a cluster without it should render an empty
  // panel rather than an error. `unwrap` promotes every payload error to a
  // rejection, which would turn that supported configuration into a failure.
  const {
    data: clones = [],
    isPending: loading,
    error: queryError,
    refetch,
  } = useQuery({
    queryKey: ["admin", "listFlexClones"],
    queryFn: async () => {
      const data = await adminQuery<{ clones?: FlexClone[] }>({ action: "listFlexClones" });
      if (data?.error && !data.error.includes("Unknown action") && !data.error.includes("not configured")) {
        throw new Error(data.error);
      }
      return data?.clones ?? [];
    },
  });

  const loadClones = () => void refetch();
  const setError = setActionError;
  const error = actionError ?? errorMessage(queryError, "Load failed");

  const handleCreate = async () => {
    if (!cloneName || !parentVolume) { setError(t("fcCloneNameRequired")); return; }
    setError(null);
    try {
      const data = await adminMutate<{ success?: boolean }>({
        action: "createFlexClone",
        params: { cloneName, parentVolume, parentSnapshot },
      });
      if (data?.success) {
        setSuccess(t("fcCloneCreated")); setShowCreate(false);
        setCloneName(""); setParentVolume(""); setParentSnapshot("");
        clearSuccess(); loadClones();
      } else setError(data?.error || "Create failed");
    } catch (e) { setError(e instanceof Error ? e.message : "Create failed"); }
  };

  /**
   * Split a clone from its parent.
   *
   * The confirmation carries the two things a reader needs at that moment: it cannot be
   * undone, and on this platform it does not cost the parent's capacity. The second half
   * used to say the opposite -- "consumes full capacity" -- which is pre-9.4 behaviour and
   * was measured false here: a 10 GiB clone used 348 KB after its split.
   */
  const handleSplit = async (clone: FlexClone) => {
    if (!window.confirm(t("fcSplitConfirm").replace("{name}", clone.name))) return;
    try {
      const data = await adminMutate<{ success?: boolean }>({
        action: "splitFlexClone",
        params: { volumeUuid: clone.uuid, volumeName: clone.name },
      });
      if (data?.success) { setSuccess(t("fcSplitInitiated")); clearSuccess(); loadClones(); }
      else setError(data?.error || "Split failed");
    } catch (e) { setError(e instanceof Error ? e.message : "Split failed"); }
  };

  return (
    <div className="flexclone-manager">
      {error && <div className="rm-error">⚠️ {error}</div>}
      {success && <div className="rm-success">✅ {success}</div>}

      <div className="lu-toolbar">
        <span className="lu-count">{clones.length} FlexClones</span>
        <button className="rm-btn-primary" onClick={() => setShowCreate(true)}>+ {t("fcCreateClone")}</button>
      </div>

      {/* Split is one button and several consequences, and the button alone cannot carry
          them: it is irreversible, its cost depends on the platform, its progress figure
          is counted in a unit that surprises people, and whether to press it at all
          depends on what happens to the parent later. Collapsed, so the panel stays a
          panel, and open is one click for anyone who has not done this before. */}
      <details className="fc-split-guide">
        <summary>{t("fcSplitGuideTitle")}</summary>

        {/* Why the parent's capacity stops moving once a clone exists. First, because it
            is what makes the rest of this worth reading: a clone is cheap to make, and
            the cost it does have is paid by the parent's snapshot, in a place neither
            this panel nor the volume list used to mention. */}
        <p className="fc-split-heading">{t("fcLockTitle")}</p>
        <ul>
          <li>{t("fcLock1")}</li>
          <li>{t("fcLock2")}</li>
          <li>{t("fcLock3")}</li>
          <li>{t("fcLock4")}</li>
        </ul>

        <p className="fc-split-heading">{t("fcSplitWhenTitle")}</p>
        <ul>
          <li>{t("fcSplitWhen1")}</li>
          <li>{t("fcSplitWhen2")}</li>
          <li>{t("fcSplitWhen3")}</li>
          <li>{t("fcSplitWhen4")}</li>
        </ul>

        <p className="fc-split-heading">{t("fcSplitFactsTitle")}</p>
        <ul>
          <li>{t("fcSplitFact1")}</li>
          <li>{t("fcSplitFact2")}</li>
          <li>{t("fcSplitFact3")}</li>
          <li>{t("fcSplitFact4")}</li>
          <li>{t("fcSplitFact5")}</li>
          <li>{t("fcSplitFact6")}</li>
        </ul>

        <p className="rm-hint">{t("fcSplitEstimateNote")}</p>
        <p className="rm-hint">
          {t("fcSplitSources")}:{" "}
          <a
            href="https://docs.netapp.com/us-en/ontap/volumes/split-flexclone-from-parent-task.html"
            target="_blank"
            rel="noreferrer"
          >
            ONTAP docs
          </a>
          {" / "}
          <a
            href="https://kb.netapp.com/on-prem/ontap/Ontap_OS/OS-KBs/FAQ_-_FlexClone_split"
            target="_blank"
            rel="noreferrer"
          >
            NetApp KB
          </a>
        </p>
      </details>

      {showCreate && (
        <div className="rm-create-form">
          <h4>{t("fcCreateClone")}</h4>
          <div className="rm-form-row">
            <label>{t("fcCloneName")}</label>
            <input type="text" value={cloneName} onChange={e => setCloneName(e.target.value)} placeholder="clone_dev_01" />
          </div>
          <div className="rm-form-row">
            <label>{t("fcParentVolume")}</label>
            <input type="text" value={parentVolume} onChange={e => setParentVolume(e.target.value)} placeholder="vol_production" />
          </div>
          <div className="rm-form-row">
            <label>{t("fcParentSnapshot")}</label>
            <input type="text" value={parentSnapshot} onChange={e => setParentSnapshot(e.target.value)} placeholder={t("fcSnapshotOptional")} />
          </div>
          <div className="rm-form-actions">
            <button className="rm-btn-primary" onClick={handleCreate}>{t("rmCreate")}</button>
            <button className="rm-btn-secondary" onClick={() => setShowCreate(false)}>{t("cancel")}</button>
          </div>
          <p className="rm-hint">{t("fcCreateHint")}</p>
        </div>
      )}

      {loading ? <div className="rm-loading">{t("ontapConnecting")}</div> : clones.length === 0 ? (
        <p className="rm-empty">{t("fcNoClones")}</p>
      ) : (
        <table className="rm-table">
          <thead><tr>
            <th>{t("fcCloneName")}</th><th>{t("fcParentVolume")}</th><th>{t("fcParentSnapshot")}</th>
            <th>{t("rmVolumeSize")}</th><th>{t("rmState")}</th><th>{t("rmActions")}</th>
          </tr></thead>
          <tbody>
            {clones.map(c => (
              <tr key={c.uuid}>
                <td className="lu-username">{c.name}</td>
                <td>{c.parentVolume}</td>
                <td>{c.parentSnapshot || "—"}</td>
                <td>{c.sizeGiB} GiB</td>
                <td>
                  {c.splitInitiated ? (
                    <span className="lu-badge active">{t("fcSplitting")} {c.splitCompletePercent}%</span>
                  ) : (
                    <span className="lu-badge">{c.state}</span>
                  )}
                </td>
                <td>
                  {!c.splitInitiated && (
                    <button className="rm-btn-sm" onClick={() => handleSplit(c)} title={t("fcSplitTitle")}>
                      {t("fcSplit")}
                    </button>
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
