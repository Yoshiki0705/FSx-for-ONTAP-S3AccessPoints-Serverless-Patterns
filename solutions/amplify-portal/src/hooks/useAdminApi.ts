/**
 * useAdminApi — shared hook for admin GraphQL API calls.
 *
 * Eliminates repeated parseResponse + generateClient boilerplate across
 * all admin components (VolumeManager, ExportPolicyManager, CifsShareManager, etc.)
 *
 * Usage:
 *   const { query, mutate, loading, error } = useAdminApi();
 *   const data = await query("listVolumes", {});
 *   const result = await mutate("createVolume", { name: "vol1", sizeGiB: 50 });
 */
import { useState, useCallback } from "react";
import { generateClient } from "aws-amplify/data";
import type { Schema } from "../../amplify/data/resource";

const client = generateClient<Schema>();

function parseResponse<T>(response: { data?: string | null }): T | null {
  if (!response.data) return null;
  try {
    return typeof response.data === "string" ? JSON.parse(response.data) : response.data;
  } catch {
    return null;
  }
}

interface UseAdminApiReturn {
  /** Execute an admin read query */
  query: <T>(action: string, params?: Record<string, unknown>) => Promise<T | null>;
  /** Execute an admin write mutation */
  mutate: <T>(action: string, params?: Record<string, unknown>) => Promise<T | null>;
  /** Current loading state */
  loading: boolean;
  /** Last error message (null if no error) */
  error: string | null;
  /** Clear error state */
  clearError: () => void;
}

export function useAdminApi(): UseAdminApiReturn {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const query = useCallback(async <T>(action: string, params?: Record<string, unknown>): Promise<T | null> => {
    setLoading(true);
    setError(null);
    try {
      const response = await (client.queries as any).adminQuery({
        action,
        params: JSON.stringify(params || {}),
      });
      const data = parseResponse<T & { error?: string }>(response);
      if (data && (data as any).error) {
        setError((data as any).error);
        return null;
      }
      return data;
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Query failed";
      setError(msg);
      return null;
    } finally {
      setLoading(false);
    }
  }, []);

  const mutate = useCallback(async <T>(action: string, params?: Record<string, unknown>): Promise<T | null> => {
    setLoading(true);
    setError(null);
    try {
      const response = await (client.mutations as any).adminMutation({
        action,
        params: JSON.stringify(params || {}),
      });
      const data = parseResponse<T & { error?: string }>(response);
      if (data && (data as any).error) {
        setError((data as any).error);
        return null;
      }
      return data;
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Mutation failed";
      setError(msg);
      return null;
    } finally {
      setLoading(false);
    }
  }, []);

  const clearError = useCallback(() => setError(null), []);

  return { query, mutate, loading, error, clearError };
}
