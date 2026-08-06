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
      // These two remain warnings, as a ratchet rather than an exemption.
      // `--max-warnings` in package.json pins the count, so it can only go down.
      //
      //   react-hooks/set-state-in-effect  34  Almost all are the fetch-on-mount
      //       shape: `const load = async () => { setLoading(true); ... }` called
      //       straight from a mount effect, so the first setState runs before the
      //       first await. `loading` already initialises to `true` in these
      //       components, which makes that call a no-op on the mount path. Clearing
      //       them means restructuring ~30 components for a pattern that is
      //       idiomatic, so each needs its own judgement about render behaviour.
      //       (34, up from the original 32: fixing AgentFileSidebar's immutability
      //       finding moved its reset calls into the effect body, and memoising
      //       AgentChat's loadSessions let the rule trace into it.)
      //
      //   react-hooks/exhaustive-deps       6  Down from 8. The two real ones were
      //       in AgentChat and are fixed — see the notes at sendMessage and
      //       saveCurrentSession; the sendMessage one silently dropped an attached
      //       image and sent a stale agent mode.
      //
      //       The remaining 6 all have the shape
      //       `useEffect(() => { loadX(); }, [trigger])`, where the array lists the
      //       state that should cause a reload and omits the loader itself. The
      //       loaders are plain function declarations, so they get a new identity
      //       every render; adding them as written would re-run the fetch on every
      //       render instead of on the trigger.
      //
      //       The honest fix is to memoise each loader and depend on it. That is
      //       deliberately not done here for two reasons. VolumeSelector cannot take
      //       it at all: its loader closes over the `onSelect` prop, and all four
      //       call sites pass an inline arrow, so the identity changes every parent
      //       render — and because the loader calls `onSelect`, which sets parent
      //       state, the result would be an unbounded refetch loop rather than a
      //       cosmetic re-render. For the other five, getting a memo dependency
      //       wrong produces the same class of loop, and these are admin panels that
      //       cannot be exercised without a deployed FSx for ONTAP backend and
      //       storage-admin group membership. Converting them belongs in a change
      //       that can be verified against a running sandbox.
      "react-hooks/set-state-in-effect": "warn",
      "react-hooks/exhaustive-deps": "warn",
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
