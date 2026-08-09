# 新パターンの完了条件

> このファイルはリポジトリに含まれる（GitHub から読める）。ローカルの Kiro では
> `.kiro/skills/new-pattern/SKILL.md` が読み込み条件だけを持ち、
> 該当する作業をしているときにこの内容へ誘導する。`.kiro/` は公開しないため、
> 知識の本体は常にこちら側に置く。

## New Pattern: Field-Shareable Definition of Done

A new industry pattern is considered field-shareable (ready for Partner/SI customer conversations) only when ALL of the following are met:

- [ ] CloudFormation template passes `cfn-lint` with zero errors
- [ ] DemoMode=true execution succeeds (no FSx for ONTAP dependency)
- [ ] Unit tests + property-based tests pass
- [ ] Success Metrics defined (Business Outcome / Technical KPI / Quality KPI / Cost KPI / Go-No-Go)
- [ ] Data classification labels documented
- [ ] Human review thresholds defined and documented
- [ ] README in JP + EN at minimum
- [ ] `samconfig.toml.example` included
- [ ] Governance Note present (for regulated/safety-critical domains)
