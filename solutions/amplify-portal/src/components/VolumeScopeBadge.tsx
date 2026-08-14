import { useTranslation } from "../i18n";

interface VolumeScopeBadgeProps {
  /** The volume the panel's figures describe, as the response named it. */
  volumeName: string;
  /**
   * True when nothing has been picked yet, so this is the volume the deployment is
   * configured with rather than a choice the reader made.
   */
  isDefault: boolean;
}

/**
 * Which volume the panel on screen is describing.
 *
 * It was a 12px pill beside the heading, reading `Volume: vol1` in pale blue. Every
 * part of that worked against it: smaller than body text, lighter than body text, and
 * shaped like the decorative badges elsewhere in the page. Before picking anything from
 * the dropdown a reader could not tell what `vol1` was -- their selection, a filter, or
 * something the page had decided on its own.
 *
 * So it is now the size of body text, the name is set in the monospace face used for
 * identifiers throughout the portal, and the unpicked case says `default` in words
 * instead of leaving it to be inferred. That last part is the actual question being
 * answered: not "which volume" but "why this one".
 *
 * One component rather than the same markup in three panels, because the three had
 * already drifted -- one of them carried a tooltip the other two did not.
 */
export function VolumeScopeBadge({ volumeName, isDefault }: VolumeScopeBadgeProps) {
  const { t } = useTranslation();
  if (!volumeName) return null;

  return (
    <span
      className={`volume-badge${isDefault ? " volume-badge-default" : ""}`}
      title={isDefault ? t("volumeScopeDefaultTitle") : t("volumeScopeSelectedTitle")}
    >
      <span className="volume-badge-label">{t("volumeScopeLabel")}</span>
      <span className="volume-badge-name">{volumeName}</span>
      {isDefault && <span className="volume-badge-origin">{t("volumeScopeDefault")}</span>}
    </span>
  );
}
