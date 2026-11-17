/**
 * Use cases as JSON files, in the shape GenU's Use Case Builder exports.
 *
 * GenU writes `{ title, description, promptTemplate, fixedModelId, fileUpload, inputExamples }`
 * (packages/web/src/components/useCaseBuilder/ButtonUseCaseExport.tsx). Its template has one
 * placeholder per input field, `{{text:label}}`, `{{form:label}}`, `{{select:label:options}}` and
 * retrieval ones; this portal's template has one input, `{{input}}`. So an export writes
 * `{{text}}` for it, and an import accepts a template with at most one text or form field and
 * refuses the rest by name, rather than guessing which field the portal's single input means.
 */

export const TITLE_MAX = 100;
export const DESCRIPTION_MAX = 300;
export const TEMPLATE_MAX = 4000;

export interface UseCaseDraft {
  title: string;
  description: string;
  template: string;
}

export interface ImportedUseCase {
  useCase: UseCaseDraft;
  /** GenU fields with a value that the portal does not keep (model pinning, file upload, examples). */
  ignored: string[];
}

export class UseCaseImportError extends Error {
  constructor(
    readonly reason: "notObject" | "noTitle" | "noTemplate" | "tooLong" | "placeholders",
    readonly detail = "",
  ) {
    super(detail ? `${reason}: ${detail}` : reason);
  }
}

const PLACEHOLDER = /\{\{[^}]*\}\}/g;
const SINGLE_INPUT_TYPES = new Set(["text", "form"]);

/** The GenU-shaped JSON for one use case. */
export function exportUseCase(u: { title: string; description?: string; template: string }): string {
  return JSON.stringify(
    {
      title: u.title,
      description: u.description || "",
      promptTemplate: u.template.split("{{input}}").join("{{text}}"),
      fixedModelId: "",
      fileUpload: false,
      inputExamples: [],
    },
    null,
    2,
  );
}

function text(value: unknown): string {
  return typeof value === "string" ? value.trim() : "";
}

/** A use case to put in the editor, from a file exported by this portal or by GenU. */
export function importUseCase(json: string): ImportedUseCase {
  let data: unknown;
  try {
    data = JSON.parse(json);
  } catch {
    throw new UseCaseImportError("notObject");
  }
  if (!data || typeof data !== "object" || Array.isArray(data)) throw new UseCaseImportError("notObject");
  const d = data as Record<string, unknown>;
  const title = text(d.title);
  const description = text(d.description);
  let template = text(d.template) || text(d.promptTemplate);
  if (!title) throw new UseCaseImportError("noTitle");
  if (!template) throw new UseCaseImportError("noTemplate");

  if (!template.includes("{{input}}")) {
    const found = [...new Set(template.match(PLACEHOLDER) || [])];
    if (found.length > 1 || (found.length === 1 && !SINGLE_INPUT_TYPES.has(found[0].slice(2, -2).split(":")[0]))) {
      throw new UseCaseImportError("placeholders", found.join(", "));
    }
    if (found.length === 1) template = template.split(found[0]).join("{{input}}");
  }
  if (title.length > TITLE_MAX || description.length > DESCRIPTION_MAX || template.length > TEMPLATE_MAX) {
    throw new UseCaseImportError("tooLong");
  }

  const ignored: string[] = [];
  if (text(d.fixedModelId)) ignored.push("fixedModelId");
  if (d.fileUpload === true) ignored.push("fileUpload");
  if (Array.isArray(d.inputExamples) && d.inputExamples.length > 0) ignored.push("inputExamples");
  return { useCase: { title, description, template }, ignored };
}
