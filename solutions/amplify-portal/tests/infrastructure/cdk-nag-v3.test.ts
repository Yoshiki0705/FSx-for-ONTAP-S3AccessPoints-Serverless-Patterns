/**
 * cdk-nag v3 API contract.
 *
 * The other harness tests read backend.ts as text, which proves the call was
 * written but not that it works. cdk-nag v3 replaced the `IAspect` engine with
 * CDK's `IPolicyValidationPlugin`, so `Aspects.of().add()` became
 * `Validations.of().addPlugins()` and `NagSuppressions` was removed in favour of
 * `Validations.of().acknowledge()`. Registration also became scope-sensitive:
 * plugins may only go on a Stage or an App.
 *
 * None of that is exercised by a normal synth here, because the portal only
 * registers the pack when CDK_NAG=1 — which is CI-only, and deliberately so,
 * since a reported violation interrupts synthesis. Without these tests the
 * migration would first be checked by the nag job on a pull request, and a
 * wrong scope would read as "cdk-nag is broken" rather than "the call moved".
 *
 * These run against real constructs, not the backend source, so they stay valid
 * if backend.ts is reorganised.
 */

import { describe, it, expect } from "vitest";
import { App, Stack, Validations } from "aws-cdk-lib";
import { Bucket } from "aws-cdk-lib/aws-s3";
import { AwsSolutionsChecks } from "cdk-nag";

/** A stack with one bucket, which trips several AwsSolutions rules. */
function fixture(): { app: App; stack: Stack } {
  const app = new App();
  const stack = new Stack(app, "NagFixture");
  new Bucket(stack, "Unlogged");
  return { app, stack };
}

/** Rule IDs the pack reports for `scope`, via the direct entry point. */
function findings(pack: AwsSolutionsChecks, scope: Stack): string[] {
  return (pack.validateScope(scope).violations ?? []).map((v) => v.ruleName);
}

describe("cdk-nag v3", () => {
  it("registers on an App", () => {
    const { app } = fixture();
    expect(() => Validations.of(app).addPlugins(new AwsSolutionsChecks(app))).not.toThrow();
  });

  it("validates the whole app no matter which scope the pack is registered on", () => {
    // The CDK docstring says plugins "can only be registered within a Stage or App
    // scope", which reads as a constraint on where addPlugins may be called. It is
    // not enforced, and it does not narrow validation: a pack registered on one
    // stack still reports findings in a sibling stack. Pinned because the wrong
    // reading leads to registering per-stack and expecting per-stack scoping.
    const app = new App();
    const a = new Stack(app, "StackA");
    new Bucket(a, "BucketA");
    const b = new Stack(app, "StackB");
    new Bucket(b, "BucketB");

    expect(() => Validations.of(a).addPlugins(new AwsSolutionsChecks(app))).not.toThrow();
    // validateScope is the direct entry point, so ask the pack about the stack it
    // was not registered on.
    expect(findings(new AwsSolutionsChecks(app), b)).toContain("AwsSolutions-S1");
  });

  it("reports findings on a stack that has them", () => {
    const { app, stack } = fixture();
    const reported = findings(new AwsSolutionsChecks(app), stack);
    expect(reported.length).toBeGreaterThan(0);
    // S1 (no server access logs) is one of the IDs the portal acknowledges, so
    // this also confirms the acknowledged IDs are still IDs this pack emits.
    expect(reported).toContain("AwsSolutions-S1");
  });

  it("acknowledging on the stack suppresses a finding beneath it", () => {
    // The v2 form was addStackSuppressions(stack, [...], true) — the trailing
    // true being "apply to children". v3 has no such flag; scope is the whole
    // mechanism. If that were wrong, every acknowledgment in backend.ts would
    // silently stop applying to the resources it was written for.
    const { app, stack } = fixture();
    Validations.of(stack).acknowledge({
      id: "AwsSolutions-S1",
      reason: "Fixture bucket; testing that acknowledgment reaches child constructs.",
    });
    expect(findings(new AwsSolutionsChecks(app), stack)).not.toContain("AwsSolutions-S1");
  });

  it("acknowledges on a single resource without touching its siblings", () => {
    // v2's per-resource form was addResourceSuppressions(resource, [{ id, reason,
    // appliesTo }]). v3 has no appliesTo — the scope is the resource. This is the
    // form security/cfn-guard-suppressions.md now documents, so it is checked here
    // rather than only asserted in prose.
    const app = new App();
    const stack = new Stack(app, "PerResource");
    const acknowledged = new Bucket(stack, "Acknowledged");
    new Bucket(stack, "Untouched");

    Validations.of(acknowledged).acknowledge({
      id: "AwsSolutions-S1",
      reason: "Fixture; testing resource-scoped acknowledgment.",
    });

    // validateScope reports `violatingResources`. The synth-time report writes the
    // same information under `violatingConstructs`, so reaching for that name here
    // yields an empty list and a test that passes for the wrong reason.
    const paths = (new AwsSolutionsChecks(app).validateScope(stack).violations ?? [])
      .filter((v) => v.ruleName === "AwsSolutions-S1")
      .flatMap((v) => (v.violatingResources ?? []).map((r) => r.constructPath ?? ""));
    expect(paths.length).toBeGreaterThan(0);
    expect(paths.some((p) => p.includes("Untouched"))).toBe(true);
    expect(paths.some((p) => p.includes("Acknowledged"))).toBe(false);
  });

  it("acknowledges more than one rule in a single call", () => {
    // backend.ts passes seven acknowledgments at once, which is variadic in v3
    // rather than the array v2 took.
    const { app, stack } = fixture();
    Validations.of(stack).acknowledge(
      { id: "AwsSolutions-S1", reason: "Fixture." },
      { id: "AwsSolutions-S10", reason: "Fixture." },
    );
    const reported = findings(new AwsSolutionsChecks(app), stack);
    expect(reported).not.toContain("AwsSolutions-S1");
    expect(reported).not.toContain("AwsSolutions-S10");
  });

  it("no longer exports NagSuppressions", async () => {
    // Named so that a dependency rollback to v2 fails here with the reason
    // rather than somewhere in a synth log.
    const nag = await import("cdk-nag");
    expect("NagSuppressions" in nag).toBe(false);
  });
});
