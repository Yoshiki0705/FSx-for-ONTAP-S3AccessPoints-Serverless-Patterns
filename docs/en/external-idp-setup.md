# External IdP Setup — SAML / OIDC Federation

> 🌐 Language: **English** | [日本語](../ja/external-idp-setup.md)

> Connect the File Portal to your organization's identity provider (AD FS, Okta, Azure AD, etc.)

## Overview

The portal uses Amazon Cognito User Pool for authentication. By default, users sign up with email/password directly in Cognito. For enterprise and public sector deployments, you can federate with an external Identity Provider (IdP) via SAML 2.0 or OIDC.

```
User → Cognito Hosted UI → External IdP (SAML/OIDC) → Cognito → AppSync
                                                              ↓
                                                     Group claim → storage-admin
```

## Prerequisites

| Item | Required |
|------|:---:|
| Cognito User Pool (deployed via sandbox) | ✅ |
| External IdP configured (AD FS / Okta / Azure AD / Google Workspace) | ✅ |
| Custom domain for Cognito (production) | Recommended |

## Step 1: Configure IdP in Cognito Console

### Option A: SAML 2.0 (AD FS, Okta)

1. In your IdP, create a new SAML application:
   - **ACS URL**: `https://<cognito-domain>.auth.<region>.amazoncognito.com/saml2/idpresponse`
   - **Entity ID**: `urn:amazon:cognito:sp:<user-pool-id>`
   - **Name ID**: Email
   - **Attributes**: Map `groups` claim to IdP groups

2. Download the IdP SAML metadata XML

3. In Cognito Console → User Pool → Sign-in Experience → Federated sign-in:
   - Add identity provider → SAML
   - Upload metadata XML
   - Map attributes:
     - `email` → Cognito `email`
     - `groups` → Cognito `custom:groups` (or use IdP-to-group mapping)

### Option B: OIDC (Azure AD, Google Workspace)

1. In Azure AD / Google Workspace, register an OAuth application:
   - **Redirect URI**: `https://<cognito-domain>.auth.<region>.amazoncognito.com/oauth2/idpresponse`
   - **Scopes**: `openid email profile`
   - Note the Client ID and Client Secret

2. In Cognito Console → Federated sign-in:
   - Add identity provider → OpenID Connect
   - Provider name: `AzureAD` (or `GoogleWorkspace`)
   - Client ID / Secret from step 1
   - Issuer URL: `https://login.microsoftonline.com/<tenant-id>/v2.0`
   - Attribute mapping: `email`, `name`, `groups`

## Step 2: Map IdP Groups to Cognito Groups

The portal uses `storage-admin` Cognito group for admin access. Map your IdP groups:

| IdP Group | Cognito Group | Portal Access |
|-----------|--------------|---------------|
| `StorageAdmins` / `IT-Infrastructure` | `storage-admin` | Full admin (ONTAP operations) |
| `AllUsers` / `Everyone` | (authenticated) | Read + AI processing |

### Automatic group assignment via Lambda trigger

Add a Cognito Pre Token Generation Lambda trigger:

```python
def handler(event, context):
    """Map IdP groups to Cognito groups in the token."""
    idp_groups = event["request"]["groupConfiguration"].get("groupsToOverride", [])

    # Map IdP group names to Cognito group names
    GROUP_MAPPING = {
        "StorageAdmins": "storage-admin",
        "IT-Infrastructure": "storage-admin",
        "NAS-Admins": "storage-admin",
    }

    cognito_groups = []
    for idp_group in idp_groups:
        if idp_group in GROUP_MAPPING:
            cognito_groups.append(GROUP_MAPPING[idp_group])

    event["response"]["claimsOverrideDetails"] = {
        "groupOverrideDetails": {
            "groupsToOverride": cognito_groups,
        }
    }
    return event
```

## Step 3: Update Amplify Auth Configuration

In `amplify/auth/resource.ts`, add the external provider:

```typescript
import { defineAuth } from "@aws-amplify/backend";

export const auth = defineAuth({
  loginWith: {
    email: true,
    externalProviders: {
      saml: {
        name: "CorporateADFS",
        metadata: {
          metadataContent: "https://adfs.example.com/FederationMetadata/2007-06/FederationMetadata.xml",
          metadataType: "URL",
        },
        attributeMapping: {
          email: "http://schemas.xmlsoap.org/ws/2005/05/identity/claims/emailaddress",
          preferredUsername: "http://schemas.xmlsoap.org/ws/2005/05/identity/claims/name",
        },
      },
      // OR for OIDC:
      // oidc: [{
      //   name: "AzureAD",
      //   clientId: "<client-id>",
      //   clientSecret: "<client-secret>",  // Use Secrets Manager in production
      //   issuerUrl: "https://login.microsoftonline.com/<tenant-id>/v2.0",
      //   attributeMapping: { email: "email", preferredUsername: "name" },
      // }],
      callbackUrls: ["http://localhost:5173/", "https://your-domain.com/"],
      logoutUrls: ["http://localhost:5173/", "https://your-domain.com/"],
    },
  },
  groups: ["storage-admin"],
});
```

## Step 4: Update Frontend Sign-In

The portal's sign-in page uses Amplify UI `<Authenticator>`. For federated sign-in, add a provider button:

```typescript
// In App.tsx or auth wrapper
import { signInWithRedirect } from "aws-amplify/auth";

// Add button to sign-in page
<button onClick={() => signInWithRedirect({ provider: "CorporateADFS" })}>
  Sign in with Corporate SSO
</button>
```

## Security Considerations

- **Token validation**: AppSync validates JWT tokens from Cognito. Federated tokens include the IdP source.
- **Group claims**: Ensure your IdP includes group membership in the SAML assertion or OIDC token.
- **MFA**: Configure MFA at the IdP level (Cognito MFA is bypassed for federated users).
- **Session duration**: Cognito token lifetime is configurable (default: 1 hour access, 30 days refresh).

## Tested IdP Configurations

| IdP | Protocol | Status | Notes |
|-----|----------|:---:|-------|
| AD FS (Windows Server 2019+) | SAML 2.0 | Documented | Standard SAML app registration |
| Okta | SAML 2.0 / OIDC | Documented | Both protocols supported |
| Azure AD (Entra ID) | OIDC | Documented | Use v2.0 endpoint |
| Google Workspace | OIDC | Documented | Custom SAML app in Admin Console |
| AWS IAM Identity Center | SAML 2.0 | Documented | Custom SAML application |

## References

- [Amplify Gen2: External login providers](https://docs.amplify.aws/gen2/build-a-backend/auth/concepts/external-identity-providers/)
- [Cognito User Pool SAML federation](https://docs.aws.amazon.com/cognito/latest/developerguide/cognito-user-pools-saml-idp.html)
- [Cognito User Pool OIDC federation](https://docs.aws.amazon.com/cognito/latest/developerguide/cognito-user-pools-oidc-idp.html)
