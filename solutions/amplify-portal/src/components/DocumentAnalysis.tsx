import { useState } from "react";
import { generateClient } from "aws-amplify/data";
import type { Schema } from "../../amplify/data/resource";
import { useTranslation } from "../i18n";

const client = generateClient<Schema>();

interface DocumentAnalysisProps {
  fileKey: string;
  fileName: string;
  /**
   * Whether the file is in a regulated folder. Textract and Comprehend send the
   * document contents to a managed service, which is the same boundary the
   * folder guard exists to hold, so the controls are refused rather than hidden.
   */
  blocked?: boolean;
}

interface ExtractResult {
  text: string;
  blockCount: number;
  pageCount: number;
}

/** Comprehend returns a different shape per analysis type, so it stays JSON. */
type AnalyzeResult = Record<string, unknown>;

const ANALYSIS_TYPES = [
  { value: "entities", labelKey: "docAnalysisEntities" },
  { value: "sentiment", labelKey: "docAnalysisSentiment" },
  { value: "pii", labelKey: "docAnalysisPii" },
  { value: "keyphrases", labelKey: "docAnalysisKeyPhrases" },
] as const;

/**
 * Textract text extraction and Comprehend analysis for one document.
 *
 * Both were reachable in the schema and deployed as Lambdas with no caller.
 * They are the document counterpart of the label detection already offered on
 * images: a scanned PDF has no text layer for the chat to read, so extracting
 * it first is what makes the rest of the AI panel work on that file.
 */
export function DocumentAnalysis({ fileKey, fileName, blocked = false }: DocumentAnalysisProps) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const [extract, setExtract] = useState<ExtractResult | null>(null);
  const [analysis, setAnalysis] = useState<AnalyzeResult | null>(null);
  const [analysisType, setAnalysisType] = useState<string>("entities");
  const [busy, setBusy] = useState<"extract" | "analyze" | null>(null);
  const [error, setError] = useState<string | null>(null);

  const runExtract = async () => {
    setBusy("extract");
    setError(null);
    try {
      const response = await client.mutations.extractText({ key: fileKey, mode: "text" });
      if (response.data?.error) {
        setError(response.data.error);
      } else {
        setExtract({
          text: response.data?.text ?? "",
          blockCount: response.data?.blockCount ?? 0,
          pageCount: response.data?.pageCount ?? 0,
        });
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : t("docAnalysisExtractFailed"));
    } finally {
      setBusy(null);
    }
  };

  const runAnalyze = async () => {
    setBusy("analyze");
    setError(null);
    try {
      const response = await client.mutations.analyzeText({ key: fileKey, analysisType });
      if (response.data?.error) {
        setError(response.data.error);
      } else {
        const raw = response.data?.results;
        const parsed =
          typeof raw === "string" ? (JSON.parse(raw) as AnalyzeResult) : (raw as AnalyzeResult);
        setAnalysis(parsed ?? null);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : t("docAnalysisAnalyzeFailed"));
    } finally {
      setBusy(null);
    }
  };

  return (
    <div className="doc-analysis">
      <button
        className="doc-analysis-toggle"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
      >
        🔎 {open ? t("docAnalysisHide") : t("docAnalysisShow")}
      </button>

      {open && (
        <div className="doc-analysis-panel">
          {blocked ? (
            // Same boundary as the rest of the AI features: the guard is about
            // where the bytes go, and these two send them to Textract and
            // Comprehend.
            <p className="fl-warning">🚫 {t("aiPhiBlocked")}</p>
          ) : (
            <>
              <p className="rm-hint">{t("docAnalysisHint")}</p>

              <div className="doc-analysis-actions">
                <button
                  className="rm-btn-primary"
                  onClick={() => void runExtract()}
                  disabled={busy !== null}
                >
                  {busy === "extract" ? t("loading") : t("docAnalysisExtract")}
                </button>

                <select
                  value={analysisType}
                  onChange={(e) => setAnalysisType(e.target.value)}
                  aria-label={t("docAnalysisType")}
                  disabled={busy !== null}
                >
                  {ANALYSIS_TYPES.map((a) => (
                    <option key={a.value} value={a.value}>
                      {t(a.labelKey)}
                    </option>
                  ))}
                </select>
                <button
                  className="rm-btn-primary"
                  onClick={() => void runAnalyze()}
                  disabled={busy !== null}
                >
                  {busy === "analyze" ? t("loading") : t("docAnalysisAnalyze")}
                </button>
              </div>

              {error && <div className="error-message">{error}</div>}

              {extract && (
                <div className="doc-analysis-result">
                  <h5>{t("docAnalysisExtractedText")}</h5>
                  {/* Page and block counts are what tell a reader whether Textract
                      saw the whole document or only its first page. */}
                  <p className="rm-hint">
                    {t("docAnalysisPages")}: {extract.pageCount} · {t("docAnalysisBlocks")}:{" "}
                    {extract.blockCount}
                  </p>
                  {extract.text ? (
                    <textarea
                      readOnly
                      rows={10}
                      value={extract.text}
                      aria-label={t("docAnalysisExtractedText")}
                    />
                  ) : (
                    <p className="rm-empty-sm">{t("docAnalysisNoText")}</p>
                  )}
                </div>
              )}

              {analysis && (
                <div className="doc-analysis-result">
                  <h5>{t("docAnalysisResults")}</h5>
                  {/* Comprehend's shape differs per analysis type, so it is shown
                      as returned rather than flattened into a table that would
                      only fit one of them. */}
                  <pre className="doc-analysis-json">{JSON.stringify(analysis, null, 2)}</pre>
                </div>
              )}
            </>
          )}
          <p className="rm-hint doc-analysis-file" title={fileKey}>
            {fileName}
          </p>
        </div>
      )}
    </div>
  );
}
