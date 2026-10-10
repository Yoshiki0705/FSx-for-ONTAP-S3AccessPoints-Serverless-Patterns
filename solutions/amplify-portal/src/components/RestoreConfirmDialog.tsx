/**
 * Confirmation + new-volume form for an AWS Backup restore, stated as consequences.
 *
 * Mirrors `SnaplockConfirmDialog`: a click sets a pending intent, the dialog
 * restates what the write does in one sentence, and only `onConfirm` fires the
 * mutation. A restore is additive — it creates a NEW volume and never overwrites an
 * existing one — so the gate is a CHECKBOX acknowledgement, not the typed keyword
 * the truly irreversible SnapLock operations use.
 *
 * The form collects the new-volume metadata the FSx for ONTAP restore requires
 * (name, SVM, junction path, size) plus the two optional fields (storage efficiency,
 * tiering policy). There is no overwrite / restore-in-place control: the AWS Backup
 * API forbids it, and the panel copy states "create a NEW volume in an existing file
 * system".
 */

import { useState } from "react";
import { useTranslation } from "../i18n";

/** The new-volume metadata the restore mutation needs. */
export interface RestoreFormValues {
  name: string;
  storageVirtualMachineId: string;
  junctionPath: string;
  sizeInMegabytes: number;
  storageEfficiencyEnabled: boolean;
  tieringPolicy: string;
}

interface RestoreConfirmDialogProps {
  /** The recovery point being restored, for the dialog heading. */
  recoveryPointArn: string;
  /** SVM ids a restore may target, constraining the SVM dropdown. */
  allowedSvmIds: string[];
  /** Tiering policies offered in the optional dropdown. */
  tieringPolicies: string[];
  /** Called with the assembled values once the operator confirms. */
  onConfirm: (values: RestoreFormValues) => void;
  onCancel: () => void;
}

const DEFAULT_TIERING = "SNAPSHOT_ONLY";

export function RestoreConfirmDialog({
  recoveryPointArn,
  allowedSvmIds,
  tieringPolicies,
  onConfirm,
  onCancel,
}: RestoreConfirmDialogProps) {
  const { t } = useTranslation();
  const [name, setName] = useState("");
  const [svm, setSvm] = useState(allowedSvmIds[0] ?? "");
  const [junctionPath, setJunctionPath] = useState("");
  const [sizeMb, setSizeMb] = useState("");
  const [storageEfficiency, setStorageEfficiency] = useState(false);
  const [tiering, setTiering] = useState(tieringPolicies[0] ?? DEFAULT_TIERING);
  const [acknowledged, setAcknowledged] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  const sizeValue = Number(sizeMb);
  const requiredFilled =
    name.trim() !== "" &&
    svm.trim() !== "" &&
    junctionPath.trim() !== "" &&
    sizeMb.trim() !== "" &&
    Number.isFinite(sizeValue) &&
    sizeValue > 0;
  const ready = requiredFilled && acknowledged;

  const submit = () => {
    if (!requiredFilled) {
      setFormError(t("rpRestoreRequiredField"));
      return;
    }
    setFormError(null);
    onConfirm({
      name: name.trim(),
      storageVirtualMachineId: svm,
      junctionPath: junctionPath.trim(),
      sizeInMegabytes: sizeValue,
      storageEfficiencyEnabled: storageEfficiency,
      tieringPolicy: tiering,
    });
  };

  return (
    <div className="slc-backdrop" role="dialog" aria-modal="true" aria-labelledby="rpr-title">
      <div className="slc-dialog">
        <h3 id="rpr-title" className="slc-title">
          {t("rpRestoreTitle")}
        </h3>

        <p className="slc-subject">{recoveryPointArn}</p>

        {/* The one-sentence consequence: new volume only, no overwrite. */}
        <p className="slc-until">{t("rpRestoreNewVolumeNote")}</p>

        {formError && <div className="error-message">{formError}</div>}

        <div className="create-form">
          <div className="form-group">
            <label htmlFor="rpr-name">{t("rpRestoreName")}</label>
            <input
              id="rpr-name"
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              autoComplete="off"
            />
          </div>
          <div className="form-group">
            <label htmlFor="rpr-svm">{t("rpRestoreSvm")}</label>
            <select id="rpr-svm" value={svm} onChange={(e) => setSvm(e.target.value)}>
              {allowedSvmIds.length === 0 && <option value="">—</option>}
              {allowedSvmIds.map((id) => (
                <option key={id} value={id}>
                  {id}
                </option>
              ))}
            </select>
          </div>
          <div className="form-group">
            <label htmlFor="rpr-junction">{t("rpRestoreJunctionPath")}</label>
            <input
              id="rpr-junction"
              type="text"
              value={junctionPath}
              onChange={(e) => setJunctionPath(e.target.value)}
              autoComplete="off"
            />
          </div>
          <div className="form-group">
            <label htmlFor="rpr-size">{t("rpRestoreSizeMb")}</label>
            <input
              id="rpr-size"
              type="number"
              min={1}
              value={sizeMb}
              onChange={(e) => setSizeMb(e.target.value)}
            />
          </div>
          <div className="form-group">
            <label className="slc-checkbox">
              <input
                type="checkbox"
                checked={storageEfficiency}
                onChange={(e) => setStorageEfficiency(e.target.checked)}
              />
              <span>{t("rpRestoreStorageEfficiency")}</span>
            </label>
          </div>
          <div className="form-group">
            <label htmlFor="rpr-tiering">{t("rpRestoreTiering")}</label>
            <select id="rpr-tiering" value={tiering} onChange={(e) => setTiering(e.target.value)}>
              {tieringPolicies.map((policy) => (
                <option key={policy} value={policy}>
                  {policy}
                </option>
              ))}
            </select>
          </div>
        </div>

        <div className="slc-gate">
          <label className="slc-checkbox">
            <input
              type="checkbox"
              checked={acknowledged}
              onChange={(e) => setAcknowledged(e.target.checked)}
            />
            <span>{t("rpRestoreAck")}</span>
          </label>
        </div>

        <div className="slc-actions">
          <button type="button" className="btn-secondary" onClick={onCancel}>
            {t("rpRestoreCancel")}
          </button>
          <button type="button" className="slc-proceed" disabled={!ready} onClick={submit}>
            {t("rpRestoreConfirm")}
          </button>
        </div>
      </div>
    </div>
  );
}
