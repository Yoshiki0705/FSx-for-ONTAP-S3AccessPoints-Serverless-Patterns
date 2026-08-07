/**
 * AiSettingsManager — Admin panel for AI Agent / Knowledge Base feature enablement.
 *
 * Architecture integration:
 *   - AI Agent (Bedrock Converse + tool_use): No KB dependency → instant enable
 *   - Semantic Search (Bedrock KB Retrieve): Requires KB infrastructure
 *     → KB deployed separately via RAG-FSxN-CDK or Bedrock Console
 *     → KB ID configured in portal-config.ts → bedrockKbId
 *     → Portal Lambda calls bedrock:Retrieve using that KB ID
 *
 * Cost model:
 *   - AI Agent: ~$0.001/request (Bedrock Converse, pay-per-use)
 *   - Semantic Search (S3 Vectors backend): ~$1-10/month
 *   - Semantic Search (OpenSearch Serverless): ~$700/month (2 OCU minimum)
 */
import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "../../i18n";
import { adminMutate, dispatch } from "../../lib/dispatch";
import { errorMessage, unwrap } from "../../lib/portalQuery";

/**
 * The settings this panel can change.
 *
 * Every key here has a consumer: `aiAgentEnabled` and `aiSearchEnabled` gate their
 * sections in `App.tsx`, and the other two are passed to `AgentChat`. Keys the
 * handler used to accept but nothing read — `aiSmartRoutingEnabled`,
 * `aiVoiceEnabled`, `agentDirectoryEnabled` — are gone from both sides.
 */
interface PortalSettings {
  aiAgentEnabled: boolean;
  aiSearchEnabled: boolean;
  aiMultimodalEnabled: boolean;
  chatHistoryEnabled: boolean;
  folderWatchEnabled: boolean;
}

interface SettingsResponse {
  settings: PortalSettings;
  error?: string;
}

interface UpdateResponse {
  success?: boolean;
  error?: string;
}

/** Everything off. Also the shape callers get before the fetch resolves. */
const DEFAULT_SETTINGS: PortalSettings = {
  aiAgentEnabled: false,
  aiSearchEnabled: false,
  aiMultimodalEnabled: false,
  chatHistoryEnabled: false,
  folderWatchEnabled: false,
};

interface AiSettingsManagerProps {
  initialSettings?: { aiAgentEnabled: boolean; aiSearchEnabled: boolean };
  onSettingsChange?: (settings: { aiAgentEnabled: boolean; aiSearchEnabled: boolean }) => void;
}

