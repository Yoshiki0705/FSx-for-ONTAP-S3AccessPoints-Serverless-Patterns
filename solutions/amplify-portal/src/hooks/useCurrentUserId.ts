/**
 * The signed-in user's Cognito subject.
 *
 * The agent registry authorizes edits and deletes by comparing `createdBy` with
 * the caller's subject, which AppSync injects server-side. The UI could not make
 * the same comparison, so it offered Edit and Delete on agents shared by other
 * people and turned an authorization refusal into the only feedback.
 *
 * Read from the ID token for the same reason as `useStorageAdmin`: the value is
 * already in the session, and asking the backend who you are would be a round
 * trip to learn something the token already says.
 *
 * Returns `null` while the session is loading, so a caller can distinguish
 * "not the owner" from "not known yet".
 */
import { useEffect, useState } from "react";
import { fetchAuthSession } from "aws-amplify/auth";

export function useCurrentUserId(): string | null {
  const [userId, setUserId] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const session = await fetchAuthSession();
        const sub = session.tokens?.idToken?.payload.sub;
        if (!cancelled) setUserId(typeof sub === "string" ? sub : null);
      } catch {
        if (!cancelled) setUserId(null);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  return userId;
}
