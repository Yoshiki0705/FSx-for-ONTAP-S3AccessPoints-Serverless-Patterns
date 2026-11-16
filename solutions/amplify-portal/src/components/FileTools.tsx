/**
 * Tools section: translate, proofread and diagram a file (or typed text), extract a web
 * page, generate an image into a folder, run code on a file in a sandbox, and saved use cases.
 *
 * The file is the one selected in All Files. The server reads it within the caller's
 * access (functions/file-tools), so this component never sends file content itself, only
 * the key. Writes (saving into a folder, saving or deleting a use case) go through
 * `toolsMutation`, which AppSync limits to the write roles when roles are enforced.
 */
import { useCallback, useEffect, useId, useState } from "react";
import { generateClient } from "aws-amplify/data";
import type { Schema } from "../../amplify/data/resource";
import { useTranslation } from "../i18n";
import type { TranslationKeys } from "../i18n";
import { Icon, type IconName } from "./Icon";

const client = generateClient<Schema>();

export type ToolTab = "translate" | "proofread" | "diagram" | "webExtract" | "image" | "code" | "minutes" | "video" | "videoGen" | "useCases";

interface ToolsConfig {
  tools: { webExtract: boolean; image: boolean; useCases: boolean; code?: boolean; minutes?: boolean; video?: boolean; videoGeneration?: boolean };
  image: { region: string; modelId: string; crossRegion: boolean } | null;
  code?: { maxRuns: number; runSeconds: number; totalSeconds: number } | null;
  videoGeneration?: { region: string; modelId: string; crossRegion: boolean; aspectRatios: string[]; resolutions: string[]; maxPromptChars: number } | null;
  video?: { extensions: string[]; maxMegabytes: number; seconds: number } | null;
  minutes?: { languages: string[]; extensions: string[]; maxMegabytes: number; minSpeakers: number; maxSpeakers: number } | null;
}
interface CodeRun {
  ok: boolean;
  timedOut: boolean;
  seconds: number;
  stdout: string;
  stderr: string;
}

interface UseCase {
  useCaseId: string;
  title: string;
  description?: string;
  template: string;
}

const LANGUAGES = ["ja", "en", "ko", "zh-CN", "zh-TW", "fr", "de", "es", "pt", "it", "id", "th", "vi"] as const;
const DIAGRAMS = ["auto", "flowchart", "sequence", "class", "state", "er", "gantt", "mindmap", "timeline", "pie"] as const;
/** Transcribe language codes to the language names the translation tool already has. */
const MINUTES_LANGUAGE_NAMES: Record<string, string> = { "ja-JP": "ja", "en-US": "en", "ko-KR": "ko", "zh-CN": "zh-CN", "fr-FR": "fr", "de-DE": "de", "es-ES": "es" };
const POLL_MS = 5000;
const POLL_LIMIT = 360;
const ASPECTS = ["1:1", "16:9", "9:16", "3:2", "2:3", "4:5", "5:4"] as const;

function langKey(code: string): TranslationKeys {
  return `ftLanguages${code.split("-").map(capital).join("")}` as TranslationKeys;
}

function capital(s: string): string {
  return s.charAt(0).toUpperCase() + s.slice(1).toLowerCase();
}

/** Calls the tools Lambda through AppSync and unwraps `{success, error}`. */
/** Which endpoint a call goes through: see the comment on the schema's tools section. */
type Endpoint = "query" | "write" | "useCase";
async function callTool(action: string, params: Record<string, unknown>, endpoint: Endpoint = "query"): Promise<Record<string, unknown>> {
  const op =
    endpoint === "write"
      ? client.mutations.toolsMutation
      : endpoint === "useCase"
        ? client.mutations.toolsUseCaseMutation
        : client.queries.toolsQuery;
  const res = await op({ action, params: JSON.stringify(params) });
  if (res.errors?.length) throw new Error(res.errors[0].message);
  const data = (typeof res.data === "string" ? JSON.parse(res.data) : res.data) as Record<string, unknown> | null;
  if (!data || data.success !== true) throw new Error(String(data?.error || "the tool failed"));
  return data;
}

function download(name: string, content: string, type: string) {
  const url = URL.createObjectURL(new Blob([content], { type }));
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  a.click();
  URL.revokeObjectURL(url);
}

