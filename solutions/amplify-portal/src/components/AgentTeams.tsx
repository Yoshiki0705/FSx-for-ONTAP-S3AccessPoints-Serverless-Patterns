/**
 * AgentTeams — Multi-Agent Teams gallery and creation wizard.
 *
 * Ported from RAG-FSxN-CDK multi-agent-teams pattern.
 * Shows existing teams as cards + wizard to create new teams by selecting agents.
 */
import { useState, useEffect, useCallback } from "react";
import { generateClient } from "aws-amplify/data";
import type { Schema } from "../../amplify/data/resource";
import { useTranslation } from "../i18n";

const client = generateClient<Schema>();

interface TeamAgent {
  agentId: string;
  name: string;
  icon: string;
  role: string;
}

interface TeamItem {
  teamId: string;
  name: string;
  description: string;
  agents: TeamAgent[];
  isShared: boolean;
  createdBy: string;
  createdAt: number;
}

interface AgentOption {
  agentId: string;
  name: string;
  icon: string;
  category: string;
}

function parseResp<T>(response: { data?: unknown }): T | null {
  if (!response.data) return null;
  try {
    return typeof response.data === "string" ? JSON.parse(response.data) : (response.data as T);
  } catch { return null; }
}

interface AgentTeamsProps {
  onSelectTeam?: (teamId: string) => void;
}