export function AiSettingsManager({ initialSettings, onSettingsChange }: AiSettingsManagerProps) {
  const { t } = useTranslation();
  const [saving, setSaving] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const setError = setActionError;
  const [successMsg, setSuccessMsg] = useState<string | null>(null);
  const queryClient = useQueryClient();

  const SETTINGS_KEY = ["admin", "getPortalSettings"];

  // A caller that already has the flags passes them in, and the panel then does
  // not fetch at all. Toggles write straight into this cache entry, so the
  // rendered state is the cache rather than a copy of it.
  const {
    data: settings = DEFAULT_SETTINGS,
    isPending,
    error: queryError,
  } = useQuery({
    queryKey: SETTINGS_KEY,
    enabled: !initialSettings,
    initialData: initialSettings
      ? { ...DEFAULT_SETTINGS, ...initialSettings }
      : undefined,
    queryFn: async () => {
      const result = await unwrap<SettingsResponse>(
        dispatch("adminQuery", { action: "getPortalSettings" }),
      );
      const s = result?.settings;
      return {
        aiAgentEnabled: s?.aiAgentEnabled === true,
        aiSearchEnabled: s?.aiSearchEnabled === true,
        aiMultimodalEnabled: s?.aiMultimodalEnabled === true,
        chatHistoryEnabled: s?.chatHistoryEnabled === true,
        folderWatchEnabled: s?.folderWatchEnabled === true,
      };
    },
  });
  const loading = isPending && !initialSettings;
  const error = actionError ?? errorMessage(queryError, "Failed to load settings");

  const toggleSetting = async (key: keyof PortalSettings) => {
    const newValue = !settings[key];
    setSaving(key);
    setError(null);
    setSuccessMsg(null);

    try {
      const result = await adminMutate<UpdateResponse>({
        action: "updatePortalSettings",
        params: { key, value: String(newValue) },
      });
      if (result?.success) {
        const newSettings = { ...settings, [key]: newValue };
        queryClient.setQueryData(SETTINGS_KEY, newSettings);
        onSettingsChange?.(newSettings);
        setSuccessMsg(t("aiSettingsSaved"));
        setTimeout(() => setSuccessMsg(null), 3000);
      } else if (result?.error) {
        setError(result.error);
      }
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to update setting");
    } finally {
      setSaving(null);
    }
  };

  if (loading) {
    return <div className="ai-settings-loading">⏳ {t("aiSettingsLoading")}</div>;
  }

  return (
    <div className="ai-settings-manager">
      <p className="ai-settings-desc">{t("aiSettingsDesc")}</p>

      {error && <div className="ai-settings-error">⚠️ {error}</div>}
      {successMsg && <div className="ai-settings-success">✅ {successMsg}</div>}

      {/* ─── AI Agent (instant-ready) ─── */}
      <div className="ai-settings-feature-section">
        <div className="ai-settings-toggle-card">
          <div className="toggle-info">
            <span className="toggle-icon">🤖</span>
            <div>
              <h4>{t("aiSettingsAgentTitle")}</h4>
              <p>{t("aiSettingsAgentDesc")}</p>
            </div>
          </div>
          <label className="toggle-switch">
            <input
              type="checkbox"
              checked={settings.aiAgentEnabled}
              onChange={() => toggleSetting("aiAgentEnabled")}
              disabled={saving !== null}
            />
            <span className="toggle-slider" />
          </label>
          {saving === "aiAgentEnabled" && <span className="toggle-saving">⏳</span>}
        </div>
        <div className="ai-settings-feature-meta">
          <span className="meta-badge ready">✅ {t("aiSettingsReady")}</span>
          <span className="meta-cost">~$0.001 / {t("aiSettingsPerRequest")}</span>
          <span className="meta-setup">⚡ {t("aiSettingsInstant")}</span>
        </div>
      </div>

      {/* ─── Semantic Search (KB required) ─── */}
      <div className="ai-settings-feature-section">
        <div className="ai-settings-toggle-card">
          <div className="toggle-info">
            <span className="toggle-icon">🔍</span>
            <div>
              <h4>{t("aiSettingsSearchTitle")}</h4>
              <p>{t("aiSettingsSearchDesc")}</p>
            </div>
          </div>
          <label className="toggle-switch">
            <input
              type="checkbox"
              checked={settings.aiSearchEnabled}
              onChange={() => toggleSetting("aiSearchEnabled")}
              disabled={saving !== null}
            />
            <span className="toggle-slider" />
          </label>
          {saving === "aiSearchEnabled" && <span className="toggle-saving">⏳</span>}
        </div>
        <div className="ai-settings-feature-meta">
          <span className="meta-badge setup-needed">⚙️ {t("aiSettingsKbRequired")}</span>
          <span className="meta-cost">~$1–10 / {t("aiSettingsPerMonth")}</span>
          <span className="meta-setup">🕐 {t("aiSettingsSetupTime")}</span>
        </div>

        {/* KB Setup Guide (collapsible) */}
        <details className="ai-settings-setup-guide">
          <summary>{t("aiSettingsSetupGuide")}</summary>
          <div className="setup-guide-content">
            <p className="setup-intro">{t("aiSettingsSetupIntro")}</p>

            {/* Cost Comparison Table */}
            <table className="setup-cost-table">
              <thead>
                <tr>
                  <th>{t("aiSettingsVectorStore")}</th>
                  <th>{t("aiSettingsMonthlyCost")}</th>
                  <th>{t("aiSettingsSetupTimeLabel")}</th>
                </tr>
              </thead>
              <tbody>
                <tr className="recommended">
                  <td><strong>S3 Vectors</strong> ⭐</td>
                  <td>~$1–10</td>
                  <td>~10 {t("aiSettingsMinutes")}</td>
                </tr>
                <tr>
                  <td>OpenSearch Serverless</td>
                  <td>~$700</td>
                  <td>~15 {t("aiSettingsMinutes")}</td>
                </tr>
              </tbody>
            </table>

            {/* Setup Steps */}
            <h5>{t("aiSettingsSetupSteps")}</h5>
            <ol className="setup-steps">
              <li>{t("aiSettingsStep1")}</li>
              <li>{t("aiSettingsStep2")}</li>
              <li>{t("aiSettingsStep3")}</li>
              <li>{t("aiSettingsStep4")}</li>
            </ol>

            <div className="setup-note">
              <strong>💡 {t("aiSettingsNote")}</strong>
              <p>{t("aiSettingsNoteDesc")}</p>
            </div>
          </div>
        </details>
      </div>

      {/* ─── Multimodal Image (requires Agent) ─── */}
      <div className="ai-settings-feature-section">
        <div className="ai-settings-toggle-card">
          <div className="toggle-info">
            <span className="toggle-icon">🖼️</span>
            <div>
              <h4>{t("aiSettingsMultimodalTitle")}</h4>
              <p>{t("aiSettingsMultimodalDesc")}</p>
            </div>
          </div>
          <label className="toggle-switch">
            <input
              type="checkbox"
              checked={settings.aiMultimodalEnabled}
              onChange={() => toggleSetting("aiMultimodalEnabled")}
              disabled={saving !== null || !settings.aiAgentEnabled}
            />
            <span className="toggle-slider" />
          </label>
          {saving === "aiMultimodalEnabled" && <span className="toggle-saving">⏳</span>}
        </div>
        <div className="ai-settings-feature-meta">
          <span className="meta-badge ready">✅ {t("aiSettingsReady")}</span>
          <span className="meta-cost">~$0.003 / {t("aiSettingsPerImage")}</span>
        </div>
      </div>

      {/* ─── Chat History ─── */}
      <div className="ai-settings-feature-section">
        <div className="ai-settings-toggle-card">
          <div className="toggle-info">
            <span className="toggle-icon">📜</span>
            <div>
              <h4>{t("aiSettingsChatHistoryTitle")}</h4>
              <p>{t("aiSettingsChatHistoryDesc")}</p>
            </div>
          </div>
          <label className="toggle-switch">
            <input
              type="checkbox"
              checked={settings.chatHistoryEnabled}
              onChange={() => toggleSetting("chatHistoryEnabled")}
              disabled={saving !== null || !settings.aiAgentEnabled}
            />
            <span className="toggle-slider" />
          </label>
          {saving === "chatHistoryEnabled" && <span className="toggle-saving">⏳</span>}
        </div>
        <div className="ai-settings-feature-meta">
          <span className="meta-badge ready">✅ {t("aiSettingsReady")}</span>
          <span className="meta-cost">~$0 / {t("aiSettingsPerMonth")}</span>
        </div>
      </div>

      {/* ─── Folder Watch ───
          Unlike the AI switches, this one does not enable a capability the portal
          owns. The events come from FPolicy on the SVM, or from Transfer Family,
          publishing to EventBridge; the portal only reads what arrived. So the
          switch means "a publisher exists", and leaving it off is the honest
          default for a deployment that has not set one up — otherwise the section
          appears with an inbox that can never fill. */}
      <div className="ai-settings-feature-section">
        <div className="ai-settings-toggle-card">
          <div className="toggle-info">
            <span className="toggle-icon">🔔</span>
            <div>
              <h4>{t("aiSettingsFolderWatchTitle")}</h4>
              <p>{t("aiSettingsFolderWatchDesc")}</p>
            </div>
          </div>
          <label className="toggle-switch">
            <input
              type="checkbox"
              checked={settings.folderWatchEnabled}
              onChange={() => toggleSetting("folderWatchEnabled")}
              disabled={saving !== null}
            />
            <span className="toggle-slider" />
          </label>
          {saving === "folderWatchEnabled" && <span className="toggle-saving">⏳</span>}
        </div>
        <div className="ai-settings-feature-meta">
          <span className="meta-badge ready">✅ {t("aiSettingsReady")}</span>
          <span className="meta-cost">~$0 / {t("aiSettingsPerMonth")}</span>
        </div>
        <p className="rm-hint">{t("aiSettingsFolderWatchPrereq")}</p>
      </div>

      {/* ─── Smart Routing — deploy-time configuration, not a switch ───
          This was a toggle. It wrote a value nothing read, so it changed nothing,
          and had it been wired the switch would have offered to widen a
          multi-tenant scope boundary from the UI. KB scope filtering follows the
          group-to-prefix mapping given at deploy time, so the panel states that
          rather than pretending to control it. */}
      <div className="ai-settings-feature-section">
        <div className="ai-settings-toggle-card">
          <div className="toggle-info">
            <span className="toggle-icon">🔀</span>
            <div>
              <h4>{t("aiSettingsSmartRoutingTitle")}</h4>
              <p>{t("aiSettingsSmartRoutingDesc")}</p>
            </div>
          </div>
          <span className="meta-badge setup-needed">⚙️ {t("aiSettingsDeployTimeOnly")}</span>
        </div>
        <div className="ai-settings-feature-meta">
          <span className="meta-badge setup-needed">⚙️ {t("aiSettingsGroupMapping")}</span>
          <span className="meta-cost">$0</span>
        </div>
        <p className="form-note">{t("aiSettingsSmartRoutingConfigNote")}</p>
      </div>

      {/* ─── Status Summary ─── */}
      <div className="ai-settings-status">
        <h4>{t("aiSettingsStatusTitle")}</h4>
        <table className="ai-settings-table">
          <tbody>
            <tr>
              <td>🤖 {t("aiSettingsAgentTitle")}</td>
              <td>
                <span className={`status-badge ${settings.aiAgentEnabled ? "enabled" : "disabled"}`}>
                  {settings.aiAgentEnabled ? t("stateEnabled") : t("stateDisabled")}
                </span>
              </td>
            </tr>
            <tr>
              <td>🔍 {t("aiSettingsSearchTitle")}</td>
              <td>
                <span className={`status-badge ${settings.aiSearchEnabled ? "enabled" : "disabled"}`}>
                  {settings.aiSearchEnabled ? t("stateEnabled") : t("stateDisabled")}
                </span>
              </td>
            </tr>
            <tr>
              <td>🖼️ {t("aiSettingsMultimodalTitle")}</td>
              <td>
                <span className={`status-badge ${settings.aiMultimodalEnabled ? "enabled" : "disabled"}`}>
                  {settings.aiMultimodalEnabled ? t("stateEnabled") : t("stateDisabled")}
                </span>
              </td>
            </tr>
            <tr>
              <td>📜 {t("aiSettingsChatHistoryTitle")}</td>
              <td>
                <span className={`status-badge ${settings.chatHistoryEnabled ? "enabled" : "disabled"}`}>
                  {settings.chatHistoryEnabled ? t("stateEnabled") : t("stateDisabled")}
                </span>
              </td>
            </tr>
            <tr>
              <td>🔀 {t("aiSettingsSmartRoutingTitle")}</td>
              <td>
                <span className="status-badge">{t("aiSettingsDeployTimeOnly")}</span>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  );
}
