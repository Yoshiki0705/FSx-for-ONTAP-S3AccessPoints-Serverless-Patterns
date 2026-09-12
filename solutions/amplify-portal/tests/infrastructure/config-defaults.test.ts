// @vitest-environment node
//
// The portal's defaults, asserted by loading the configuration rather than by reading it.
//
// Source-text assertions elsewhere pin the expressions; this pins the answer. The two are
// not the same check: a source assertion confirms that `!== "false"` is written down, and
// this confirms what an unset environment actually resolves to.
//
// Node environment, not jsdom: `portal-config` is reached from `backend.ts`, and
// `@aws-amplify/backend` refuses to load in a browser environment.
//
// `amplify/portal-config.ts` is gitignored and CI copies `portal-config.example.ts` over
// it, so everything here has to hold in both shapes. It now does in a stronger sense than
// before: until 2026-09-07 the example held bare literals and ignored the environment
// entirely, which made an opt-out assertion pass locally and fail in CI, and made the
// misspelling case below a real test of the polarity only on a machine with the real file.
// The example gained the same environment layer -- the reason being that the variables this
// guide and `backend.ts` tell you to set were silently ignored on every copied config -- so
// the opt-out is now assertable against either file, and is asserted below.
import { describe, it, expect, vi, beforeEach } from "vitest";

beforeEach(() => {
  vi.resetModules();
  vi.unstubAllEnvs();
});

/** Load the configuration under a given environment. */
async function loadConfig(env: Record<string, string> = {}) {
  for (const [name, value] of Object.entries(env)) vi.stubEnv(name, value);
  const module = await import("../../amplify/portal-config");
  return module.config;
}

describe("Portal configuration defaults", () => {
  it("closes registration and enforces roles when nothing is set", async () => {
    // Both were the other way round, on a compatibility argument. Nothing downstream
    // depends on this repository, so the default is the safe one.
    const config = await loadConfig();
    expect(config.signIn.selfSignUpEnabled).toBe(false);
    expect(config.enforceRoles).toBe(true);
  });

  it("withholds the AI endpoints and share links from outside members", async () => {
    const config = await loadConfig();
    expect(config.externalDefaults.aiEnabled).toBe(false);
    // Empty denies every role, since a role absent from the map is denied.
    expect(config.externalDefaults.shareLinksByRole).toEqual({});
  });

  it("stays restrictive when the variable is misspelled", async () => {
    // The reason the polarity was chosen. `AMPLIFY_PORTAL_ENFORCE_ROLES=treu` used to
    // read as "not true" and silently removed the authorization rules; now the word that
    // has to be spelled correctly is the one that removes them.
    const config = await loadConfig({
      AMPLIFY_PORTAL_SELF_SIGN_UP: "ture",
      AMPLIFY_PORTAL_ENFORCE_ROLES: "flase",
      AMPLIFY_PORTAL_EXTERNAL_AI_ENABLED: "yes",
    });
    expect(config.signIn.selfSignUpEnabled).toBe(false);
    expect(config.enforceRoles).toBe(true);
    expect(config.externalDefaults.aiEnabled).toBe(false);
  });

  it("opts out when the word that leaves the restrictive state is spelled correctly", async () => {
    // The other half of the polarity: a default that cannot be turned off is not a
    // default. Assertable in both shapes only since the example gained the environment
    // layer; before that this would have failed in CI while passing locally.
    const config = await loadConfig({
      AMPLIFY_PORTAL_SELF_SIGN_UP: "true",
      AMPLIFY_PORTAL_ENFORCE_ROLES: "false",
      AMPLIFY_PORTAL_EXTERNAL_AI_ENABLED: "true",
    });
    expect(config.signIn.selfSignUpEnabled).toBe(true);
    expect(config.enforceRoles).toBe(false);
    expect(config.externalDefaults.aiEnabled).toBe(true);
  });

  it("reads the variables the setup guide tells you to set", async () => {
    // The regression this guards. The guide, the error messages in `backend.ts` and the
    // header of the example all name these; on a copied config none of them were read, so
    // a second sandbox in a shared VPC still tried to own the DynamoDB gateway endpoint
    // and rolled the data stack back on the route it collided with.
    const config = await loadConfig({
      AMPLIFY_PORTAL_DDB_GW_ENDPOINT_EXISTS: "1",
      AMPLIFY_PORTAL_VPC_ID: "vpc-0123456789abcdef0",
      AMPLIFY_PORTAL_VPC_ROUTE_TABLE_IDS: "rtb-0123456789abcdef0, rtb-00112233445566778",
      AMPLIFY_PORTAL_SFN_ARN: "arn:aws:states:ap-northeast-1:111122223333:stateMachine:uc1",
    });
    expect(config.dynamoDbGatewayEndpointExists).toBe(true);
    expect(config.vpcId).toBe("vpc-0123456789abcdef0");
    // Split and trimmed: a whitespace-only entry surviving as a list member would satisfy
    // the synth guard in `backend.ts` while naming no route table.
    expect(config.vpcRouteTableIds).toEqual([
      "rtb-0123456789abcdef0",
      "rtb-00112233445566778",
    ]);
    expect(config.stateMachineArn).toBe(
      "arn:aws:states:ap-northeast-1:111122223333:stateMachine:uc1",
    );
  });

  it("leaves the path prefixes undefined rather than empty when unset", async () => {
    // `{}` and undefined are different instructions to `backend.ts`: undefined derives the
    // prefixes from `groupApMapping`, `{}` reads as "configured, restricting nothing".
    const config = await loadConfig();
    expect(config.groupPathPrefixes).toBeUndefined();
  });
});
