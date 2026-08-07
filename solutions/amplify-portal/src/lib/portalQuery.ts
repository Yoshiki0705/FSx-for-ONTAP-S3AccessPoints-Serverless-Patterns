/**
 * Bridge between the generic AppSync dispatch operations and TanStack Query.
 *
 * Every panel in this portal talks to one of nine dispatch operations declared in
 * amplify/data/resource.ts (adminQuery, adminMutation, protectionQuery, and so on).
 * They all return `a.json()`, and they all signal a resolver-level failure by
 * putting a message in an `error` field of that payload rather than by rejecting.
 *
 * That last part is why this helper exists. TanStack Query decides between its
 * `data` and `error` channels by whether the query function rejects, so a payload
 * carrying `{ error: "..." }` would otherwise be delivered as a *successful*
 * result and every caller would have to re-check it by hand — which is what the
 * hand-rolled loaders did, and what they occasionally forgot to do.
 *
 * `unwrap` promotes those payload errors to rejections, so `error` in a component
 * means "this did not work" regardless of which layer said so.
 *
 * Usage:
 *
 *     const { data, isPending, error, refetch } = useQuery({
 *       queryKey: ["admin", "listVolumes"],
 *       queryFn: () =>
 *         unwrap<{ volumes?: Volume[] }>(
 *           dispatch("adminQuery", { action: "listVolumes" }),
 *         ),
 *     });
 *
 * Go through `dispatch` from `./dispatch`, not the generated client directly: it is
 * what checks the action name and its parameters. The operation is invoked at the
 * call site rather than passed in as a function, so the Amplify client keeps its
 * `this` binding.
 */

import { parseResponse } from "../utils/parseResponse";

/** The shape every dispatch operation resolves to. */
export interface PortalResponse {
  data?: unknown;
  errors?: readonly { message: string }[];
}

/**
 * Parse a dispatch response, rejecting when the operation reported a failure.
 *
 * @param pending The in-flight operation, already invoked.
 * @returns The parsed payload, or null when the operation returned no data.
 * @throws Error when the payload carries an `error` field, or when the payload is
 *   absent and GraphQL reported errors.
 */
export async function unwrap<T>(pending: Promise<PortalResponse>): Promise<T | null> {
  const response = await pending;
  const data = parseResponse<T & { error?: string }>(response);

  if (data?.error) {
    throw new Error(data.error);
  }
  if (!data && response.errors?.length) {
    throw new Error(response.errors.map((e) => e.message).join(", "));
  }
  return data;
}

/**
 * Turn a query error into the string the panels display.
 *
 * Panels rendered `error` as a plain string. TanStack hands back an `Error`, so
 * this keeps the call sites from repeating the same narrowing.
 */
export function errorMessage(error: unknown, fallback: string): string | null {
  if (!error) return null;
  return error instanceof Error ? error.message : fallback;
}
