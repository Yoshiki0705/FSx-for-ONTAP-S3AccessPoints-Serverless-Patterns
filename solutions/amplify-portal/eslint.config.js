// ESLint flat config for the portal.
//
// The `lint` script has existed in package.json since the portal was created,
// but no config file did — so `npm run lint` exited 2 ("could not find a
// configuration file") on every invocation, and CI never called it. The portal
// therefore had no JavaScript/TypeScript linting at all, while the rest of the
// repository is covered by ruff, cfn-lint and cdk-nag. This file closes that
// gap.
//
// Type-aware rules are deliberately NOT enabled (no `projectService`). They
// require typescript-eslint to parse with full type information, which roughly
// doubles lint time, and the type errors they would catch are already caught by
// `tsc --noEmit` in `npm run build`. What ESLint adds here is the class of
// problem the compiler does not look for: unused directives, React Hooks rule
// violations, and accidental `any`.

import js from "@eslint/js";
import globals from "globals";
import tseslint from "typescript-eslint";
import reactHooks from "eslint-plugin-react-hooks";

export default tseslint.config(
  {
    // Build output, dependencies, and generated Amplify artifacts.
    ignores: [
      "dist/**",
      "node_modules/**",
      ".amplify/**",
      "amplify_outputs.json",
      "coverage/**",
      "playwright-report/**",
      "test-results/**",
    ],
  },
  js.configs.recommended,
  ...tseslint.configs.recommended,
  {
    files: ["**/*.{ts,tsx}"],
    languageOptions: {
      ecmaVersion: 2022,
      globals: {
        ...globals.browser,
        ...globals.node,
      },
    },
    plugins: {
      "react-hooks": reactHooks,
    },
    rules: {
      ...reactHooks.configs.recommended.rules,
      // Unused variables are an error, but allow the `_`-prefixed convention
      // for deliberately-ignored destructured values, catch bindings, and CDK
      // constructs that are created for their side effect on the stack.
      "@typescript-eslint/no-unused-vars": [
        "error",
        {
          argsIgnorePattern: "^_",
          varsIgnorePattern: "^_",
          caughtErrorsIgnorePattern: "^_",
        },
      ],

      // When this config was introduced the portal had never been linted, and it
      // reported 176 findings:
      //
      //   @typescript-eslint/no-explicit-any   134
      //   react-hooks/set-state-in-effect       32
      //   react-hooks/exhaustive-deps            8
      //   react-hooks/immutability               2
      //
      // All 134 `any` and both immutability findings are now fixed, so those two
      // rules are errors — a new one fails the build instead of joining a backlog.
      //
      // The 134 `any` were not suppressed one by one. 113 were
      // `(client.queries as any)` / `(client.mutations as any)`, needed only because
      // 30 copies of a local `parseResponse` helper declared their parameter as
      // `{ data?: string | null }` while the schema returns `a.json()`. Removing the
      // casts surfaced 104 type errors, all of them that single disagreement; one
      // shared helper in src/utils/parseResponse.ts with the honest `unknown`
      // signature resolved every one. The rest were a `TaskCard` whose key fields
      // were `string` rather than `TranslationKeys`, callback parameters TypeScript
      // could infer once the response type was no longer erased, and a lookup of a
      // `window` global that nothing ever assigns.
      "@typescript-eslint/no-explicit-any": "error",
      "react-hooks/immutability": "error",
      // These two were carried as warnings behind a `--max-warnings` ratchet while
      // the portal fetched in effects. Both are now zero and are errors.
      //
      // They were not fixable by rearranging the effects. The documented react.dev
      // remedy for `set-state-in-effect` ("do not set loading state synchronously")
      // was applied to ArpStatus in full and the warning stayed: the rule traces
      // into the loader, so an effect that calls anything which eventually sets
      // state is flagged whether or not the call is synchronous. react.dev's own
      // guidance for fetching is a dedicated library, so the fix was to adopt one.
      //
      // Every loader is now a TanStack Query `useQuery`, which also removed the
      // `exhaustive-deps` findings: those effects listed the trigger state and
      // omitted the loader, because the loaders were re-created each render and
      // depending on them would have refetched on every render. With the trigger in
      // the query key there is no loader closure left to depend on. VolumeSelector
      // was the one that could not be memoised at all — its loader called the
      // `onSelect` prop, which sets parent state, so depending on it would have
      // looped; its default selection is derived during render instead.
      //
      // Cache writes replace the local-list edits that mutation handlers used to
      // make, so a deleted row disappears without refetching the collection.
      "react-hooks/set-state-in-effect": "error",
      "react-hooks/exhaustive-deps": "error",
    },
  },
  {
    // The generic dispatch endpoints take an action name and a JSON blob, so a call
    // made directly on the generated client has nothing to check it: TypeScript sees
    // two strings. That is how a lock button shipped sending a snapshot name and a
    // day count to an action that reads a UUID and an absolute instant.
    //
    // `src/lib/dispatch.ts` wraps them with the action union and per-action parameter
    // types generated from the handlers, and is the one place allowed to reach the
    // client. `folderMutation` is not listed: the folder download function never
    // looks at `action`, so it has no action union to belong to and its own schema
    // types are already specific.
    files: ["src/**/*.{ts,tsx}"],
    ignores: ["src/lib/dispatch.ts"],
    rules: {
      "no-restricted-syntax": [
        "error",
        {
          selector:
            "MemberExpression[object.property.name=/^(queries|mutations)$/]" +
            "[property.name=/^(adminQuery|adminMutation|arpQuery|arpMutation|protectionQuery" +
            "|protectionMutation|fileQuery|fileMutation|agentQuery)$/]",
          message:
            "Call the generic dispatch endpoints through src/lib/dispatch.ts " +
            "(dispatch / adminQuery / adminMutate / …), which checks the action name " +
            "and its parameters against the handler. A direct client call is unchecked.",
        },
      ],
    },
  },
  {
    // Playwright specs are type-checked and run by Playwright's own runner and
    // are excluded from tsconfig, so linting them here would report unresolved
    // imports for a dependency that is intentionally provisioned via npx.
    files: ["tests/e2e/**"],
    rules: {
      "@typescript-eslint/no-unused-vars": "off",
    },
  },
);
