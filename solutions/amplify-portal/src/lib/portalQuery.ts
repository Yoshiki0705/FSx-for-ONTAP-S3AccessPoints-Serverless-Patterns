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

/** The fields a handler adds beside `error` to say *which* way it failed. */
export interface FailureDiagnosis {
  /** One of the classes in shared/ontap_diagnosis.py. */
  errorClass?: string;
  /** The HTTP status, when the far side answered at all. */
  errorStatus?: number;
  /** ONTAP's own error code. */
  errorCode?: string;
}

/** The payload fields `unwrap` inspects, on top of whatever the caller asked for. */
type FailurePayload = { error?: string } & FailureDiagnosis;

/**
 * A resolver-reported failure, with the diagnosis attached.
 *
 * Promoting the payload error to a rejection is what makes TanStack's `error`
 * channel mean "this did not work" (see the module comment). Doing that with a
 * bare `Error` also threw away everything except the message, so a panel could
 * only ever render one piece of guidance for five different causes — which is how
 * a rejected password came to be displayed as a VPC problem.
 */
export class DispatchError extends Error implements FailureDiagnosis {
  readonly errorClass?: string;
  readonly errorStatus?: number;
  readonly errorCode?: string;

  constructor(message: string, diagnosis: FailureDiagnosis = {}) {
    super(message);
    this.name = "DispatchError";
    this.errorClass = diagnosis.errorClass;
    this.errorStatus = diagnosis.errorStatus;
    this.errorCode = diagnosis.errorCode;
  }
}

/**
 * Parse a dispatch response, rejecting when the operation reported a failure.
 *
 * @param pending The in-flight operation, already invoked.
 * @returns The parsed payload, or null when the operation returned no data.
 * @throws DispatchError when the payload carries an `error` field, or when the
 *   payload is absent and GraphQL reported errors.
 */
export async function unwrap<T>(pending: Promise<PortalResponse>): Promise<T | null> {
  const response = await pending;
  const data = parseResponse<T & FailurePayload>(response);

  if (data?.error) {
    throw new DispatchError(data.error, data);
  }
  if (!data && response.errors?.length) {
    throw new DispatchError(response.errors.map((e) => e.message).join(", "));
  }
  return data;
}

/**
 * The diagnosis a query error carries, or an empty object.
 *
 * Empty rather than null so a call site can spread it into the notice without a
 * branch: a handler that has not been migrated, or an older deployment, then
 * simply renders the general guidance.
 */
export function failureDiagnosis(error: unknown): FailureDiagnosis {
  if (!(error instanceof DispatchError)) return {};
  return {
    errorClass: error.errorClass,
    errorStatus: error.errorStatus,
    errorCode: error.errorCode,
  };
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
