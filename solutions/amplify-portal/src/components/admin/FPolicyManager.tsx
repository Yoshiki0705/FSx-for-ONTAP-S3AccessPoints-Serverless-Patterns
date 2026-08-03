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
  const [success, setSuccess] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [showCreate, setShowCreate] = useState(false);
  // Policy form
  const [polName, setPolName] = useState("");
  const [polEvents, setPolEvents] = useState("");
  const [polEngine, setPolEngine] = useState("native");
  const [polPriority, setPolPriority] = useState(1);
  // Event form
  const [evName, setEvName] = useState("");
  const [evProtocol, setEvProtocol] = useState("cifs");
  const [evOps, setEvOps] = useState<string[]>(["create", "delete"]);

  /** Run a write action, then refresh the active tab. */
  const runAction = async (action: string, params: Record<string, unknown>) => {
    setBusy(true);
    setError(null);
    setSuccess(null);
    try {
      const resp = await (client.mutations as any).adminMutation({
        action,
        params: JSON.stringify(params),
      });
      const data = parseResponse<{ success?: boolean; error?: string }>(resp);
      if (data?.success) {
        setSuccess(t("fpActionDone"));
        setTimeout(() => setSuccess(null), 4000);
        setShowCreate(false);
        loadData();
      } else {
        setError(data?.error || "Action failed");
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "Action failed");
    } finally {
      setBusy(false);
    }
  };

  const toggleOp = (op: string) =>
    setEvOps((prev) => (prev.includes(op) ? prev.filter((o) => o !== op) : [...prev, op]));

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
      {success && <div className="rm-success">✅ {success}</div>}

      {tab !== "connections" && (
        <div className="lu-toolbar">
          <span className="lu-count">
            {tab === "policies" ? policies.length : events.length}{" "}
            {tab === "policies" ? t("fpPolicies") : t("fpEvents")}
          </span>
          <button
            className="rm-btn-primary"
            disabled={busy}
            onClick={() => setShowCreate((v) => !v)}
          >
            + {tab === "policies" ? t("fpCreatePolicy") : t("fpCreateEvent")}
          </button>
        </div>
      )}

      {showCreate && tab === "policies" && (
        <div className="rm-form">
          <h4>{t("fpCreatePolicy")}</h4>
          <div className="rm-form-row">
            <label htmlFor="fp-name">{t("fpPolicyName")}</label>
            <input id="fp-name" type="text" value={polName} disabled={busy}
              onChange={(e) => setPolName(e.target.value)} placeholder="audit_all" />
          </div>
          <div className="rm-form-row">
            <label htmlFor="fp-events">{t("fpEvents")}</label>
            <input id="fp-events" type="text" value={polEvents} disabled={busy}
              onChange={(e) => setPolEvents(e.target.value)} placeholder="file_ops_cifs" />
          </div>
          <div className="rm-form-row">
            <label htmlFor="fp-engine">{t("fpEngine")}</label>
            <input id="fp-engine" type="text" value={polEngine} disabled={busy}
              onChange={(e) => setPolEngine(e.target.value)} />
          </div>
          <div className="rm-form-row">
            <label htmlFor="fp-priority">{t("fpPriority")}</label>
            <input id="fp-priority" type="number" min={1} value={polPriority} disabled={busy}
              onChange={(e) => setPolPriority(Number(e.target.value))} />
          </div>
          <div className="rm-form-actions">
            <button className="rm-btn-primary" disabled={busy || !polName.trim() || !polEvents.trim()}
              onClick={() => runAction("createFpolicyPolicy", {
                name: polName.trim(),
                events: polEvents.split(",").map((s) => s.trim()).filter(Boolean),
                engineName: polEngine.trim() || "native",
                priority: polPriority,
              })}>
              {t("rmCreate")}
            </button>
            <button className="rm-btn-secondary" onClick={() => setShowCreate(false)}>{t("cancel")}</button>
          </div>
          <p className="rm-hint">{t("fpCreatePolicyHint")}</p>
        </div>
      )}

      {showCreate && tab === "events" && (
        <div className="rm-form">
          <h4>{t("fpCreateEvent")}</h4>
          <div className="rm-form-row">
            <label htmlFor="fp-ev-name">{t("fpEventName")}</label>
            <input id="fp-ev-name" type="text" value={evName} disabled={busy}
              onChange={(e) => setEvName(e.target.value)} placeholder="file_ops_cifs" />
          </div>
          <div className="rm-form-row">
            <label htmlFor="fp-ev-proto">{t("fpProtocol")}</label>
            <select id="fp-ev-proto" value={evProtocol} disabled={busy}
              onChange={(e) => setEvProtocol(e.target.value)}>
              <option value="cifs">cifs</option>
              <option value="nfsv3">nfsv3</option>
              <option value="nfsv4">nfsv4</option>
            </select>
          </div>
          <div className="rm-form-row">
            <label>{t("fpOperations")}</label>
            <span className="fp-ops">
              {["create", "delete", "rename", "read", "write", "open", "close"].map((op) => (
                <label key={op} className="fp-op">
                  <input type="checkbox" checked={evOps.includes(op)} disabled={busy}
                    onChange={() => toggleOp(op)} />
                  {op}
                </label>
              ))}
            </span>
          </div>
          <div className="rm-form-actions">
            <button className="rm-btn-primary" disabled={busy || !evName.trim() || evOps.length === 0}
              onClick={() => runAction("createFpolicyEvent", {
                name: evName.trim(), protocol: evProtocol, fileOperations: evOps,
              })}>
              {t("rmCreate")}
            </button>
            <button className="rm-btn-secondary" onClick={() => setShowCreate(false)}>{t("cancel")}</button>
          </div>
        </div>
      )}

      {loading ? <div className="rm-loading">{t("ontapConnecting")}</div> : tab === "policies" ? (
        policies.length === 0 ? <p className="rm-empty">{t("fpNoPolicies")}</p> : (
          <table className="rm-table">
            <thead><tr><th>{t("fpPolicyName")}</th><th>{t("fpEnabled")}</th><th>{t("fpPriority")}</th><th>{t("fpEngine")}</th><th>{t("fpEvents")}</th><th>{t("rmActions")}</th></tr></thead>
            <tbody>{policies.map(p => (
              <tr key={p.name}>
                <td className="lu-username">{p.name}</td>
                <td><span className={`lu-badge ${p.enabled ? "active" : "disabled"}`}>{p.enabled ? t("luActive") : t("luDisabled")}</span></td>
                <td>{p.priority}</td>
                <td>{p.engineType}</td>
                <td>{p.events.join(", ") || "—"}</td>
                <td>
                  <span className="sm-actions" style={{ padding: 0, border: "none" }}>
                    <button className="rm-btn-sm" disabled={busy}
                      onClick={() => runAction("setFpolicyPolicyEnabled", {
                        name: p.name,
                        enabled: !p.enabled,
                        priority: p.enabled ? undefined : p.priority || 1,
                      })}>
                      {p.enabled ? t("fpDisableBtn") : t("fpEnableBtn")}
                    </button>
                    <button className="rm-btn-danger-sm" disabled={busy || p.enabled}
                      title={p.enabled ? t("fpDisableFirst") : t("delete")}
                      onClick={() => runAction("deleteFpolicyPolicy", { name: p.name })}>
                      {t("delete")}
                    </button>
                  </span>
                </td>
              </tr>
            ))}</tbody>
          </table>
        )
      ) : tab === "events" ? (
        events.length === 0 ? <p className="rm-empty">{t("fpNoEvents")}</p> : (
          <table className="rm-table">
            <thead><tr><th>{t("fpEventName")}</th><th>{t("fpProtocol")}</th><th>{t("fpOperations")}</th><th>{t("rmActions")}</th></tr></thead>
            <tbody>{events.map(e => (
              <tr key={e.name}>
                <td className="lu-username">{e.name}</td>
                <td>{e.protocol}</td>
                <td>{e.fileOperations.join(", ") || "—"}</td>
                <td>
                  <button className="rm-btn-danger-sm" disabled={busy}
                    onClick={() => runAction("deleteFpolicyEvent", { name: e.name })}>
                    {t("delete")}
                  </button>
                </td>
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
