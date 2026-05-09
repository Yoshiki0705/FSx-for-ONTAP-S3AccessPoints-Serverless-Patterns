# Requirements Document

## Introduction

本機能は2つの主要タスクで構成される: (1) 全ユースケースフォルダの README を8言語対応にし、言語切替リンクを統一する、(2) EDA Summit 向けに半導体/EDA エンドユーザー視点のデモ動画企画を策定する。ルート README で既に実現している多言語切替パターンを各 UC フォルダに展開し、UC6 については EDA エンドユーザー（設計エンジニア）が価値を実感できるデモシナリオを提案する。

## Glossary

- **UC_Folder**: ユースケースごとのディレクトリ（semiconductor-eda, financial-idp, legal-compliance, healthcare-dicom, genomics-pipeline, media-vfx, autonomous-driving, construction-bim, education-research, energy-seismic, insurance-claims, logistics-ocr, manufacturing-analytics, retail-catalog の14フォルダ）
- **Language_Switcher**: README 先頭に配置する8言語切替リンク行（🌐 **Language / 言語**: [日本語](README.md) | [English](README.en.md) | ... 形式）
- **Target_Languages**: ja, en, ko, zh-CN, zh-TW, fr, de, es の8言語
- **Translation_System**: README の翻訳を生成・管理するプロセス
- **EDA_Demo_Proposal**: EDA Summit 向けデモ動画の企画書
- **EDA_End_User**: 半導体設計エンジニア（DRC 結果確認、メタデータ検索、設計品質レビューを行う人）
- **Root_README**: リポジトリルートの README.md および各言語版ファイル

## Requirements

### Requirement 1: UC フォルダ多言語 README ファイル生成

**User Story:** As a non-Japanese-speaking developer, I want each UC folder to have README files in my language, so that I can understand the use case without relying on machine translation.

#### Acceptance Criteria

1. THE Translation_System SHALL generate README files in all Target_Languages for each UC_Folder, following the naming convention `README.{lang}.md` (Japanese version is `README.md`)
2. WHEN a README file is generated, THE Translation_System SHALL include a Language_Switcher as the first content line after the title, linking to all 8 language versions using relative paths within the same directory
3. THE Translation_System SHALL preserve the original document structure (headings, code blocks, Mermaid diagrams, tables) in all translated versions
4. THE Translation_System SHALL translate prose content while keeping code snippets, CLI commands, file paths, and AWS service names untranslated
5. WHEN the source README.md (Japanese) is updated, THE Translation_System SHALL provide a mechanism to regenerate translated versions to maintain consistency

### Requirement 2: Language_Switcher の統一フォーマット

**User Story:** As a repository visitor, I want a consistent language switching experience across all README files, so that I can navigate between languages seamlessly regardless of which UC folder I am viewing.

#### Acceptance Criteria

1. THE Language_Switcher SHALL follow the exact format: `🌐 **Language / 言語**: [日本語](README.md) | [English](README.en.md) | [한국어](README.ko.md) | [简体中文](README.zh-CN.md) | [繁體中文](README.zh-TW.md) | [Français](README.fr.md) | [Deutsch](README.de.md) | [Español](README.es.md)`
2. THE Language_Switcher SHALL be placed immediately after the first H1 heading in each README file
3. WHEN a user is viewing a specific language version, THE Language_Switcher SHALL display the current language without a hyperlink (plain text) and all other languages as clickable links

### Requirement 3: 既存 README との整合性

**User Story:** As a project maintainer, I want the multilingual expansion to be consistent with the existing root README pattern, so that the repository has a unified look and feel.

#### Acceptance Criteria

1. THE Translation_System SHALL use the same Language_Switcher format that the Root_README already uses
2. WHERE a UC_Folder already has translated README files (e.g., semiconductor-eda/README.en.md), THE Translation_System SHALL update the existing files to add the Language_Switcher rather than overwriting content
3. THE Translation_System SHALL maintain technical accuracy in translations, preserving domain-specific terminology (e.g., GDSII, DRC, OASIS, Athena, Bedrock) without translation

