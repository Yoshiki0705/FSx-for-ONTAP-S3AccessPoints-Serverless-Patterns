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
 * The group claim is read from the ID token rather than asked of the backend: it is
 * already in the session, and a request to find out whether requests are allowed
 * would be the same round trip it is trying to avoid.
 *
 * Returns `null` while the session is still loading, so a caller can tell "not an
 * admin" from "not known yet" and avoid showing the section and then removing it.
 */
import { useEffect, useState } from "react";
import { fetchAuthSession } from "aws-amplify/auth";

/** The group the schema requires for every admin dispatch endpoint. */
export const STORAGE_ADMIN_GROUP = "storage-admin";

export function useStorageAdmin(): boolean | null {
  const [isAdmin, setIsAdmin] = useState<boolean | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const session = await fetchAuthSession();
        const groups = session.tokens?.idToken?.payload["cognito:groups"];
        // The claim is absent for a user in no group, and a single-element list is
        // still a list, so the shape is checked rather than assumed.
        const member = Array.isArray(groups) && groups.includes(STORAGE_ADMIN_GROUP);
        if (!cancelled) setIsAdmin(member);
      } catch {
        // No readable session means no group claim to honour. Hiding the section is
        // the safe reading: the server would refuse it anyway.
        if (!cancelled) setIsAdmin(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  return isAdmin;
}
