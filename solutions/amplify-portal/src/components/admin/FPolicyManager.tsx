import { useState, useEffect } from "react";
import { generateClient } from "aws-amplify/data";
import type { Schema } from "../../../amplify/data/resource";
import { useTranslation } from "../../i18n";

const client = generateClient<Schema>();

function parseResponse<T>(response: { data?: string | null }): T | null {
  if (!response.data) return null;
  try {
    return typeof response.data === "string" ? JSON.parse(response.data) : response.data;
  } catch { return null; }
}

interface FPolicyPolicy {
  name: string;
  enabled: boolean;
  priority: number;
  engineType: string;
  events: string[];
}

interface FPolicyEvent {
  name: string;
  protocol: string;
  fileOperations: string[];
}

interface FPolicyConnection {
  node: string;
  policy: string;
  server: string;
  state: string;
}

type Tab = "policies" | "events" | "connections";

export function FPolicyManager() {
  const { t } = useTranslation();
  const [tab, setTab] = useState<Tab>("policies");
  const [policies, setPolicies] = useState<FPolicyPolicy[]>([]);
  const [events, setEvents] = useState<FPolicyEvent[]>([]);
  const [connections, setConnections] = useState<FPolicyConnection[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadData = async () => {
    setLoading(true); setError(null);
    try {
      if (tab === "policies") {
        const resp = await (client.queries as any).adminQuery({ action: "listFpolicyPolicies", params: JSON.stringify({}) });
        const data = parseResponse<{ policies?: FPolicyPolicy[]; error?: string }>(resp);
        if (data?.error && !data.error.includes("Unknown action") && !data.error.includes("not configured")) setError(data.error);
        else setPolicies(data?.policies || []);
      } else if (tab === "events") {
        const resp = await (client.queries as any).adminQuery({ action: "listFpolicyEvents", params: JSON.stringify({}) });
        const data = parseResponse<{ events?: FPolicyEvent[]; error?: string }>(resp);
        if (data?.error && !data.error.includes("Unknown action") && !data.error.includes("not configured")) setError(data.error);
        else setEvents(data?.events || []);
      } else {
        const resp = await (client.queries as any).adminQuery({ action: "getFpolicyStatus", params: JSON.stringify({}) });
        const data = parseResponse<{ connections?: FPolicyConnection[]; error?: string }>(resp);
        if (data?.error && !data.error.includes("Unknown action") && !data.error.includes("not configured")) setError(data.error);
        else setConnections(data?.connections || []);
      }
    } catch (e) { setError(e instanceof Error ? e.message : "Load failed"); }
    finally { setLoading(false); }
  };

  useEffect(() => { loadData(); }, [tab]);

  return (
    <div className="fpolicy-manager">
      <div className="lu-tabs">
        <button className={`lu-tab ${tab === "policies" ? "active" : ""}`} onClick={() => setTab("policies")}>📋 {t("fpPolicies")}</button>
        <button className={`lu-tab ${tab === "events" ? "active" : ""}`} onClick={() => setTab("events")}>📡 {t("fpEvents")}</button>
        <button className={`lu-tab ${tab === "connections" ? "active" : ""}`} onClick={() => setTab("connections")}>🔌 {t("fpConnections")}</button>
      </div>

      {error && <div className="rm-error">⚠️ {error}</div>}

      {loading ? <div className="rm-loading">{t("ontapConnecting")}</div> : tab === "policies" ? (
        policies.length === 0 ? <p className="rm-empty">{t("fpNoPolicies")}</p> : (
          <table className="rm-table">
            <thead><tr><th>{t("fpPolicyName")}</th><th>{t("fpEnabled")}</th><th>{t("fpPriority")}</th><th>{t("fpEngine")}</th><th>{t("fpEvents")}</th></tr></thead>
            <tbody>{policies.map(p => (
              <tr key={p.name}>
                <td className="lu-username">{p.name}</td>
                <td><span className={`lu-badge ${p.enabled ? "active" : "disabled"}`}>{p.enabled ? t("luActive") : t("luDisabled")}</span></td>
                <td>{p.priority}</td>
                <td>{p.engineType}</td>
                <td>{p.events.join(", ") || "—"}</td>
              </tr>
            ))}</tbody>
          </table>
        )
      ) : tab === "events" ? (
        events.length === 0 ? <p className="rm-empty">{t("fpNoEvents")}</p> : (
          <table className="rm-table">
            <thead><tr><th>{t("fpEventName")}</th><th>{t("fpProtocol")}</th><th>{t("fpOperations")}</th></tr></thead>
            <tbody>{events.map(e => (
              <tr key={e.name}>
                <td className="lu-username">{e.name}</td>
                <td>{e.protocol}</td>
                <td>{e.fileOperations.join(", ") || "—"}</td>
              </tr>
            ))}</tbody>
          </table>
        )
      ) : (
        connections.length === 0 ? <p className="rm-empty">{t("fpNoConnections")}</p> : (
          <table className="rm-table">
            <thead><tr><th>{t("fpPolicy")}</th><th>{t("fpServer")}</th><th>{t("rmState")}</th><th>Node</th></tr></thead>
            <tbody>{connections.map((c, i) => (
              <tr key={i}>
                <td>{c.policy}</td><td>{c.server}</td>
                <td><span className={`lu-badge ${c.state === "connected" ? "active" : "disabled"}`}>{c.state}</span></td>
                <td>{c.node}</td>
              </tr>
            ))}</tbody>
          </table>
        )
      )}
    </div>
  );
}
