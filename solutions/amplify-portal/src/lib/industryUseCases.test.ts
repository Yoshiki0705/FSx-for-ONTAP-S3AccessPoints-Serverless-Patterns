import { describe, it, expect } from "vitest";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { ja, en, ko, zhCN, zhTW, fr, de, es } from "../i18n/locales";
import { INDUSTRY_USE_CASES, SELECTABLE_PATTERNS, patternSlug } from "./industryUseCases";
import { AGENT_INDUSTRY_TEMPLATES, buildSystemPrompt } from "./agentIndustryTemplates";

const root = resolve(__dirname, "../..");
const resourceSource = readFileSync(resolve(root, "amplify/data/resource.ts"), "utf8");
const enumBody = /ProcessingPattern: a\.enum\(\[([\s\S]*?)\]\)/.exec(resourceSource)?.[1] ?? "";
const enumValues = [...enumBody.matchAll(/"([A-Z0-9_]+)"/g)].map((m) => m[1]);
const locales = { ja, en, ko, zhCN, zhTW, fr, de, es } as Record<string, Record<string, string>>;

describe("industry processing patterns", () => {
  it("lists UC1 to UC28 in order", () => {
    expect(INDUSTRY_USE_CASES).toHaveLength(28);
    INDUSTRY_USE_CASES.forEach((key, index) => expect(key.startsWith(`UC${index + 1}_`)).toBe(true));
  });

  it("matches the GraphQL enum; FC7 is the one value kept off the screen", () => {
    expect([...enumValues].sort()).toEqual([...SELECTABLE_PATTERNS, "FC7_FLEXCLONE_RESTORE"].sort());
  });

  it("derives the directory name used in the state machine name", () => {
    expect(patternSlug("UC1_LEGAL_COMPLIANCE")).toBe("legal-compliance");
    expect(patternSlug("UC17_SMART_CITY_GEOSPATIAL")).toBe("smart-city-geospatial");
    expect(patternSlug("OPS1_CAPACITY_RIGHTSIZING")).toBeNull();
  });

  it("routes each pattern to its own state machine in the resolver", () => {
    const resolver = readFileSync(resolve(root, "amplify/data/resolvers/start-processing.js"), "utf8");
    expect(resolver).toContain('ctx.env["SFN_ARN_" + prefix] || ctx.env.STATE_MACHINE_ARN');
    const backend = readFileSync(resolve(root, "amplify/backend.ts"), "utf8");
    expect(backend).toContain("EnvironmentVariables.SFN_ARN_${pattern.split(\"_\")[0]}");
    // APPSYNC_JS has no String(), regular expressions or similar globals: `aws appsync evaluate-code`
    // rejected String(...) here with INVALID_FUNCTION_INVOCATION, which unit tests under Node cannot show.
    expect(resolver).not.toMatch(/\bString\(|\bNumber\(|new RegExp|\.match\(/);
  });

  it("has a directory under solutions/industry for every industry pattern", () => {
    for (const key of INDUSTRY_USE_CASES) {
      const dir = resolve(root, "../industry", patternSlug(key) as string, "template.yaml");
      expect(() => readFileSync(dir), key).not.toThrow();
    }
  });

  it.each(Object.keys(locales))("%s has a label for every pattern and template", (name) => {
    const messages = locales[name];
    for (const key of SELECTABLE_PATTERNS) {
      expect(messages[`ucIndustry_${key}`], `${name}: ucIndustry_${key}`).toBeTruthy();
      expect(messages[`ucTask_${key}`], `${name}: ucTask_${key}`).toBeTruthy();
    }
    for (const template of AGENT_INDUSTRY_TEMPLATES) {
      expect(messages[template.nameKey], `${name}: ${template.nameKey}`).toBeTruthy();
      expect(messages[template.descKey], `${name}: ${template.descKey}`).toBeTruthy();
      expect(messages[template.descKey].length).toBeLessThanOrEqual(200);
    }
  });
});

describe("agent industry templates", () => {
  const validTools = new Set([
    "list_files", "read_file", "search_files", "get_volume_summary", "kb_search", "request_action_approval",
  ]);
  const categories = new Set(["custom", "file-ops", "knowledge", "security", "analytics", "automation"]);

  it("uses only tools and categories the agent API accepts", () => {
    for (const template of AGENT_INDUSTRY_TEMPLATES) {
      expect(template.tools.length).toBeGreaterThan(0);
      for (const tool of template.tools) expect(validTools.has(tool), `${template.id}: ${tool}`).toBe(true);
      expect(categories.has(template.category), template.id).toBe(true);
    }
  });

  it("has unique ids and appends the shared rules to the prompt", () => {
    const ids = AGENT_INDUSTRY_TEMPLATES.map((t) => t.id);
    expect(new Set(ids).size).toBe(ids.length);
    for (const template of AGENT_INDUSTRY_TEMPLATES) {
      expect(buildSystemPrompt(template)).toContain("answer only from files");
    }
  });
});
