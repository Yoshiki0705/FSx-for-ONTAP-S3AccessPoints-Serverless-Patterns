# CDK Migration Evaluation (Phase 9 Theme E)

**Date**: 2026-05-12
**Status**: EVALUATED — **No-Go for Phase 9/10** (see Conclusion)

---

## 1. Current State

- 17 UC templates in raw CloudFormation YAML (`template-deploy.yaml`)
- Average template size: ~800-1100 lines
- Shared patterns: Parameters, Conditions, Lambda functions, Step Functions ASL, IAM roles
- Tooling: cfn-lint, cfn-guard, 5 custom Python validators

## 2. Pain Points with YAML

| Pain Point | Severity | Frequency |
|-----------|----------|-----------|
| Copy-paste errors across UCs | Medium | Every new UC |
| No type safety on !Ref / !Sub | Medium | Occasional |
| ASL JSON embedded in YAML (escaping) | Low | Rare (stable) |
| Condition logic verbosity | Low | Stable |
| No IDE autocomplete for resources | Low | Always |

## 3. CDK Migration Benefits

| Benefit | Impact |
|---------|--------|
| Type-safe constructs | Catches !Ref typos at compile time |
| Reusable L3 constructs | Shared patterns as classes |
| IDE autocomplete | Faster development |
| Unit testing of infrastructure | Jest/pytest for stacks |
| Programmatic conditions | Replace verbose !If chains |

## 4. CDK Migration Costs

| Cost | Impact |
|------|--------|
| Learning curve | Team must learn CDK + TypeScript |
| Migration effort | 17 templates × ~2 hours = ~34 hours |
| Dual maintenance during migration | Both YAML and CDK must work |
| CI/CD pipeline changes | New synth + deploy workflow |
| Loss of template portability | CDK output is synthesized CFn (less readable) |
| Existing validator scripts | Must be rewritten or adapted |
| Phase 1-8 documentation | All references to template-deploy.yaml become stale |

## 5. Evaluation Criteria

| Criterion | Weight | YAML Score | CDK Score |
|-----------|--------|-----------|-----------|
| Time to add new UC | 20% | 7/10 (copy+modify) | 9/10 (extend class) |
| Bug prevention | 25% | 6/10 (validators catch most) | 8/10 (compile-time) |
| Maintenance burden | 20% | 7/10 (stable, rarely changes) | 6/10 (CDK version upgrades) |
| Team familiarity | 15% | 9/10 (everyone knows YAML) | 4/10 (CDK learning curve) |
| Portability | 10% | 9/10 (raw CFn, any tool) | 5/10 (CDK-specific) |
| Documentation alignment | 10% | 9/10 (all docs reference YAML) | 3/10 (must rewrite) |
| **Weighted Total** | | **7.35** | **6.35** |

## 6. Conclusion: No-Go

**Decision**: Do NOT migrate to CDK in Phase 9 or Phase 10.

**Rationale**:
1. The 5 custom validators (check_s3ap_iam_patterns, check_handler_names, check_conditional_refs, check_python_quality, cfn-guard rules) already catch the bug classes that CDK's type safety would prevent.
2. The templates are stable — Phase 8 was the last major structural change (OutputDestination, Observability). Future phases add features within existing template structure.
3. Migration cost (34+ hours) exceeds the benefit for a pattern library that adds ~1 new UC per phase.
4. The blog article series and all 8-language documentation reference `template-deploy.yaml` directly. Migration would require rewriting hundreds of documentation pages.

**Revisit conditions**:
- If the project grows beyond 25 UCs
- If a new team member joins who is CDK-native
- If AWS CDK adds a "import from existing CFn" feature that preserves logical names

## 7. Alternative: Incremental Improvement

Instead of full CDK migration, Phase 9+ will:
1. Keep YAML templates as source of truth
2. Add cfn-guard rules for common patterns (done in Theme D)
3. Consider a Python-based template generator for the repetitive sections (Parameters, Conditions, IAM roles) — similar to `create_deploy_template.py` but for new UC scaffolding
