import { useQuery } from "@tanstack/react-query";
import { generateClient } from "aws-amplify/data";
import type { Schema } from "../../amplify/data/resource";
import { useTranslation } from "../i18n";

const client = generateClient<Schema>();

export interface AiMetadata {
  fileKey: string;
  classification?: string | null;
  rekognitionLabels?: number | null;
  comprehendEntities?: number | null;
  textractLength?: number | null;
  bedrockSummary?: string | null;
  processedAt?: string | null;
  pattern?: string | null;
}

/**
 * AI processing metadata for the files in one listing, keyed by file key.
 *
 * One batched call per folder rather than one per row: the handler takes up to
 * 100 keys, and a listing page is 100 files.
 *
 * The metadata table is optional. A deployment that has never run a processing
 * pattern has no table configured, in which case the handler says so and this
 * resolves to an empty map — no badges, no error surfaced to the user, because
 * "nothing has been processed" is a normal state rather than a failure.
 */
export function useAiMetadata(fileKeys: string[]) {
  return useQuery({
    // Sorted so two renders of the same page share a cache entry regardless of
    // the order the keys arrived in.
    queryKey: ["aiMetadata", [...fileKeys].sort().join("\u0000")],
    enabled: fileKeys.length > 0,
    queryFn: async () => {
      const response = await client.queries.getFileMetadata({ fileKeys });
      const raw = response.data?.metadata;
      const list = (typeof raw === "string" ? JSON.parse(raw) : raw) as AiMetadata[] | null;
      const byKey = new Map<string, AiMetadata>();
      for (const entry of list ?? []) {
        if (entry?.fileKey) byKey.set(entry.fileKey, entry);
      }
      return byKey;
    },
  });
}

/** Classifications that warrant a warning colour rather than a neutral one. */
const SENSITIVE = new Set(["CONFIDENTIAL", "RESTRICTED", "CUI", "PHI", "PII"]);

interface AiMetadataBadgesProps {
  metadata?: AiMetadata;
}

/**
 * Inline badges summarising what AI processing found in a file.
 *
 * Deliberately counts and labels rather than content: the listing is a place to
 * notice that a file was classified CONFIDENTIAL, not a place to read its
 * summary. The summary is offered as the badge's tooltip.
 */
export function AiMetadataBadges({ metadata }: AiMetadataBadgesProps) {
  const { t } = useTranslation();
  if (!metadata) return null;

  const { classification, rekognitionLabels, comprehendEntities, textractLength, bedrockSummary } =
    metadata;

  const hasAny =
    classification || rekognitionLabels || comprehendEntities || textractLength || bedrockSummary;
  if (!hasAny) return null;

  return (
    <span className="ai-meta-badges">
      {classification && (
        <span
          className={`ai-meta-badge ${
            SENSITIVE.has(classification.toUpperCase()) ? "sensitive" : ""
          }`}
          title={t("aiMetaClassification")}
        >
          {classification}
        </span>
      )}
      {!!rekognitionLabels && (
        <span className="ai-meta-badge" title={t("aiMetaLabels")}>
          🏞 {rekognitionLabels}
        </span>
      )}
      {!!comprehendEntities && (
        <span className="ai-meta-badge" title={t("aiMetaEntities")}>
          🔤 {comprehendEntities}
        </span>
      )}
      {!!textractLength && (
        <span className="ai-meta-badge" title={t("aiMetaTextLength")}>
          📝 {textractLength.toLocaleString()}
        </span>
      )}
      {bedrockSummary && (
        <span className="ai-meta-badge" title={bedrockSummary}>
          ✨ {t("aiMetaSummary")}
        </span>
      )}
    </span>
  );
}
