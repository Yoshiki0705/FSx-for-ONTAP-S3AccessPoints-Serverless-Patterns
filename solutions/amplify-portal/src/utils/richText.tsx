/**
 * Substitute React nodes into a translated sentence.
 *
 * Several of the portal's help texts name a literal the user has to type — a
 * database called `default`, a `SHOW DATABASES` statement, an `s3://` path — and
 * those read badly without code styling. Splitting the sentence into one key per
 * fragment would put the word order in the component instead of the locale file,
 * which breaks the moment a language orders the clause differently. So the whole
 * sentence stays in one key with `{placeholder}` markers, and the nodes are
 * spliced in here.
 *
 * The plain-string case already has a convention (`t(key).replace("{name}", v)`)
 * and should keep using it; this is only for values that must render as markup.
 */

import { Fragment, type ReactNode } from "react";

const TOKEN = /(\{[a-zA-Z][a-zA-Z0-9]*\})/g;

/**
 * An unknown placeholder is left as written rather than dropped: `{db}` visible
 * in the UI points at the missing value, whereas silently removing it produces a
 * sentence that reads fine and means something else.
 */
export function withNodes(template: string, values: Record<string, ReactNode>): ReactNode {
  return template.split(TOKEN).map((part, index) => {
    const name = part.startsWith("{") && part.endsWith("}") ? part.slice(1, -1) : null;
    const value = name !== null && name in values ? values[name] : part;
    return <Fragment key={index}>{value}</Fragment>;
  });
}
