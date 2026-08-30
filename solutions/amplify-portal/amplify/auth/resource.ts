import { defineAuth } from "@aws-amplify/backend";

import { config } from "../portal-config";
import { ALL_PORTAL_GROUPS } from "../portal-groups";

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
   * Two axes now, not one. `storage-admin` keeps its name and its meaning; the
   * additions are the other three roles and the two scopes. See
   * `amplify/portal-groups.ts` for why the axes are separate.
   *
   * Declaring a group is not granting it. Every deployment gets all six, and a user
   * holds whichever were granted with `admin-add-user-to-group`. A user holding none
   * behaves exactly as before, which is what keeps this change compatible: the
   * stricter authorization rules are emitted only when `enforceRoles` is set.
   *
   * `amplify/data/resource.ts` guards the resource-management, ARP, snapshot and
   * Athena endpoints with `allow.groups([ROLE_STORAGE_ADMIN])`, and `App.tsx` hides
   * the matching sections when the session lacks it. Declaring the group here is what
   * makes a fresh deployment reachable: it was once missing, so it existed only where
   * somebody had created it by hand, and a newly deployed portal came up with the
   * administrative sections simply absent — which reads as "not built yet" rather than
   * as a misconfiguration.
   */
  groups: [...ALL_PORTAL_GROUPS],

  /**
   * Multi-factor authentication, from configuration rather than from a literal.
   *
   * `OPTIONAL` is the default and is what shipped. Worth reading precisely: `OPTIONAL`
   * means each user decides, so it is `OFF` for everyone who does not go looking for
   * it. A deployment that needs MFA to be true of every session wants `REQUIRED`.
   */
  multifactor:
    config.signIn.mfa === "OFF" ? { mode: "OFF" } : { mode: config.signIn.mfa, totp: true },

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
