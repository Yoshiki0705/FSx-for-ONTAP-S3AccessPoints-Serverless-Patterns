/**
 * Storage Browser tab — integrated into the Amplify portal.
 *
 * Uses @aws-amplify/ui-react-storage's StorageBrowser component
 * with the FSx for ONTAP S3 AP alias as the bucket target.
 *
 * Provides: file listing, folder navigation, drag-and-drop upload (max 5GB),
 * download, copy, delete, folder creation — all via S3 AP.
 *
 * Credentials come from Cognito Identity Pool (authenticated user).
 */
import { createManagedAuthAdapter, createStorageBrowser } from "@aws-amplify/ui-react-storage/browser";
import "@aws-amplify/ui-react-storage/styles.css";
import { fetchAuthSession } from "aws-amplify/auth";
import { portalSettings } from "../portal-settings";

const { StorageBrowser } = createStorageBrowser({
  config: createManagedAuthAdapter({
    credentialsProvider: async () => {
      // Use Cognito Identity Pool credentials from the authenticated session
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
    region: portalSettings.region,
    accountId: portalSettings.accountId,
    registerAuthListener: (_onAuthStateChange: () => void) => {
      // Called when auth state changes (e.g., sign out)
      // StorageBrowser will clear sensitive state automatically
    },
  }),
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
  return (
    <div className="storage-browser-tab">
      <div className="storage-browser-header">
        <h2>Upload & Manage Files</h2>
        <p className="storage-browser-description">
          Drag and drop files to upload, or browse and manage files directly.
          Changes are immediately visible via NFS/SMB.
        </p>
      </div>
      <StorageBrowser />
    </div>
  );
}