function Mermaid({ code, onSvg, errorLabel }: { code: string; onSvg: (svg: string) => void; errorLabel: string }) {
  const id = useId().replace(/[^a-zA-Z0-9]/g, "");
  const [svg, setSvg] = useState("");
  const [error, setError] = useState("");
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const mermaid = (await import("mermaid")).default;
        // "strict" encodes HTML in labels and disables click handlers; the server also
        // strips click lines and init directives before the code gets here.
        mermaid.initialize({ startOnLoad: false, securityLevel: "strict" });
        const out = await mermaid.render(`ft-mermaid-${id}`, code);
        if (!cancelled) {
          setSvg(out.svg);
          setError("");
          onSvg(out.svg);
        }
      } catch (e) {
        if (!cancelled) setError(e instanceof Error ? e.message : String(e));
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [code, id, onSvg]);
  if (error) return <div className="error-message">{errorLabel}: {error}</div>;
  // Mermaid's output with securityLevel "strict" (sanitized by its bundled DOMPurify).
  return <div className="ft-diagram" dangerouslySetInnerHTML={{ __html: svg }} />;
}

interface FileToolsProps {
  selectedFileKey: string | null;
  selectedFolder: string;
  canWrite: boolean;
  /** Save and delete use cases. Separate from canWrite: viewers may, see usePortalRole. */
  canSaveUseCases: boolean;
  initialTab?: ToolTab;
}

