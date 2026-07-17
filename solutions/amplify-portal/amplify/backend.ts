import { defineBackend } from "@aws-amplify/backend";
import { auth } from "./auth/resource";
import { data } from "./data/resource";
import { stepFunctionsStack } from "./custom/step-functions";

/**
 * FSx for ONTAP File Portal — Amplify Gen2 Backend
 *
 * Architecture:
 *   defineAuth (Cognito + SAML/OIDC)
 *   defineData (AppSync GraphQL API)
 *     → HTTP Resolver → Step Functions (existing ASL workflows)
 *   CDK Custom Resource (Step Functions state machine reference)
 *
 * The backend integrates with existing serverless patterns
 * without modifying them. It references deployed Step Functions
 * state machines and invokes them via AppSync HTTP resolvers.
 */
const backend = defineBackend({
  auth,
  data,
});

// Add Step Functions custom resource stack
const customStack = backend.createStack("StepFunctionsIntegration");
stepFunctionsStack(customStack, backend);
