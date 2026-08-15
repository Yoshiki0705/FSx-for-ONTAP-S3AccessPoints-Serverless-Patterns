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
import { createStorageBrowser, defaultActionConfigs } from "@aws-amplify/ui-react-storage/browser";
import type { LocationData } from "@aws-amplify/ui-react-storage/browser";
import "@aws-amplify/ui-react-storage/styles.css";
import { fetchAuthSession } from "aws-amplify/auth";
import { fileQuery } from "../lib/dispatch";
import { s3ApAlias, outputsRegion } from "../lib/portalOutputs";
import {
  createFolderWithoutConditionalWrite,
  uploadWithoutConditionalWrite,
} from "../lib/storageBrowserWriteHandlers";
import { useTranslation } from "../i18n";

/** One access point as `listAccessPoints` reports it. */
type DiscoveredAccessPoint = {
  alias: string;
  name: string;
  lifecycle: string;
  origin: string;
  isDefault: boolean;
};

/**
 * Locations from the backend, or null when it could not answer.
 *
 * Only `AVAILABLE` access points are offered: the others exist but cannot serve
 * data operations, and listing one produces an error the user cannot act on.
 * `UNKNOWN` is kept, because that is what the handler reports when the FSx
 * describe call itself failed, and dropping it would hide a configured alias for
 * a reason that has nothing to do with the alias.
 */
async function discoverLocations() {
  try {
    const parsed = await fileQuery<{ accessPoints?: DiscoveredAccessPoint[] }>({
      action: "listAccessPoints",
    });
    const usable = (parsed?.accessPoints ?? []).filter(
      (ap) => ap.alias && (ap.lifecycle === "AVAILABLE" || ap.lifecycle === "UNKNOWN")
    );
    if (usable.length === 0) return null;
    return usable.map(
      (ap): LocationData => ({
        bucket: ap.alias,
        // Stable across renders, and distinct per access point so the component
        // does not treat two locations as the same one.
        id: `fsxn-s3ap-${ap.alias}`,
        permissions: ["delete", "get", "list", "write"],
        prefix: "",
        type: "BUCKET",
      })
    );
  } catch {
    return null;
  }
}

const { StorageBrowser } = createStorageBrowser({
  // The two write handlers are replaced because the vendor ones ask S3 for a
  // conditional write (`if-none-match: *`), which this access point answers with
  // 501 -- so every upload and every folder creation failed. Everything else,
  // including the action list items and their views, stays as shipped. See
  // src/lib/storageBrowserWriteHandlers.ts.
  actions: {
    default: {
      ...defaultActionConfigs,
      createFolder: {
        ...defaultActionConfigs.createFolder,
        handler: createFolderWithoutConditionalWrite,
      },
      upload: { ...defaultActionConfigs.upload, handler: uploadWithoutConditionalWrite },
    },
  },
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
    /*
     * The locations the caller may browse, asked of the backend rather than
     * hardcoded here.
     *
     * This used to return the one alias baked in at build time, which says
     * nothing about whether that access point still exists: a deleted or
     * MISCONFIGURED one looks identical in a config file to a working one, and
     * the failure arrives later as an error against an access point the operator
     * believes in. The `listAccessPoints` action answers from
     * `DescribeS3AccessPointAttachments`, and narrows the answer to the aliases
     * the caller's Cognito groups map to, so asking does not widen access.
     *
     * On any failure it falls back to the alias in the generated outputs. A
     * portal that cannot browse at all is worse than one browsing an alias whose
     * state could not be confirmed.
     */
    listLocations: async () => {
      const items = (await discoverLocations()) ?? [
        {
          bucket: s3ApAlias,
          id: "fsxn-s3ap",
          permissions: ["delete", "get", "list", "write"] as const,
          prefix: "",
          type: "BUCKET" as const,
        },
      ];
      return { items, nextToken: undefined };
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