export function FileTools({ selectedFileKey, selectedFolder, canWrite, canSaveUseCases, initialTab }: FileToolsProps) {
  const { t } = useTranslation();
  const [config, setConfig] = useState<ToolsConfig | null>(null);
  const [tab, setTab] = useState<ToolTab>(initialTab || "translate");
  const [useFile, setUseFile] = useState(!!selectedFileKey);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [folder, setFolder] = useState(selectedFolder);

  // Translate / proofread / diagram / web
  const [target, setTarget] = useState("en");
  const [style, setStyle] = useState("as-is");
  const [note, setNote] = useState("");
  const [diagramType, setDiagramType] = useState("auto");
  const [url, setUrl] = useState("");
  const [task, setTask] = useState("summary");
  const [question, setQuestion] = useState("");
  const [result, setResult] = useState<Record<string, unknown> | null>(null);
  const [svg, setSvg] = useState("");
  // Image
  const [prompt, setPrompt] = useState("");
  const [negative, setNegative] = useState("");
  const [aspect, setAspect] = useState("1:1");
  const [fileName, setFileName] = useState("generated-image");
  // Code execution
  const [codeTask, setCodeTask] = useState("");
  // Minutes
  const [minLanguage, setMinLanguage] = useState("ja-JP");
  const [minSpeakers, setMinSpeakers] = useState(2);
  // A job running in the background: which status action to ask, and what to say if it fails.
  const [poll, setPoll] = useState<{ action: string; params: Record<string, unknown>; failed: TranslationKeys } | null>(null);
  // Video generation
  const [genPrompt, setGenPrompt] = useState("");
  const [genAspect, setGenAspect] = useState("16:9");
  const [genResolution, setGenResolution] = useState("540p");
  // Video analysis
  const [videoTask, setVideoTask] = useState("");
  // Use cases
  const [useCases, setUseCases] = useState<UseCase[]>([]);
  const [editing, setEditing] = useState<Partial<UseCase> | null>(null);
  const [active, setActive] = useState<UseCase | null>(null);

  // Follow the props when they change (a new file or folder selected, a shortcut from the
  // AI panel), without an effect: React's "adjust state when a prop changes" pattern.
  const [seen, setSeen] = useState({ initialTab, selectedFileKey, selectedFolder });
  if (seen.initialTab !== initialTab || seen.selectedFileKey !== selectedFileKey || seen.selectedFolder !== selectedFolder) {
    setSeen({ initialTab, selectedFileKey, selectedFolder });
    if (seen.initialTab !== initialTab) setTab(initialTab || "translate");
    if (seen.selectedFileKey !== selectedFileKey) setUseFile(!!selectedFileKey);
    if (seen.selectedFolder !== selectedFolder) setFolder(selectedFolder);
  }

  useEffect(() => {
    callTool("config", {}).then((d) => setConfig(d as unknown as ToolsConfig)).catch(() => {});
  }, []);

  const loadUseCases = useCallback(() => {
    callTool("listUseCases", {}).then((d) => setUseCases((d.useCases as UseCase[]) || [])).catch(() => {});
  }, []);
  useEffect(() => {
    if (tab === "useCases") loadUseCases();
  }, [tab, loadUseCases]);

  // While a background job runs, ask for its state every 5 s. The job lives in Amazon Transcribe
  // (minutes) or in a bucket (video), so a reload loses only the screen's handle on it.
  useEffect(() => {
    if (!poll) return;
    let polls = 0;
    let stopped = false;
    const timer = setInterval(async () => {
      polls += 1;
      try {
        const out = await callTool(poll.action, poll.params);
        if (stopped) return;
        if (out.status === "COMPLETED") {
          setResult(out);
          setPoll(null);
        } else if (out.status === "FAILED") {
          setError(t(poll.failed).replace("{reason}", String(out.reason || "")));
          setPoll(null);
        } else if (polls >= POLL_LIMIT) {
          setError(t("ftMinutesTimeout"));
          setPoll(null);
        }
      } catch (e) {
        if (stopped) return;
        setError(e instanceof Error ? e.message : String(e));
        setPoll(null);
      }
    }, POLL_MS);
    return () => {
      stopped = true;
      clearInterval(timer);
    };
  }, [poll, t]);
  const run = async (fn: () => Promise<void>) => {
    setBusy(true);
    setError("");
    setNotice("");
    try {
      await fn();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  const input = () => (useFile && selectedFileKey ? { key: selectedFileKey } : { text });
  const baseName = (selectedFileKey || "result").split("/").pop() || "result";

  const save = (content: string, format: "markdown" | "mermaid", name: string) =>
    run(async () => {
      const out = await callTool("saveResult", { folder, fileName: name, content, format }, "write");
      setNotice(t("ftSaved").replace("{key}", String(out.key)));
    });

  const tabs: { id: ToolTab; icon: IconName; label: TranslationKeys; show: boolean }[] = [
    { id: "translate", icon: "globe", label: "ftTabsTranslate", show: true },
    { id: "proofread", icon: "pencil", label: "ftTabsProofread", show: true },
    { id: "diagram", icon: "git-branch", label: "ftTabsDiagram", show: true },
    { id: "webExtract", icon: "link", label: "ftTabsWebextract", show: config?.tools.webExtract ?? true },
    { id: "image", icon: "image", label: "ftTabsImage", show: config?.tools.image ?? false },
    { id: "code", icon: "wrench", label: "ftTabsCode", show: config?.tools.code ?? false },
    { id: "minutes", icon: "users", label: "ftTabsMinutes", show: config?.tools.minutes ?? false },
    { id: "video", icon: "eye", label: "ftTabsVideo", show: config?.tools.video ?? false },
    { id: "videoGen", icon: "image", label: "ftTabsVideogen", show: config?.tools.videoGeneration ?? false },
    { id: "useCases", icon: "sparkles", label: "ftTabsUsecases", show: config?.tools.useCases ?? true },
  ];
  const current = tabs.some((x) => x.id === tab && x.show) ? tab : "translate";

  const inputBlock = (
    <div className="form-group">
      <div className="ft-source" role="radiogroup" aria-label={t("ftSourceLabel")}>
        <label>
          <input type="radio" checked={useFile} disabled={!selectedFileKey} onChange={() => setUseFile(true)} /> {t("ftSourceFile")}
        </label>
        <label>
          <input type="radio" checked={!useFile} onChange={() => setUseFile(false)} /> {t("ftSourceText")}
        </label>
      </div>
      {useFile && selectedFileKey ? (
        <>
          <div className="ft-file"><Icon name="file-text" className="icon-lead" />{selectedFileKey}</div>
          <small>{t("ftFileNote")}</small>
        </>
      ) : (
        <>
          {!selectedFileKey && <small>{t("ftNoFile")}</small>}
          <textarea rows={8} value={text} onChange={(e) => setText(e.target.value)} placeholder={t("ftSourceTextplaceholder")} aria-label={t("ftSourceText")} />
        </>
      )}
    </div>
  );
  const hasInput = (useFile && !!selectedFileKey) || !!text.trim();

  const folderBlock = canWrite ? (
    <div className="form-group">
      <label htmlFor="ft-folder">{t("ftSaveFolder")}</label>
      <input id="ft-folder" value={folder} onChange={(e) => setFolder(e.target.value)} />
    </div>
  ) : (
    <small>{t("ftNoWrite")}</small>
  );

  const textResult = (content: string, name: string, format: "markdown" | "mermaid" = "markdown") => (
    <div className="ft-result">
      <div className="ft-actions">
        <button type="button" className="btn-secondary btn-sm" onClick={() => navigator.clipboard.writeText(content)}>
          <Icon name="copy" className="icon-lead" />{t("ftCopy")}
        </button>
        <button type="button" className="btn-secondary btn-sm" onClick={() => download(name, content, "text/plain")}>
          <Icon name="download" className="icon-lead" />{t("ftDownload")}
        </button>
        {canWrite && (
          <button type="button" className="btn-secondary btn-sm" disabled={busy} onClick={() => save(content, format, name)}>
            <Icon name="folder-plus" className="icon-lead" />{t("ftSaveToFolder")}
          </button>
        )}
      </div>
      {format === "markdown" && <pre className="ft-pre">{content}</pre>}
    </div>
  );

  return (
    <div className="file-tools">
      <h2>{t("ftTitle")}</h2>
      <p className="rm-hint">{t("ftSubtitle")}</p>
      <div className="ft-tabs" role="tablist" aria-label={t("ftTitle")}>
        {tabs.filter((x) => x.show).map((x) => (
          <button key={x.id} type="button" role="tab" aria-selected={current === x.id} className={`ft-tab ${current === x.id ? "active" : ""}`} onClick={() => { setTab(x.id); setResult(null); setError(""); setNotice(""); }}>
            <Icon name={x.icon} className="icon-lead" />{t(x.label)}
          </button>
        ))}
      </div>
      {error && <div className="error-message" role="alert">{error}</div>}
      {notice && <div className="success-message">{notice}</div>}

      {current === "translate" && (
        <section role="tabpanel">
          {inputBlock}
          <div className="ft-row">
            <div className="form-group">
              <label htmlFor="ft-target">{t("ftTranslateTarget")}</label>
              <select id="ft-target" value={target} onChange={(e) => setTarget(e.target.value)}>
                {LANGUAGES.map((l) => <option key={l} value={l}>{t(langKey(l))}</option>)}
              </select>
            </div>
            <div className="form-group">
              <label htmlFor="ft-style">{t("ftTranslateStyle")}</label>
              <select id="ft-style" value={style} onChange={(e) => setStyle(e.target.value)}>
                <option value="as-is">{t("ftTranslateStylesAsIs")}</option>
                <option value="formal">{t("ftTranslateStylesFormal")}</option>
                <option value="casual">{t("ftTranslateStylesCasual")}</option>
              </select>
            </div>
            <div className="form-group">
              <label htmlFor="ft-note">{t("ftTranslateNote")}</label>
              <input id="ft-note" value={note} onChange={(e) => setNote(e.target.value)} placeholder={t("ftTranslateNoteplaceholder")} />
            </div>
          </div>
          <button type="button" className="btn-primary" disabled={busy || !hasInput} onClick={() => run(async () => setResult(await callTool("translate", { ...input(), target, style, note })))}>
            <Icon name="globe" className="icon-lead" />{busy ? t("ftRunning") : t("ftTranslateRun")}
          </button>
          {result && typeof result.result === "string" && (<>{folderBlock}{textResult(result.result, `${baseName}.${target}.md`)}</>)}
        </section>
      )}

      {current === "proofread" && (
        <section role="tabpanel">
          {inputBlock}
          <button type="button" className="btn-primary" disabled={busy || !hasInput} onClick={() => run(async () => setResult(await callTool("proofread", input())))}>
            <Icon name="pencil" className="icon-lead" />{busy ? t("ftRunning") : t("ftProofreadRun")}
          </button>
          {result && Array.isArray(result.issues) && (
            <div className="ft-result">
              <h3>{t("ftProofreadIssues").replace("{count}", String(result.issues.length))}</h3>
              {result.issues.length === 0 ? <p>{t("ftProofreadNoissues")}</p> : (
                <table className="ft-table">
                  <thead><tr><th>{t("ftProofreadOriginal")}</th><th>{t("ftProofreadSuggestion")}</th><th>{t("ftProofreadReason")}</th></tr></thead>
                  <tbody>
                    {(result.issues as { original: string; suggestion: string; reason: string }[]).map((i, n) => (
                      <tr key={n}><td><del>{i.original}</del></td><td>{i.suggestion}</td><td>{i.reason}</td></tr>
                    ))}
                  </tbody>
                </table>
              )}
              <h3>{t("ftProofreadCorrected")}</h3>
              {folderBlock}
              {textResult(String(result.corrected || ""), `${baseName}.proofread.md`)}
            </div>
          )}
        </section>
      )}

      {current === "diagram" && (
        <section role="tabpanel">
          {inputBlock}
          <div className="form-group">
            <label htmlFor="ft-diagram">{t("ftDiagramType")}</label>
            <select id="ft-diagram" value={diagramType} onChange={(e) => setDiagramType(e.target.value)}>
              {DIAGRAMS.map((d) => <option key={d} value={d}>{t(`ftDiagramTypes${capital(d)}` as TranslationKeys)}</option>)}
            </select>
          </div>
          <button type="button" className="btn-primary" disabled={busy || !hasInput} onClick={() => run(async () => { setSvg(""); setResult(await callTool("diagram", { ...input(), type: diagramType })); })}>
            <Icon name="git-branch" className="icon-lead" />{busy ? t("ftRunning") : t("ftDiagramRun")}
          </button>
          {result && typeof result.mermaid === "string" && (
            <div className="ft-result">
              <Mermaid code={result.mermaid} onSvg={setSvg} errorLabel={t("ftDiagramRendererror")} />
              <div className="ft-actions">
                <button type="button" className="btn-secondary btn-sm" disabled={!svg} onClick={() => download(`${baseName}.svg`, svg, "image/svg+xml")}>
                  <Icon name="download" className="icon-lead" />{t("ftDiagramDownloadsvg")}
                </button>
              </div>
              {folderBlock}
              {textResult(result.mermaid, `${baseName}.mmd`, "mermaid")}
              <details><summary>{t("ftDiagramCode")}</summary><pre className="ft-pre">{result.mermaid}</pre></details>
            </div>
          )}
        </section>
      )}

      {current === "webExtract" && (
        <section role="tabpanel">
          <div className="form-group">
            <label htmlFor="ft-url">{t("ftWebextractUrl")}</label>
            <input id="ft-url" type="url" value={url} onChange={(e) => setUrl(e.target.value)} placeholder="https://" />
            <small>{t("ftWebextractNote")}</small>
          </div>
          <div className="ft-row">
            <div className="form-group">
              <label htmlFor="ft-task">{t("ftWebextractTask")}</label>
              <select id="ft-task" value={task} onChange={(e) => setTask(e.target.value)}>
                <option value="summary">{t("ftWebextractTasksSummary")}</option>
                <option value="extract">{t("ftWebextractTasksExtract")}</option>
                <option value="question">{t("ftWebextractTasksQuestion")}</option>
              </select>
            </div>
            {task === "question" && (
              <div className="form-group">
                <label htmlFor="ft-question">{t("ftWebextractQuestion")}</label>
                <input id="ft-question" value={question} onChange={(e) => setQuestion(e.target.value)} />
              </div>
            )}
          </div>
          <button type="button" className="btn-primary" disabled={busy || !url.trim()} onClick={() => run(async () => setResult(await callTool("webExtract", { url, task, question, language: document.documentElement.lang || "ja" })))}>
            <Icon name="link" className="icon-lead" />{busy ? t("ftRunning") : t("ftWebextractRun")}
          </button>
          {result && typeof result.result === "string" && (
            <>
              <p className="rm-hint">{result.title ? `${result.title} · ` : ""}{String(result.url)}{result.truncated ? ` (${t("ftWebextractTruncated")})` : ""}</p>
              {folderBlock}
              {textResult(result.result, "web-extract.md")}
            </>
          )}
        </section>
      )}

      {current === "image" && config?.image && (
        <section role="tabpanel">
          <div className="ft-notice" role="note">
            {(config.image.crossRegion ? t("ftImageRegionnotice") : t("ftImageInregion")).replace("{region}", config.image.region)}
            <small>{t("ftImageModel").replace("{model}", config.image.modelId)}</small>
          </div>
          <div className="form-group">
            <label htmlFor="ft-prompt">{t("ftImagePrompt")}</label>
            <textarea id="ft-prompt" rows={4} value={prompt} onChange={(e) => setPrompt(e.target.value)} placeholder={t("ftImagePromptplaceholder")} />
          </div>
          <div className="ft-row">
            <div className="form-group">
              <label htmlFor="ft-negative">{t("ftImageNegative")}</label>
              <input id="ft-negative" value={negative} onChange={(e) => setNegative(e.target.value)} />
            </div>
            <div className="form-group">
              <label htmlFor="ft-aspect">{t("ftImageAspect")}</label>
              <select id="ft-aspect" value={aspect} onChange={(e) => setAspect(e.target.value)}>
                {ASPECTS.map((a) => <option key={a} value={a}>{a}</option>)}
              </select>
            </div>
          </div>
          {canWrite ? (
            <>
              <div className="ft-row">
                <div className="form-group">
                  <label htmlFor="ft-folder-img">{t("ftSaveFolder")}</label>
                  <input id="ft-folder-img" value={folder} onChange={(e) => setFolder(e.target.value)} />
                </div>
                <div className="form-group">
                  <label htmlFor="ft-name">{t("ftFileName")}</label>
                  <input id="ft-name" value={fileName} onChange={(e) => setFileName(e.target.value)} />
                </div>
              </div>
              <small>{t("ftImageSavedTo")}</small>
              <button type="button" className="btn-primary" disabled={busy || !prompt.trim()} onClick={() => run(async () => {
                const out = await callTool("generateImage", { prompt, negativePrompt: negative, aspectRatio: aspect, folder, fileName }, "write");
                setResult(out);
                setNotice(t("ftSaved").replace("{key}", String(out.key)));
              })}>
                <Icon name="image" className="icon-lead" />{busy ? t("ftRunning") : t("ftImageRun")}
              </button>
            </>
          ) : <small>{t("ftNoWrite")}</small>}
          {result && typeof result.imageBase64 === "string" && (
            <img className="ft-image" src={`data:image/png;base64,${result.imageBase64}`} alt={prompt} />
          )}
        </section>
      )}

      {current === "code" && config?.code && (
        <section role="tabpanel">
          <div className="ft-notice" role="note">
            {t("ftCodeEnv")}
            <small>
              {t("ftCodeLimits")
                .replace("{runs}", String(config.code.maxRuns))
                .replace("{seconds}", String(config.code.runSeconds))
                .replace("{total}", String(config.code.totalSeconds))}
            </small>
          </div>
          {inputBlock}
          <div className="form-group">
            <label htmlFor="ft-code-task">{t("ftCodeTask")}</label>
            <textarea id="ft-code-task" rows={3} value={codeTask} onChange={(e) => setCodeTask(e.target.value)} placeholder={t("ftCodeTaskplaceholder")} />
          </div>
          <button type="button" className="btn-primary" disabled={busy || !hasInput || !codeTask.trim()} onClick={() => run(async () => setResult(await callTool("code", { ...input(), task: codeTask })))}>
            <Icon name="wrench" className="icon-lead" />{busy ? t("ftRunning") : t("ftCodeRun")}
          </button>
          {result && Array.isArray(result.runs) && (
            <div className="ft-result">
              {result.completed === true && typeof result.result === "string" ? (
                <>
                  <h3>{t("ftCodeAnswer")}</h3>
                  {folderBlock}
                  {textResult(result.result, `${baseName}.analysis.md`)}
                </>
              ) : (
                <div className="error-message" role="alert">
                  {t(result.reason === "timeout" ? "ftCodeTimeout" : result.reason === "no_time" ? "ftCodeNotime" : "ftCodeFailed")}
                </div>
              )}
              {typeof result.code === "string" && result.code && (
                <details><summary>{t("ftCodeProgram")}</summary><pre className="ft-pre">{result.code}</pre></details>
              )}
              {(result.runs as CodeRun[]).length > 0 && (
                <details>
                  <summary>{t("ftCodeRuns")}</summary>
                  <ul>
                    {(result.runs as CodeRun[]).map((r, n) => (
                      <li key={n}>
                        <strong>{t("ftCodeRunN").replace("{n}", String(n + 1))}</strong>{" "}
                        {r.timedOut ? t("ftCodeRunTimeout") : r.ok ? t("ftCodeRunOk") : t("ftCodeRunFailed")} ({r.seconds}s)
                        {r.stdout && (<><small>{t("ftCodeStdout")}</small><pre className="ft-pre">{r.stdout}</pre></>)}
                        {r.stderr && (<><small>{t("ftCodeStderr")}</small><pre className="ft-pre">{r.stderr}</pre></>)}
                      </li>
                    ))}
                  </ul>
                </details>
              )}
            </div>
          )}
        </section>
      )}
      {current === "minutes" && config?.minutes && (
        <section role="tabpanel">
          <div className="ft-notice" role="note">
            {t("ftMinutesNote").replace("{mb}", String(config.minutes.maxMegabytes))}
            <small>{config.minutes.extensions.join(", ")}</small>
          </div>
          {selectedFileKey ? (
            <div className="ft-file"><Icon name="file-text" className="icon-lead" />{selectedFileKey}</div>
          ) : (
            <small>{t("ftMinutesNofile")}</small>
          )}
          <div className="ft-row">
            <div className="form-group">
              <label htmlFor="ft-min-language">{t("ftMinutesLanguage")}</label>
              <select id="ft-min-language" value={minLanguage} onChange={(e) => setMinLanguage(e.target.value)}>
                {config.minutes.languages.map((l) => <option key={l} value={l}>{t(langKey(MINUTES_LANGUAGE_NAMES[l] || "en"))}</option>)}
              </select>
            </div>
            <div className="form-group">
              <label htmlFor="ft-min-speakers">{t("ftMinutesSpeakers")}</label>
              <input id="ft-min-speakers" type="number" min={config.minutes.minSpeakers} max={config.minutes.maxSpeakers} value={minSpeakers} onChange={(e) => setMinSpeakers(Number(e.target.value))} />
            </div>
          </div>
          <button type="button" className="btn-primary" disabled={busy || !!poll || !selectedFileKey} onClick={() => run(async () => {
            setResult(null);
            const out = await callTool("minutes-start", { key: selectedFileKey, language: minLanguage, speakers: minSpeakers });
            setPoll({ action: "minutes-status", params: { jobName: String(out.jobName) }, failed: "ftMinutesFailed" });
          })}>
            <Icon name="users" className="icon-lead" />{busy || poll ? t("ftRunning") : t("ftMinutesRun")}
          </button>
          {poll?.action === "minutes-status" && <p className="rm-hint" role="status">{t("ftMinutesWorking")}</p>}
          {result && typeof result.result === "string" && (
            <>
              {result.truncated === true && <p className="rm-hint">{t("ftMinutesTruncated")}</p>}
              {folderBlock}
              {textResult(result.result, `${baseName}.minutes.md`)}
            </>
          )}
        </section>
      )}
      {current === "video" && config?.video && (
        <section role="tabpanel">
          <div className="ft-notice" role="note">
            {t("ftVideoNoteSync").replace("{mb}", String(config.video.maxMegabytes)).replace("{seconds}", String(config.video.seconds))}
            <small>{config.video.extensions.join(", ")}</small>
            <small>{t("ftVideoNoaudio")}</small>
            <small>{t("ftVideoCaveat")}</small>
          </div>
          {selectedFileKey ? (
            <div className="ft-file"><Icon name="file-text" className="icon-lead" />{selectedFileKey}</div>
          ) : (
            <small>{t("ftVideoNofile")}</small>
          )}
          <div className="form-group">
            <label htmlFor="ft-video-task">{t("ftVideoTask")}</label>
            <textarea id="ft-video-task" rows={3} value={videoTask} onChange={(e) => setVideoTask(e.target.value)} placeholder={t("ftVideoTaskplaceholder")} />
          </div>
          <button type="button" className="btn-primary" disabled={busy || !selectedFileKey} onClick={() => run(async () => {
            setResult(null);
            setResult(await callTool("video", { key: selectedFileKey, task: videoTask.trim() || undefined, language: document.documentElement.lang || "ja" }));
          })}>
            <Icon name="eye" className="icon-lead" />{busy ? t("ftRunning") : t("ftVideoRun")}
          </button>
          {result && typeof result.result === "string" && (<>{folderBlock}{textResult(result.result, `${baseName}.video.md`)}</>)}
        </section>
      )}
      {current === "videoGen" && config?.videoGeneration && (
        <section role="tabpanel">
          <div className="ft-notice" role="note">
            {(config.videoGeneration.crossRegion ? t("ftVideoGenRegionnotice") : t("ftVideoGenInregion")).replace("{region}", config.videoGeneration.region)}
            <small>{t("ftVideoGenLimits")}</small>
            <small>{t("ftImageModel").replace("{model}", config.videoGeneration.modelId)}</small>
          </div>
          <div className="form-group">
            <label htmlFor="ft-gen-prompt">{t("ftVideoGenPrompt")}</label>
            <textarea id="ft-gen-prompt" rows={4} maxLength={config.videoGeneration.maxPromptChars} value={genPrompt} onChange={(e) => setGenPrompt(e.target.value)} placeholder={t("ftVideoGenPromptplaceholder")} />
          </div>
          <div className="ft-row">
            <div className="form-group">
              <label htmlFor="ft-gen-aspect">{t("ftImageAspect")}</label>
              <select id="ft-gen-aspect" value={genAspect} onChange={(e) => setGenAspect(e.target.value)}>
                {config.videoGeneration.aspectRatios.map((a) => <option key={a} value={a}>{a}</option>)}
              </select>
            </div>
            <div className="form-group">
              <label htmlFor="ft-gen-resolution">{t("ftVideoGenResolution")}</label>
              <select id="ft-gen-resolution" value={genResolution} onChange={(e) => setGenResolution(e.target.value)}>
                {config.videoGeneration.resolutions.map((r) => <option key={r} value={r}>{r}</option>)}
              </select>
            </div>
          </div>
          <button type="button" className="btn-primary" disabled={busy || !!poll || !genPrompt.trim()} onClick={() => run(async () => {
            setResult(null);
            const out = await callTool("video-generate-start", { prompt: genPrompt, aspectRatio: genAspect, resolution: genResolution });
            setPoll({ action: "video-generate-status", params: { invocationArn: String(out.invocationArn) }, failed: "ftVideoGenFailed" });
          })}>
            <Icon name="image" className="icon-lead" />{busy || poll ? t("ftRunning") : t("ftVideoGenRun")}
          </button>
          {poll?.action === "video-generate-status" && <p className="rm-hint" role="status">{t("ftVideoGenWorking")}</p>}
          {result && typeof result.url === "string" && (
            <div className="ft-result">
              <video className="ft-image" controls src={result.url} aria-label={genPrompt} />
              <div className="ft-actions">
                <a className="btn-secondary btn-sm" href={result.url} download="generated-video.mp4">
                  <Icon name="download" className="icon-lead" />{t("ftDownload")}
                </a>
              </div>
              <small>{t("ftVideoGenExpires")}</small>
            </div>
          )}
        </section>
      )}
      {current === "useCases" && (
        <section role="tabpanel">
          <p className="rm-hint">{t("ftUsecasesIntro")}</p>
          {canSaveUseCases ? (
            <button type="button" className="btn-primary" onClick={() => setEditing({ title: "", description: "", template: t("ftUsecasesTemplateexample") })}>{/* i18n-placeholder-checked: {{input}} is the template syntax the user types, shown as is */}
              <Icon name="plus" className="icon-lead" />{t("ftUsecasesNew")}
            </button>
          ) : <small>{t("ftUsecasesNoRole")}</small>}
          {editing && (
            <div className="ft-editor">
              <div className="form-group">
                <label htmlFor="ft-uc-title">{t("ftUsecasesTitle")}</label>
                <input id="ft-uc-title" value={editing.title || ""} onChange={(e) => setEditing({ ...editing, title: e.target.value })} />
              </div>
              <div className="form-group">
                <label htmlFor="ft-uc-desc">{t("ftUsecasesDescription")}</label>
                <input id="ft-uc-desc" value={editing.description || ""} onChange={(e) => setEditing({ ...editing, description: e.target.value })} />
              </div>
              <div className="form-group">
                <label htmlFor="ft-uc-template">{t("ftUsecasesTemplate")}</label>
                <textarea id="ft-uc-template" rows={6} value={editing.template || ""} onChange={(e) => setEditing({ ...editing, template: e.target.value })} />
                <small>{t("ftUsecasesTemplatehelp")}</small>{/* i18n-placeholder-checked: {{input}} is the template syntax, shown as is */}
              </div>
              <div className="ft-actions">
                <button type="button" className="btn-primary" disabled={busy} onClick={() => run(async () => { await callTool("saveUseCase", editing, "useCase"); setEditing(null); loadUseCases(); })}>{t("ftUsecasesSave")}</button>
                <button type="button" className="btn-secondary" onClick={() => setEditing(null)}>{t("ftUsecasesCancel")}</button>
              </div>
            </div>
          )}
          {useCases.length === 0 && !editing ? <p className="rm-hint">{t("ftUsecasesEmpty")}</p> : (
            <ul className="ft-usecases">
              {useCases.map((u) => (
                <li key={u.useCaseId}>
                  <div>
                    <strong>{u.title}</strong>
                    {u.description && <small>{u.description}</small>}
                  </div>
                  <div className="ft-actions">
                    <button type="button" className="btn-secondary btn-sm" aria-label={t("ftUsecasesRun")} onClick={() => { setActive(u); setResult(null); }}><Icon name="zap" /></button>
                    {canSaveUseCases && <button type="button" className="btn-secondary btn-sm" aria-label={t("ftUsecasesEdit")} onClick={() => setEditing(u)}><Icon name="pencil" /></button>}
                    {canSaveUseCases && <button type="button" className="btn-secondary btn-sm" aria-label={t("ftUsecasesDelete")} onClick={() => run(async () => { await callTool("deleteUseCase", { useCaseId: u.useCaseId }, "useCase"); if (active?.useCaseId === u.useCaseId) setActive(null); loadUseCases(); })}><Icon name="trash" /></button>}
                  </div>
                </li>
              ))}
            </ul>
          )}
          {active && (
            <div className="ft-editor">
              <h3>{active.title}</h3>
              {inputBlock}
              <button type="button" className="btn-primary" disabled={busy} onClick={() => run(async () => setResult(await callTool("runUseCase", { useCaseId: active.useCaseId, ...input() })))}>
                <Icon name="sparkles" className="icon-lead" />{busy ? t("ftRunning") : t("ftUsecasesRun")}
              </button>
              {result && typeof result.result === "string" && (<>{folderBlock}{textResult(result.result, `${active.title}.md`)}</>)}
            </div>
          )}
        </section>
      )}
    </div>
  );
}
