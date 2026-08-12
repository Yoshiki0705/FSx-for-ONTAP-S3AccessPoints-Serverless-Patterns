import { defineAuth } from "@aws-amplify/backend";

/**
 * Authentication resource for the File Portal.
 *
 * Default: Cognito User Pool with email sign-in.
 * For enterprise environments, configure SAML/OIDC federation
 * by uncommenting the external provider section below.
 *
 * See: https://docs.amplify.aws/gen2/build-a-backend/auth/
 */
export const auth = defineAuth({
  loginWith: {
    email: {
      // Email verification for self-service sign-up
      verificationEmailStyle: "CODE",
      verificationEmailSubject: "FSx for ONTAP File Portal - Verification Code",
    },
  },

  /**
   * The group that gates every administrative operation.
   *
   * `amplify/data/resource.ts` guards the resource-management, ARP, snapshot and
   * Athena endpoints with `allow.groups(["storage-admin"])`, and `App.tsx` hides
   * the matching sections when the session lacks it. The group itself was missing
   * here, so it existed only where somebody had created it by hand: a sandbox
   * that had been running a while had it, and a freshly deployed one did not.
   * Nothing failed loudly — the portal came up with the admin sections simply
   * absent, which reads as "not built yet" rather than "misconfigured".
   *
   * Declaring it means a fresh deploy is reachable. Membership is still granted
   * deliberately, per user:
   *
   *   aws cognito-idp admin-add-user-to-group \
   *     --user-pool-id <pool> --username <user> --group-name storage-admin
   */
  groups: ["storage-admin"],

  // Multi-factor authentication (recommended for production)
  multifactor: {
    mode: "OPTIONAL",
    totp: true,
  },

  // User attributes
  userAttributes: {
    preferredUsername: {
      mutable: true,
      required: false,
    },
  },

  // -------------------------------------------------------------------
  // Enterprise IdP Integration (SAML / OIDC)
  // -------------------------------------------------------------------
  // Uncomment and configure one of the following for enterprise SSO:
  //
  // SAML Provider (e.g., Azure AD, Okta, ADFS):
  // externalProviders: {
  //   saml: {
  //     name: "EnterpriseIdP",
  //     metadata: {
  //       // Option 1: Metadata URL
  //       metadataUrl: "https://your-idp.example.com/metadata.xml",
  //       // Option 2: Metadata content (paste XML directly)
  //       // metadataContent: "<EntityDescriptor>...</EntityDescriptor>",
  //     },
  //     attributeMapping: {
  //       email: "http://schemas.xmlsoap.org/ws/2005/05/identity/claims/emailaddress",
  //       preferredUsername: "http://schemas.xmlsoap.org/ws/2005/05/identity/claims/name",
  //     },
  //   },
  //   callbackUrls: ["http://localhost:5173/", "https://your-domain.amplifyapp.com/"],
  //   logoutUrls: ["http://localhost:5173/", "https://your-domain.amplifyapp.com/"],
  // },
  //
  // OIDC Provider (e.g., Keycloak, Auth0):
  // externalProviders: {
  //   oidc: [{
  //     name: "EnterpriseOIDC",
  //     clientId: "<YOUR_OIDC_CLIENT_ID>",
  //     clientSecret: "<YOUR_OIDC_CLIENT_SECRET>",
  //     issuerUrl: "https://your-oidc-issuer.example.com",
  //     scopes: ["openid", "email", "profile"],
  //     attributeMapping: {
  //       email: "email",
  //       preferredUsername: "preferred_username",
  //     },
  //   }],
  //   callbackUrls: ["http://localhost:5173/", "https://your-domain.amplifyapp.com/"],
  //   logoutUrls: ["http://localhost:5173/", "https://your-domain.amplifyapp.com/"],
  // },
  // -------------------------------------------------------------------
});