export function AgentTeams({ onSelectTeam }: AgentTeamsProps) {
  const { t } = useTranslation();
  const [teams, setTeams] = useState<TeamItem[]>([]);
  const [agents, setAgents] = useState<AgentOption[]>([]);
  const [loading, setLoading] = useState(true);
  const [showWizard, setShowWizard] = useState(false);

  // Wizard state
  const [wizName, setWizName] = useState("");
  const [wizDesc, setWizDesc] = useState("");
  const [wizAgents, setWizAgents] = useState<TeamAgent[]>([]);
  const [wizShared, setWizShared] = useState(false);
  const [wizSaving, setWizSaving] = useState(false);
  const [wizError, setWizError] = useState<string | null>(null);

  const loadData = useCallback(async () => {
    setLoading(true);
    try {
      const [teamsResp, agentsResp] = await Promise.all([
        (client.queries as any).agentQuery({ action: "listTeams", params: JSON.stringify({}) }),
        (client.queries as any).agentQuery({ action: "listAgents", params: JSON.stringify({}) }),
      ]);
      const teamsData = parseResp<{ teams: TeamItem[] }>(teamsResp);
      const agentsData = parseResp<{ agents: AgentOption[] }>(agentsResp);
      if (teamsData?.teams) setTeams(teamsData.teams);
      if (agentsData?.agents) setAgents(agentsData.agents);
    } catch { /* silent */ }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { loadData(); }, [loadData]);

  function addAgentToTeam(agent: AgentOption) {
    if (wizAgents.find((a) => a.agentId === agent.agentId)) return;
    setWizAgents((prev) => [...prev, { agentId: agent.agentId, name: agent.name, icon: agent.icon, role: "collaborator" }]);
  }

  function removeAgentFromTeam(agentId: string) {
    setWizAgents((prev) => prev.filter((a) => a.agentId !== agentId));
  }

  function setAgentRole(agentId: string, role: string) {
    setWizAgents((prev) => prev.map((a) => a.agentId === agentId ? { ...a, role } : a));
  }

  async function createTeam() {
    if (!wizName.trim()) { setWizError(t("teamsNameRequired")); return; }
    if (wizAgents.length < 2) { setWizError(t("teamsMinAgents")); return; }

    setWizSaving(true);
    setWizError(null);
    try {
      const response = await (client.queries as any).agentQuery({
        action: "createTeam",
        params: JSON.stringify({
          name: wizName.trim(),
          description: wizDesc,
          agents: wizAgents,
          isShared: wizShared,
        }),
      });
      const data = parseResp<{ success: boolean; teamId: string }>(response);
      if (data?.success) {
        setShowWizard(false);
        setWizName(""); setWizDesc(""); setWizAgents([]); setWizShared(false);
        loadData();
      } else {
        setWizError("Failed to create team");
      }
    } catch (e: unknown) {
      setWizError(e instanceof Error ? e.message : "Error");
    } finally { setWizSaving(false); }
  }

  async function deleteTeam(teamId: string) {
    if (!confirm(t("teamsDeleteConfirm"))) return;
    try {
      await (client.queries as any).agentQuery({
        action: "deleteTeam",
        params: JSON.stringify({ teamId }),
      });
      setTeams((prev) => prev.filter((t) => t.teamId !== teamId));
    } catch { /* silent */ }
  }

  // --- Wizard View ---
  if (showWizard) {
    const availableAgents = agents.filter((a) => !wizAgents.find((wa) => wa.agentId === a.agentId));

    return (
      <div className="agent-teams">
        <div className="teams-wizard">
          <div className="teams-wizard-header">
            <h3>🧩 {t("teamsWizardTitle")}</h3>
            <button className="btn-sm" onClick={() => setShowWizard(false)}>✕</button>
          </div>

          {wizError && <div className="teams-error">⚠️ {wizError}</div>}

          {/* Step 1: Name */}
          <div className="wizard-step">
            <label>{t("teamsName")} *</label>
            <input type="text" value={wizName} onChange={(e) => setWizName(e.target.value)} placeholder={t("teamsNamePlaceholder")} />
          </div>

          <div className="wizard-step">
            <label>{t("teamsDesc")}</label>
            <input type="text" value={wizDesc} onChange={(e) => setWizDesc(e.target.value)} placeholder={t("teamsDescPlaceholder")} />
          </div>

          {/* Step 2: Select Agents */}
          <div className="wizard-step">
            <label>{t("teamsSelectAgents")} ({wizAgents.length} {t("teamsSelected")})</label>
            <div className="wizard-agent-pool">
              {availableAgents.map((agent) => (
                <button key={agent.agentId} className="wizard-agent-chip" onClick={() => addAgentToTeam(agent)}>
                  + {agent.icon} {agent.name}
                </button>
              ))}
              {availableAgents.length === 0 && <span className="teams-hint">{t("teamsNoMoreAgents")}</span>}
            </div>
          </div>

          {/* Step 3: Assign Roles */}
          {wizAgents.length > 0 && (
            <div className="wizard-step">
              <label>{t("teamsAssignRoles")}</label>
              <div className="wizard-team-list">
                {wizAgents.map((agent) => (
                  <div key={agent.agentId} className="wizard-team-member">
                    <span className="team-member-icon">{agent.icon}</span>
                    <span className="team-member-name">{agent.name}</span>
                    <select value={agent.role} onChange={(e) => setAgentRole(agent.agentId, e.target.value)}>
                      <option value="supervisor">Supervisor</option>
                      <option value="collaborator">Collaborator</option>
                      <option value="reviewer">Reviewer</option>
                    </select>
                    <button className="btn-sm" onClick={() => removeAgentFromTeam(agent.agentId)}>✕</button>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Shared */}
          <div className="wizard-step">
            <label className="shared-toggle">
              <input type="checkbox" checked={wizShared} onChange={(e) => setWizShared(e.target.checked)} />
              <span>{t("teamsShared")}</span>
            </label>
          </div>

          {/* Submit */}
          <div className="creator-actions">
            <button className="btn-secondary" onClick={() => setShowWizard(false)}>{t("cancel")}</button>
            <button className="btn-primary" onClick={createTeam} disabled={wizSaving}>
              {wizSaving ? "⏳" : "🧩"} {t("teamsCreate")}
            </button>
          </div>
        </div>
      </div>
    );
  }

  // --- Gallery View ---
  return (
    <div className="agent-teams">
      <div className="teams-header">
        <h2>🧩 {t("teamsTitle")}</h2>
        <button className="btn-primary" onClick={() => setShowWizard(true)}>+ {t("teamsCreate")}</button>
      </div>

      {loading ? (
        <div className="agent-dir-loading">⏳ {t("loading")}</div>
      ) : teams.length === 0 ? (
        <div className="agent-dir-empty">
          <p>{t("teamsEmpty")}</p>
          <button className="btn-primary" onClick={() => setShowWizard(true)}>+ {t("teamsCreate")}</button>
        </div>
      ) : (
        <div className="teams-gallery">
          {teams.map((team) => (
            <div key={team.teamId} className="team-card">
              <div className="team-card-header">
                <h4>{team.name}</h4>
                {team.isShared && <span className="agent-dir-shared-badge">{t("agentDirShared")}</span>}
              </div>
              {team.description && <p className="team-card-desc">{team.description}</p>}
              <div className="team-card-agents">
                {team.agents.map((a) => (
                  <span key={a.agentId} className="team-agent-badge" title={`${a.name} (${a.role})`}>
                    {a.icon} <span className="team-role-tag">{a.role}</span>
                  </span>
                ))}
              </div>
              <div className="team-card-actions">
                {onSelectTeam && (
                  <button className="btn-sm" onClick={() => onSelectTeam(team.teamId)}>💬 {t("teamsUse")}</button>
                )}
                <button className="btn-sm" onClick={() => deleteTeam(team.teamId)}>🗑️</button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
