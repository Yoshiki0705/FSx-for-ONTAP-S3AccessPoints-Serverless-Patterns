/**
 * AgentTeams — Multi-Agent Teams gallery and creation wizard.
 *
 * Ported from RAG-FSxN-CDK multi-agent-teams pattern.
 * Shows existing teams as cards + wizard to create new teams by selecting agents.
 */
import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "../i18n";
import { dispatch } from "../lib/dispatch";

/** Cache key for the teams + agents bundle, shared with the delete action. */
const TEAMS_KEY = ["agents", "teamsAndAgents"];

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
  /**
   * Open the chat running this stored team.
   *
   * Optional, and for a while nothing passed it — so the "use" button below never
   * rendered and a saved team had no way to be run. It is wired now; the name comes
   * along so the chat can say which team is answering.
   */
  onSelectTeam?: (teamId: string, name: string) => void;
}

export function AgentTeams({ onSelectTeam }: AgentTeamsProps) {
  const { t } = useTranslation();
  const [showWizard, setShowWizard] = useState(false);

  // Wizard state
  const [wizName, setWizName] = useState("");
  const [wizDesc, setWizDesc] = useState("");
  const [wizAgents, setWizAgents] = useState<TeamAgent[]>([]);
  const [wizShared, setWizShared] = useState(false);
  const [wizSaving, setWizSaving] = useState(false);
  const [wizError, setWizError] = useState<string | null>(null);

  const queryClient = useQueryClient();

  // The wizard needs both lists before it is useful, so they stay one query and
  // are fetched in parallel inside it.
  const {
    data,
    isPending: loading,
    refetch,
  } = useQuery({
    queryKey: TEAMS_KEY,
    queryFn: async () => {
      const [teamsResp, agentsResp] = await Promise.all([
        dispatch("agentQuery", { action: "listTeams" }),
        dispatch("agentQuery", { action: "listAgents" }),
      ]);
      return {
        teams: parseResp<{ teams: TeamItem[] }>(teamsResp)?.teams ?? [],
        agents: parseResp<{ agents: AgentOption[] }>(agentsResp)?.agents ?? [],
      };
    },
  });

  const teams = data?.teams ?? [];
  const agents = data?.agents ?? [];
  const loadData = () => void refetch();

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
      const response = await dispatch("agentQuery", {
        action: "createTeam",
        params: {
          name: wizName.trim(),
          description: wizDesc,
          agents: wizAgents,
          isShared: wizShared,
        },
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
      await dispatch("agentQuery", { action: "deleteTeam", params: { teamId } });
      // Drop the card from the cache rather than refetching both lists.
      queryClient.setQueryData<{ teams: TeamItem[]; agents: AgentOption[] }>(
        TEAMS_KEY,
        (prev) =>
          prev
            ? { ...prev, teams: prev.teams.filter((x) => x.teamId !== teamId) }
            : prev,
      );
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
                  <button className="btn-sm" onClick={() => onSelectTeam(team.teamId, team.name)}>
                    💬 {t("teamsUse")}
                  </button>
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
