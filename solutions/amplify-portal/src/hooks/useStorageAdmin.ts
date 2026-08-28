/**
 * Whether the signed-in user is in the `storage-admin` Cognito group.
 *
 * The admin sections are authorized server-side: `adminQuery` and `adminMutation`
 * are declared `allow.groups(["storage-admin"])`, so a user outside the group
 * cannot reach them. Nothing checked it in the UI, though, so every authenticated
 * user saw the Resource Management card grid, opened a panel, and got an
 * authorization error from each of the twenty. That is not a security hole — the
 * server refused correctly — but a menu that leads only to errors is a menu that
 * lies about what the account can do.
 *
 * Returns `null` while the session is still loading, so a caller can tell "not an
 * admin" from "not known yet" and avoid showing the section and then removing it.
 *
 * Kept as its own hook because four components ask only this question and reading a
 * boolean is clearer there than destructuring one field. It derives from
 * `usePortalRole` rather than reading the session a second time: two hooks parsing the
 * same claim is the shape that drifts, and the group name now comes from
 * `amplify/portal-groups.ts` instead of a third copy of the string.
 */
import { ROLE_STORAGE_ADMIN } from "../../amplify/portal-groups";
import { usePortalRole } from "./usePortalRole";

/** The group the schema requires for every admin dispatch endpoint. */
export const STORAGE_ADMIN_GROUP = ROLE_STORAGE_ADMIN;

export function useStorageAdmin(): boolean | null {
  const capabilities = usePortalRole();
  return capabilities === null ? null : capabilities.isAdmin;
}
