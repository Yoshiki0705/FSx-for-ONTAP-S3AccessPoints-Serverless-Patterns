/**
 * AiSettingsManager — Admin panel for AI Agent / Knowledge Base feature enablement.
 *
 * Bedrock KB incurs ongoing running costs (OpenSearch Serverless OCU),
 * so these features are disabled by default and must be explicitly enabled
 * by an administrator from this panel.
 *
 * Pattern inspired by RAG-FSxN-CDK FeatureGateConstruct (DynamoDB-backed toggle).
 */
import { useState, useEffect, useCallback } from "react";
import { generateClient } from "aws-amplify/data";
import type { Schema } from "../../../amplify/data/resource";
import { useTranslation } from "../../i18n";

const client = generateClient<Schema>();

function parseResponse<T>(response: { data?: unknown }): T | null {
  if (!response.data) return null;
  try {
    return typeof response.data === "string" ? JSON.parse(response.data) : (response.data as T);
  } catch { return null; }
}

interface PortalSettings {
  aiAgentEnabled: boolean;
  aiSearchEnabled: boolean;
}

interface SettingsResponse {
  settings: PortalSettings;
  error?: string;
}

interface UpdateResponse {
  success?: boolean;
  error?: string;
}

export function AiSettingsManager() {
  const { t } = useTranslation();
  const [settings, setSettings] = useState<PortalSettings>({
    aiAgentEnabled: false,
    aiSearchEnabled: false,
  });
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);

  const loadSettings = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await client.queries.adminQuery({
        action: "getPortalSettings",
        params: JSON.stringify({}),
      });
      const result = parseResponse<SettingsResponse>(response);
      if (result?.settings) {
        setSettings({
          aiAgentEnabled: result.settings.aiAgentEnabled === true,
          aiSearchEnabled: result.settings.aiSearchEnabled === true,
        });
      }
      if (result?.error) {
        setError(result.error);
      }
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to load settings");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { loadSettings(); }, [loadSettings]);

  const toggleSetting = async (key: keyof PortalSettings) => {
    const newValue = !settings[key];
    setSaving(key);
    setError(null);
    setSuccessMsg(null);

    try {
      const response = await client.mutations.adminMutation({
        action: "updatePortalSettings",
        params: JSON.stringify({ key, value: String(newValue) }),
      });
      const result = parseResponse<UpdateResponse>(response);
      if (result?.success) {
        setSettings((prev) => ({ ...prev, [key]: newValue }));
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
      <div className="ai-settings-header">
        <p className="ai-settings-desc">{t("aiSettingsDesc")}</p>
      </div>

      {error && (
        <div className="ai-settings-error">⚠️ {error}</div>
      )}
      {successMsg && (
        <div className="ai-settings-success">✅ {successMsg}</div>
      )}

      {/* Cost Warning */}
      <div className="ai-settings-cost-warning">
        <span className="cost-icon">💰</span>
        <div>
          <strong>{t("aiSettingsCostTitle")}</strong>
          <p>{t("aiSettingsCostDesc")}</p>
        </div>
      </div>

      {/* Feature Toggles */}
      <div className="ai-settings-toggles">
        {/* AI Agent Chat */}
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

        {/* Semantic Search (KB) */}
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
      </div>

      {/* Status Summary */}
      <div className="ai-settings-status">
        <h4>{t("aiSettingsStatusTitle")}</h4>
        <table className="ai-settings-table">
          <tbody>
            <tr>
              <td>🤖 {t("aiSettingsAgentTitle")}</td>
              <td>
                <span className={`status-badge ${settings.aiAgentEnabled ? "enabled" : "disabled"}`}>
                  {settings.aiAgentEnabled ? t("aiSettingsEnabled") : t("aiSettingsDisabled")}
                </span>
              </td>
            </tr>
            <tr>
              <td>🔍 {t("aiSettingsSearchTitle")}</td>
              <td>
                <span className={`status-badge ${settings.aiSearchEnabled ? "enabled" : "disabled"}`}>
                  {settings.aiSearchEnabled ? t("aiSettingsEnabled") : t("aiSettingsDisabled")}
                </span>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  );
}
