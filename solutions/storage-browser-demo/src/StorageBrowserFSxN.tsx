/**
 * Storage Browser for S3 — configured to browse FSx for ONTAP via S3 Access Point alias.
 *
 * Method 2: Managed Auth Adapter (custom credentials provider).
 * The S3 AP alias is used as the "bucket" name in the location configuration.
 *
 * For production: replace the credentialsProvider with Cognito Identity Pool
 * or a backend API that returns STS AssumeRole temporary credentials.
 */
import { createManagedAuthAdapter, createStorageBrowser } from '@aws-amplify/ui-react-storage/browser';
import '@aws-amplify/ui-react-storage/styles.css';

// ===== CONFIGURATION — Update these values for your environment =====
const CONFIG = {
  /**
   * FSx for ONTAP S3 AP alias.
   * Find with: aws fsx describe-s3-access-point-attachments \
   *   --query 'S3AccessPointAttachments[?Lifecycle==`AVAILABLE`].S3AccessPoint.Alias' \
   *   --region ap-northeast-1
   */
  s3ApAlias: 'verification-tes-fpg5t76dgh3xchkrudk6yc4jhgzz1apn1b-ext-s3alias',

  /** AWS region (must match the S3 AP region) */
  region: 'ap-northeast-1',

  /** AWS account ID (aws sts get-caller-identity --query Account) */
  accountId: '123456789012',
};
// ===== END CONFIGURATION =====

export const { StorageBrowser } = createStorageBrowser({
  config: createManagedAuthAdapter({
    credentialsProvider: async () => {
      /**
       * Demo: reads credentials from environment / local backend.
       * For production: use Cognito Identity Pool getCredentialsForIdentity
       * or a /api/credentials backend endpoint returning STS temp creds.
       *
       * IMPORTANT: Never embed long-term credentials in frontend code.
       */
      const response = await fetch('/api/credentials');
      if (!response.ok) {
        throw new Error(`Credentials endpoint returned ${response.status}`);
      }
      const creds = await response.json();
      return {
        credentials: {
          accessKeyId: creds.accessKeyId,
          secretAccessKey: creds.secretAccessKey,
          sessionToken: creds.sessionToken,
          expiration: new Date(creds.expiration),
        },
      };
    },
    region: CONFIG.region,
    accountId: CONFIG.accountId,
    registerAuthListener: (_onAuthStateChange) => {
      // Call onAuthStateChange() when user logs out to clear sensitive state
    },
  }),
});