### Requirement 4: EDA Summit デモ動画企画の策定

**User Story:** As a presenter at the EDA Summit, I want a demo video proposal targeting EDA end-users, so that the audience can see the value of automated design file analysis from their perspective.

#### Acceptance Criteria

1. THE EDA_Demo_Proposal SHALL define a demo scenario from the EDA_End_User perspective (not infrastructure admin perspective)
2. THE EDA_Demo_Proposal SHALL include a storyboard with the following sections: problem statement, workflow trigger, automated analysis, results review, and actionable insights
3. THE EDA_Demo_Proposal SHALL target a video duration of 3–5 minutes suitable for summit presentation
4. THE EDA_Demo_Proposal SHALL demonstrate the end-to-end flow: design file discovery → metadata extraction → DRC aggregation → AI-generated review report
5. THE EDA_Demo_Proposal SHALL emphasize EDA-specific value propositions: automated quality gate, cross-design-library analytics, and natural language risk assessment

### Requirement 5: デモシナリオの EDA エンドユーザー視点

**User Story:** As an EDA engineer watching the demo, I want to see how this tool solves my daily pain points, so that I can evaluate whether to adopt it in my workflow.

#### Acceptance Criteria

1. THE EDA_Demo_Proposal SHALL frame the narrative around a realistic EDA workflow scenario (e.g., pre-tapeout design quality review across multiple IP blocks)
2. THE EDA_Demo_Proposal SHALL show the user experience of querying design metadata via Athena SQL (e.g., "show all cells with bounding box outliers")
3. THE EDA_Demo_Proposal SHALL show the AI-generated design review report as the primary deliverable visible to the EDA_End_User
4. THE EDA_Demo_Proposal SHALL avoid infrastructure setup details (CloudFormation, IAM, VPC) and focus on input/output from the engineer's perspective
5. IF the demo includes CLI or console interactions, THEN THE EDA_Demo_Proposal SHALL present them as actions an EDA engineer would perform (e.g., triggering analysis after a design milestone)

### Requirement 6: デモ動画の技術的実現可能性

**User Story:** As the demo creator, I want the proposed demo to be executable with the current UC6 implementation, so that I can produce the video within the one-week timeline.

#### Acceptance Criteria

1. THE EDA_Demo_Proposal SHALL use only components that are already deployed and verified (Step Functions, Lambda, Athena, Bedrock)
2. THE EDA_Demo_Proposal SHALL specify the sample data requirements (GDS/OASIS files) that can be generated or are already available in the demo environment
3. THE EDA_Demo_Proposal SHALL include a recording plan with screen capture points and narration outline
4. WHEN proposing demo enhancements, THE EDA_Demo_Proposal SHALL clearly separate "achievable within 1 week" items from "future enhancement" items
5. THE EDA_Demo_Proposal SHALL be deliverable as a markdown document (`semiconductor-eda/docs/eda-summit-demo-proposal.md`)

### Requirement 7: 翻訳品質の担保

**User Story:** As a reader of the translated README, I want the translation to be natural and accurate in my language, so that I can understand the content without confusion.

#### Acceptance Criteria

1. THE Translation_System SHALL produce translations that read naturally in each target language (not word-for-word machine translation artifacts)
2. THE Translation_System SHALL keep AWS service names in English across all languages (e.g., "Amazon Bedrock", "AWS Step Functions", "Amazon Athena")
3. THE Translation_System SHALL translate section headings appropriately while maintaining the same hierarchical structure
4. THE Translation_System SHALL preserve all hyperlinks, ensuring relative paths remain correct for the UC folder context
5. IF a technical term has a widely accepted translation in the target language, THEN THE Translation_System SHALL use that accepted translation with the English term in parentheses on first occurrence
