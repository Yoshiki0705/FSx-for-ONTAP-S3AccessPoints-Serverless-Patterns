/**
 * Decode the payload of a custom AppSync operation.
 *
 * The generic dispatch operations in `amplify/data/resource.ts` (adminQuery,
 * adminMutation, agentQuery and the rest) are declared `.returns(a.json())`, so the
 * generated client types their `data` as `Json` — a string, number, boolean, object
 * or array. The resolvers in practice hand back a JSON *string*, which is why every
 * caller parses it.
 *
 * This lived as 31 near-identical copies pasted across the components, in five
 * formatting variants. Thirty of them declared the parameter as
 * `{ data?: string | null }`, narrower than what the schema actually returns; the
 * thirty-first already used `unknown`. The mismatch was invisible because each call
 * site went through `(client.queries as any)`, which erased the response type before
 * it could be checked. Removing those casts surfaced 104 type errors, all of them
 * this one disagreement.
 *
 * `unknown` is the honest parameter type, and the runtime check that follows is the
 * same one every copy already performed.
 */
export function parseResponse<T>(response: { data?: unknown }): T | null {
  if (!response.data) return null;
  try {
    return typeof response.data === "string"
      ? (JSON.parse(response.data) as T)
      : (response.data as T);
  } catch {
    return null;
  }
}
