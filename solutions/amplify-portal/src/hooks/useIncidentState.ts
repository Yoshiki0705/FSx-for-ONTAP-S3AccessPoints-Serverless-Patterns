/**
 * useIncidentState — Incident lifecycle management for ARP/AI containment.
 *
 * States: DETECTED → CONTAINED → INVESTIGATING → RESOLVED
 *
 * Stored in localStorage (per-volume). Future: DynamoDB persistence.
 * Integrates with ARP containment actions to auto-advance state.
 */
import { useState, useCallback } from "react";

export type IncidentState = "none" | "detected" | "contained" | "investigating" | "resolved";

export interface IncidentRecord {
  state: IncidentState;
  detectedAt?: string;
  containedAt?: string;
  resolvedAt?: string;
  blockedUsers: string[];
  blockedIps: string[];
  snapshotName?: string;
  notes: string;
}

const STORAGE_PREFIX = "portal-incident-";

function loadIncident(volumeName: string): IncidentRecord {
  try {
    const raw = localStorage.getItem(`${STORAGE_PREFIX}${volumeName}`);
    if (raw) return JSON.parse(raw);
  } catch { /* noop */ }
  return { state: "none", blockedUsers: [], blockedIps: [], notes: "" };
}

function saveIncident(volumeName: string, record: IncidentRecord) {
  try { localStorage.setItem(`${STORAGE_PREFIX}${volumeName}`, JSON.stringify(record)); }
  catch { /* noop */ }
}

export function useIncidentState(volumeName: string) {
  const [incident, setIncident] = useState<IncidentRecord>(() => loadIncident(volumeName));

  const transition = useCallback((newState: IncidentState, updates?: Partial<IncidentRecord>) => {
    setIncident((prev) => {
      const updated: IncidentRecord = {
        ...prev,
        ...updates,
        state: newState,
      };
      if (newState === "detected" && !updated.detectedAt) updated.detectedAt = new Date().toISOString();
      if (newState === "contained" && !updated.containedAt) updated.containedAt = new Date().toISOString();
      if (newState === "resolved" && !updated.resolvedAt) updated.resolvedAt = new Date().toISOString();

      saveIncident(volumeName, updated);
      return updated;
    });
  }, [volumeName]);

  const markDetected = useCallback(() => transition("detected"), [transition]);
  const markContained = useCallback((snapshot?: string, users?: string[], ips?: string[]) => {
    transition("contained", { snapshotName: snapshot, blockedUsers: users || [], blockedIps: ips || [] });
  }, [transition]);
  const markInvestigating = useCallback((notes?: string) => transition("investigating", { notes: notes || "" }), [transition]);
  const markResolved = useCallback(() => transition("resolved"), [transition]);
  const reset = useCallback(() => {
    const empty: IncidentRecord = { state: "none", blockedUsers: [], blockedIps: [], notes: "" };
    saveIncident(volumeName, empty);
    setIncident(empty);
  }, [volumeName]);

  return { incident, markDetected, markContained, markInvestigating, markResolved, reset };
}
