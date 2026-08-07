import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "../../i18n";
import { errorMessage } from "../../lib/portalQuery";
import { adminMutate, adminQuery, type DispatchCall } from "../../lib/dispatch";

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
  const [actionError, setActionError] = useState<string | null>(null);
  const setError = setActionError;
  const [success, setSuccess] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [showCreate, setShowCreate] = useState(false);
  /** Policy or event awaiting delete confirmation. */
  const [confirmFor, setConfirmFor] = useState<{ kind: "policy" | "event"; name: string } | null>(null);
  // Policy form
  const [polName, setPolName] = useState("");
  const [polEvents, setPolEvents] = useState("");
  const [polEngine, setPolEngine] = useState("native");
  const [polPriority, setPolPriority] = useState(1);
  // Event form
  const [evName, setEvName] = useState("");
  const [evProtocol, setEvProtocol] = useState("cifs");
  const [evOps, setEvOps] = useState<string[]>(["create", "delete"]);

  /**
   * Run a write action, then refresh the active tab.
   *
   * Takes the whole call rather than `(action: string, params: Record<string,
   * unknown>)`. That signature accepted any name with any parameters beside it,
   * which is the shape that let a lock button ship broken elsewhere in this portal.
   */
  const runAction = async (call: DispatchCall<"adminMutation">) => {
    setBusy(true);
    setError(null);
    setSuccess(null);
    try {
      const data = await adminMutate<{ success?: boolean }>(call);
      if (data?.success) {
        setSuccess(t("fpActionDone"));
        setTimeout(() => setSuccess(null), 4000);
        setShowCreate(false);
        setConfirmFor(null);
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

  // One query per tab. The tab is part of the key, which is also what removed
  // the exhaustive-deps warning: the effect listed only [tab] while the loader
  // it called closed over the tab as well.
  const {
    data,
    isPending: loading,
    error: queryError,
    refetch,
  } = useQuery({
    queryKey: ["admin", "fpolicy", tab],
    queryFn: async () => {
      const call =
        tab === "policies"
          ? ({ action: "listFpolicyPolicies" } as const)
          : tab === "events"
            ? ({ action: "listFpolicyEvents" } as const)
            : ({ action: "getFpolicyStatus" } as const);
      const parsed = await adminQuery<{
        policies?: FPolicyPolicy[];
        events?: FPolicyEvent[];
        connections?: FPolicyConnection[];
      }>(call);
      // A dispatcher that is not wired yet is an empty list, not a failure.
      if (
        parsed?.error &&
        !parsed.error.includes("Unknown action") &&
        !parsed.error.includes("not configured")
      ) {
        throw new Error(parsed.error);
      }
      return parsed;
    },
  });

  const policies = tab === "policies" ? data?.policies ?? [] : [];
  const events = tab === "events" ? data?.events ?? [] : [];
  const connections = tab === "connections" ? data?.connections ?? [] : [];

  // Mutation handlers report through their own state, so a failed action is
  // never mistaken for a failed load.
  const loadData = () => void refetch();
  const error = actionError ?? errorMessage(queryError, "Load failed");

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
              onClick={() => runAction({ action: "createFpolicyPolicy", params: {
                name: polName.trim(),
                events: polEvents.split(",").map((s) => s.trim()).filter(Boolean),
                engineName: polEngine.trim() || "native",
                priority: polPriority,
              } })}>
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
              onClick={() => runAction({ action: "createFpolicyEvent", params: {
                name: evName.trim(), protocol: evProtocol, fileOperations: evOps,
              } })}>
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
                      onClick={() => runAction({ action: "setFpolicyPolicyEnabled", params: {
                        name: p.name,
                        enabled: !p.enabled,
                        priority: p.enabled ? undefined : p.priority || 1,
                      } })}>
                      {p.enabled ? t("fpDisableBtn") : t("fpEnableBtn")}
                    </button>
                    <button className="rm-btn-danger-sm" disabled={busy || p.enabled}
                      title={p.enabled ? t("fpDisableFirst") : t("delete")}
                      onClick={() => setConfirmFor({ kind: "policy", name: p.name })}>
                      {t("delete")}
                    </button>
                  </span>
                  {confirmFor?.kind === "policy" && confirmFor.name === p.name && (
                    <span className="peer-accept-row" role="alertdialog">
                      <span className="sm-confirm-text">{t("fpConfirmDeletePolicy")}</span>
                      <button className="rm-btn-danger-sm" disabled={busy}
                        onClick={() => runAction({ action: "deleteFpolicyPolicy", params: { name: p.name, confirm: true } })}>
                        {t("rmExecute")}
                      </button>
                      <button className="rm-btn-sm" onClick={() => setConfirmFor(null)}>
                        {t("cancel")}
                      </button>
                    </span>
                  )}
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
                    onClick={() => setConfirmFor({ kind: "event", name: e.name })}>
                    {t("delete")}
                  </button>
                  {confirmFor?.kind === "event" && confirmFor.name === e.name && (
                    <span className="peer-accept-row" role="alertdialog">
                      <span className="sm-confirm-text">{t("fpConfirmDeleteEvent")}</span>
                      <button className="rm-btn-danger-sm" disabled={busy}
                        onClick={() => runAction({ action: "deleteFpolicyEvent", params: { name: e.name, confirm: true } })}>
                        {t("rmExecute")}
                      </button>
                      <button className="rm-btn-sm" onClick={() => setConfirmFor(null)}>
                        {t("cancel")}
                      </button>
                    </span>
                  )}
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
