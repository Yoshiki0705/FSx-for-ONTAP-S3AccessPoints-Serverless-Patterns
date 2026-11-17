import { describe, expect, it } from "vitest";
import { exportUseCase, importUseCase, UseCaseImportError } from "../../src/lib/useCaseJson";

function reason(fn: () => unknown): string {
  try {
    fn();
  } catch (e) {
    return e instanceof UseCaseImportError ? e.reason : "other";
  }
  return "none";
}

describe("use case JSON", () => {
  it("exports in GenU's shape, with the single input as a text field", () => {
    const out = JSON.parse(exportUseCase({ title: "Mail", description: "d", template: "Rewrite:\n{{input}}" }));
    expect(out).toEqual({
      title: "Mail",
      description: "d",
      promptTemplate: "Rewrite:\n{{text}}",
      fixedModelId: "",
      fileUpload: false,
      inputExamples: [],
    });
  });

  it("round-trips its own export", () => {
    const u = { title: "Mail", description: "", template: "A {{input}} B {{input}}" };
    expect(importUseCase(exportUseCase(u)).useCase).toEqual(u);
  });

  it("maps one labelled GenU text or form field to the portal's input", () => {
    const genu = { title: "Review", promptTemplate: "Review this code:\n{{text:Code}}\nAgain: {{text:Code}}" };
    expect(importUseCase(JSON.stringify(genu)).useCase.template).toBe("Review this code:\n{{input}}\nAgain: {{input}}");
    expect(importUseCase(JSON.stringify({ title: "F", promptTemplate: "{{form:Body}}" })).useCase.template).toBe("{{input}}");
  });

  it("keeps a template that already uses {{input}} or has no placeholder", () => {
    expect(importUseCase(JSON.stringify({ title: "T", template: "x {{input}}" })).useCase.template).toBe("x {{input}}");
    expect(importUseCase(JSON.stringify({ title: "T", template: "summarize" })).useCase.template).toBe("summarize");
  });

  it("refuses templates with more than one field or a field it cannot fill", () => {
    expect(reason(() => importUseCase(JSON.stringify({ title: "T", promptTemplate: "{{text:A}} {{text:B}}" })))).toBe("placeholders");
    expect(reason(() => importUseCase(JSON.stringify({ title: "T", promptTemplate: "{{select:Tone:formal,casual}}" })))).toBe("placeholders");
    expect(reason(() => importUseCase(JSON.stringify({ title: "T", promptTemplate: "{{retrieveKnowledgeBase}}" })))).toBe("placeholders");
  });

  it("refuses what is not a use case", () => {
    expect(reason(() => importUseCase("not json"))).toBe("notObject");
    expect(reason(() => importUseCase("[]"))).toBe("notObject");
    expect(reason(() => importUseCase(JSON.stringify({ promptTemplate: "x" })))).toBe("noTitle");
    expect(reason(() => importUseCase(JSON.stringify({ title: "T" })))).toBe("noTemplate");
    expect(reason(() => importUseCase(JSON.stringify({ title: "T", template: "x".repeat(4001) })))).toBe("tooLong");
  });

  it("names the GenU fields it does not keep", () => {
    const genu = { title: "T", promptTemplate: "{{text}}", fixedModelId: "m", fileUpload: true, inputExamples: [{ title: "e" }] };
    expect(importUseCase(JSON.stringify(genu)).ignored).toEqual(["fixedModelId", "fileUpload", "inputExamples"]);
    expect(importUseCase(JSON.stringify({ title: "T", promptTemplate: "{{text}}", fixedModelId: "", inputExamples: [] })).ignored).toEqual([]);
  });
});
