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

      // The three rules below are warnings, not errors, and that is a
      // deliberate ratchet rather than an exemption.
      //
      // This config is the first time the portal has ever been linted — the
      // `lint` script existed without a config file, so it exited 2 on every
      // run. Turning ~170 pre-existing findings into errors would either block
      // every future change or force a mass rewrite inside an unrelated
      // dependency upgrade. As warnings they are visible on every run and
      // `--max-warnings` (see package.json) pins the current count, so the
      // number can only go down.
      //
      // Baseline at the time of writing — 176 warnings, matching the
      // `--max-warnings 176` in the lint script:
      //   @typescript-eslint/no-explicit-any   134  typing debt, mostly around
      //                                             `client.mutations as any`
      //                                             for Amplify-generated types
      //   react-hooks/set-state-in-effect       32  needs per-case judgement
      //                                             about render behaviour
      //   react-hooks/exhaustive-deps            8  possible stale closures
      //   react-hooks/immutability               2
      //
      // The react-hooks findings are the ones worth real attention: they can
      // indicate extra render passes or stale reads, not just style.
      "@typescript-eslint/no-explicit-any": "warn",
      "react-hooks/set-state-in-effect": "warn",
      "react-hooks/exhaustive-deps": "warn",
      "react-hooks/immutability": "warn",
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
