/**
 * Typed access to the portal's generic dispatch endpoints.
 *
 * The endpoints take an action name and a JSON blob. That shape is what let a lock
 * button ship having never worked: it sent a snapshot name and a day count to an
 * action that reads a UUID and an absolute instant, and neither the compiler nor
 * the linter had anything to compare the call against.
 *
 * Going through here gives the compiler two things it did not have:
 *
 *   - the action name is a union of the actions its endpoint's handler dispatches,
 *     so a name that is misspelled or has moved is a build error
 *   - the parameters are the ones that action reads, with identifiers, instants and
 *     durations branded, so a volume name cannot be passed where a UUID belongs
 *
 * The maps come from `dispatchActions.ts`, which is generated from the handlers and
 * checked against them by `scripts/portal_action_types.py`. The parameter *names*
 * are still checked separately, by `scripts/check_portal_action_params.py`, because
 * a generated type and the handler it was generated from can drift apart.
 */
import { generateClient } from "aws-amplify/data";
import type { Schema } from "../../amplify/data/resource";
import { parseResponse } from "../utils/parseResponse";
import type { PortalResponse } from "./portalQuery";
import type { ActionOf, DispatchEndpoint, ParamsOf } from "./dispatchActions";

const client = generateClient<Schema>();

/**
 * One legal call to an endpoint: an action, and the parameters that action takes.
 *
 * This is a union over the endpoint's actions rather than a pair of generic
 * arguments, and the difference is the whole mechanism. TypeScript infers type
 * arguments all-or-nothing, so a signature of `<T, A extends Action>(action: A,
 * params: ParamsOf<A>)` cannot be called as `dispatch<Response>(...)`: naming the
 * response type means `A` is no longer inferred, it falls back to its constraint,
 * and `params` widens to the union of every action's parameters — which accepts
 * nearly anything. A first attempt in that shape type-checked the whole portal
 * without a single complaint, which is how it was found out.
 *
 * Passing one object lets the `action` property select the union member, so the
 * response type can be named without giving up the parameter check.
 *
 * `params` is optional exactly when every one of its properties is, so a listing
 * call need not write `params: {}` while `resizeVolume` cannot omit its UUID.
 */
export type DispatchCall<E extends DispatchEndpoint> = {
  [A in ActionOf<E>]: Record<string, never> extends ParamsOf<E, A>
    ? { action: A; params?: ParamsOf<E, A> }
    : { action: A; params: ParamsOf<E, A> };
}[ActionOf<E>];

/**
 * Call a dispatch endpoint and return the raw response.
 *
 * Compose with `unwrap` inside a TanStack `queryFn`, which is where a payload-level
 * error should become a rejection:
 *
 *     unwrap<{ volumes?: Volume[] }>(dispatch("adminQuery", { action: "listVolumes" }))
 */
export async function dispatch<E extends DispatchEndpoint>(
  endpoint: E,
  call: DispatchCall<E>
): Promise<PortalResponse> {
  const { action, params } = call;
  // The endpoint names are the field names of the generated client, and
  // `DispatchEndpoint` is derived from the same schema, so this lookup is sound
  // even though the client's own types do not express the query/mutation split in a
  // form a generic can follow.
  const operations = { ...client.queries, ...client.mutations } as unknown as Record<
    string,
    (input: { action: string; params: string }) => Promise<PortalResponse>
  >;
  const operation = operations[endpoint];
  if (!operation) {
    throw new Error(`No dispatch endpoint named ${endpoint}`);
  }
  return operation({ action, params: JSON.stringify(params ?? {}) });
}

/**
 * Call a dispatch endpoint and return the parsed payload.
 *
 * A payload-level `error` stays in the object rather than being thrown, which is
 * what the mutation call sites expect: they show the message beside the form.
 *
 * `T` is a claim by the caller, not something derived. The handlers build their
 * responses ad hoc, so there is nothing on that side to derive it from — the
 * guarantee here is about the request.
 */
async function dispatchFor<T, E extends DispatchEndpoint>(
  endpoint: E,
  call: DispatchCall<E>
): Promise<(T & { error?: string }) | null> {
  return parseResponse<T & { error?: string }>(await dispatch(endpoint, call));
}

/**
 * One reader per endpoint, because the endpoint cannot be a type parameter here.
 *
 * The all-or-nothing inference rule bites a second time: `dispatchFor<T, E>(endpoint,
 * call)` cannot be called as `dispatchFor<Volume[]>("adminQuery", ...)`, since naming
 * the response type means `E` must be named too. Fixing `E` per function leaves `T`
 * as the only type argument, so a call site names the response type and nothing else.
 *
 * Each returns the parsed payload with any `error` left in place, which is what the
 * panels show beside their forms.
 */
export const adminQuery = <T,>(call: DispatchCall<"adminQuery">) => dispatchFor<T, "adminQuery">("adminQuery", call);
export const adminMutate = <T,>(call: DispatchCall<"adminMutation">) =>
  dispatchFor<T, "adminMutation">("adminMutation", call);
export const arpQuery = <T,>(call: DispatchCall<"arpQuery">) => dispatchFor<T, "arpQuery">("arpQuery", call);
export const arpMutate = <T,>(call: DispatchCall<"arpMutation">) => dispatchFor<T, "arpMutation">("arpMutation", call);
export const protectionQuery = <T,>(call: DispatchCall<"protectionQuery">) =>
  dispatchFor<T, "protectionQuery">("protectionQuery", call);
export const protectionMutate = <T,>(call: DispatchCall<"protectionMutation">) =>
  dispatchFor<T, "protectionMutation">("protectionMutation", call);
export const fileQuery = <T,>(call: DispatchCall<"fileQuery">) => dispatchFor<T, "fileQuery">("fileQuery", call);
export const fileMutate = <T,>(call: DispatchCall<"fileMutation">) =>
  dispatchFor<T, "fileMutation">("fileMutation", call);
export const agentQuery = <T,>(call: DispatchCall<"agentQuery">) => dispatchFor<T, "agentQuery">("agentQuery", call);
export const thumbnailQuery = <T,>(call: DispatchCall<"thumbnailQuery">) =>
  dispatchFor<T, "thumbnailQuery">("thumbnailQuery", call);

// No helper for `folderMutation`: the folder download Lambda never reads `action`,
// so it does one thing whatever it is sent and there is no action set to constrain.
// Its single call site stays on the generated client.
