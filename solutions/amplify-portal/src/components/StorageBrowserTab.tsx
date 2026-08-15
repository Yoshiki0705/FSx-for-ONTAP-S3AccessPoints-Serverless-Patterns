/**
 * Storage Browser tab — integrated into the Amplify portal.
 *
 * Uses @aws-amplify/ui-react-storage's StorageBrowser component
 * with the FSx for ONTAP S3 AP alias as the bucket target.
 *
 * Uses direct credentials mode (no S3 Access Grants required).
 * This avoids the ListCallerAccessGrants API call that fails
 * when Access Grants are not configured for the S3 AP.
 *
 * Provides: file listing, folder navigation, drag-and-drop upload (max 5GB),
 * download, copy, delete, folder creation — all via S3 AP.
 *
 * Credentials come from Cognito Identity Pool (authenticated user).
 */
import { createStorageBrowser } from "@aws-amplify/ui-react-storage/browser";
import "@aws-amplify/ui-react-storage/styles.css";
import { fetchAuthSession } from "aws-amplify/auth";
import { s3ApAlias, outputsRegion } from "../lib/portalOutputs";
import { useTranslation } from "../i18n";

const { StorageBrowser } = createStorageBrowser({
  config: {
    // Direct credentials mode — bypasses S3 Access Grants
    getLocationCredentials: async () => {
      const session = await fetchAuthSession();
      const credentials = session.credentials;
      if (!credentials) {
        throw new Error("No credentials available — user may not be authenticated");
      }
      return {
        credentials: {
          accessKeyId: credentials.accessKeyId,
          secretAccessKey: credentials.secretAccessKey,
          sessionToken: credentials.sessionToken ?? "",
          expiration: credentials.expiration ?? new Date(Date.now() + 3600_000),
        },
      };
    },
    // Provide the S3 AP as a pre-configured location
    listLocations: async () => {
      return {
        items: [
          {
            bucket: s3ApAlias,
            id: "fsxn-s3ap",
            permissions: ["delete", "get", "list", "write"] as const,
            prefix: "",
            type: "BUCKET" as const,
          },
        ],
        nextToken: undefined,
      };
    },
    region: outputsRegion,
    registerAuthListener: (_onAuthStateChange: () => void) => {
      // Called when auth state changes
    },
  },
});

/**
 * StorageBrowserTab — renders the Storage Browser component
 * configured to browse the FSx for ONTAP S3 AP.
 *
 * Upload: drag-and-drop or file picker (max 5GB per S3 AP PutObject limit)
 * Download: click file → download via browser
 * Delete: select files → delete
 * Copy: select file → copy to another location
 */
export function StorageBrowserTab() {
  const { t } = useTranslation();
  if (!s3ApAlias) {
    return (
      <div className="storage-browser-tab">
        <div className="storage-browser-header">
          <h2>{t("uploadTitle")}</h2>
          <p className="storage-browser-description">{t("sbNotConfigured")}</p>
        </div>
      </div>
    );
  }

  return (
    <div className="storage-browser-tab">
      <div className="storage-browser-header">
        <h2>{t("uploadTitle")}</h2>
        <p className="storage-browser-description">
          {t("uploadDesc")}
        </p>
      </div>
      <StorageBrowser />
    </div>
  );
}
