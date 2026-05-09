# Implementation Plan: UC Multilingual README & EDA Demo Proposal

## Overview

本実装は2つの独立したトラックで進行する: (1) EDA Summit デモ企画書の作成（時間制約あり）、(2) 翻訳システムのコアロジック実装とプロパティテスト、(3) 全 UC フォルダへの README 生成展開。EDA Summit が来週のため、デモ企画書を最優先で完成させる。

## Tasks

- [x] 1. EDA Summit デモ企画書の作成
  - [x] 1.1 EDA デモ企画書ドキュメントを作成する
    - `semiconductor-eda/docs/eda-summit-demo-proposal.md` を作成
    - Executive Summary、Target Audience & Persona、Demo Scenario (Pre-tapeout Quality Review) を記述
    - Storyboard (5 sections, 3-5 min total) を定義: problem statement → workflow trigger → automated analysis → results review → actionable insights
    - Screen Capture Plan と Narration Outline を含める
    - Sample Data Requirements（GDS/OASIS ファイル）を明記
    - Timeline セクションで「1週間以内に達成可能」と「将来の拡張」を明確に分離
    - 使用コンポーネントは既存実装のみ（Step Functions, Lambda, Athena, Bedrock）
    - EDA エンドユーザー（設計エンジニア）視点で記述し、インフラ詳細（CloudFormation, IAM, VPC）は排除
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 5.1, 5.2, 5.3, 5.4, 5.5, 6.1, 6.2, 6.3, 6.4, 6.5_

- [x] 2. Checkpoint - EDA デモ企画書レビュー
  - Ensure all tests pass, ask the user if questions arise.
  - EDA デモ企画書の内容が Requirements 4, 5, 6 を満たしているか確認

- [x] 3. Translation System コアモジュールの実装
  - [x] 3.1 プロジェクト構造とデータモデルを作成する
    - `scripts/translate_readmes.py` を作成
    - `TranslationConfig` dataclass を実装（source_lang, target_languages, uc_folders, bedrock_model_id）
    - `BlockType` enum と `ContentBlock` dataclass を実装
    - `TranslationResult` dataclass を実装
    - `LanguageSwitcherConfig` dataclass を実装
    - _Requirements: 1.1_

  - [x] 3.2 LanguageSwitcherInjector クラスを実装する
    - `SWITCHER_TEMPLATE`, `LANG_LABELS`, `LANG_FILES` 定数を定義
    - `generate_switcher(current_lang)` メソッド: 現在言語をプレーンテキスト、他言語をリンクとして Switcher 行を生成
    - `inject_into_markdown(content, current_lang)` メソッド: H1 直後に Switcher を挿入（既存 Switcher があれば置換）
    - Root README の Language Switcher フォーマットと完全一致させる
    - _Requirements: 1.2, 2.1, 2.2, 2.3, 3.1, 3.2_

  - [x]* 3.3 Property test: Language Switcher placement after H1 (Property 1)
    - **Property 1: Language Switcher placement after H1**
    - Hypothesis で任意の H1 を含む Markdown に対して、inject 後に Switcher が H1 直後に配置されることを検証
    - **Validates: Requirements 1.2, 2.2**

  - [x]* 3.4 Property test: Current language is plain text in switcher (Property 2)
    - **Property 2: Current language is plain text in switcher**
    - Hypothesis で全8言語コードに対して、生成された Switcher に7つのリンクと1つのプレーンテキストが含まれることを検証
    - **Validates: Requirements 2.3**

  - [x]* 3.5 Property test: Content preservation on switcher injection (Property 6)
    - **Property 6: Content preservation on switcher injection**
    - Hypothesis で既存 Switcher あり/なしの Markdown に対して、inject 後に元コンテンツが保持されることを検証
    - **Validates: Requirements 3.2**

- [x] 4. MarkdownTranslator クラスの実装
  - [x] 4.1 split_translatable メソッドを実装する
    - Markdown をセクション単位に分割: prose, code, mermaid, table, heading, switcher
    - コードブロック（```...```）、Mermaid ダイアグラム、インラインコードを翻訳対象外として分離
    - テーブル構造を検出し、テキストセルのみ翻訳対象としてマーク
    - _Requirements: 1.3, 1.4_

  - [x] 4.2 reassemble メソッドを実装する
    - 翻訳済み prose + 未翻訳コードブロックを再結合
    - ブロック順序を保持し、元の Markdown 構造を復元
    - _Requirements: 1.3_

  - [x] 4.3 translate_prose メソッドを実装する（Bedrock 連携）
    - Amazon Bedrock (Claude Haiku) で prose セクションを翻訳
    - AWS サービス名、技術用語（GDSII, DRC, OASIS 等）を保持するプロンプト設計
    - Exponential backoff（max 3 retries）によるレート制限対応
    - 60s タイムアウト設定
    - _Requirements: 1.4, 3.3, 7.1, 7.2, 7.5_

  - [x]* 4.4 Property test: Document structure invariant across translation (Property 3)
    - **Property 3: Document structure invariant across translation**
    - Hypothesis で split → reassemble のラウンドトリップで構造（見出し数、コードブロック数、Mermaid 数、テーブル行数）が保持されることを検証
    - **Validates: Requirements 1.3, 7.3**

  - [x]* 4.5 Property test: Untranslatable content preservation (Property 4)
    - **Property 4: Untranslatable content preservation**
    - Hypothesis でコードブロック・インラインコード・AWS サービス名を含む Markdown に対して、split → reassemble 後にそれらが byte-for-byte 同一であることを検証
    - **Validates: Requirements 1.4, 3.3, 7.2**

  - [x]* 4.6 Property test: Hyperlink target preservation (Property 5)
    - **Property 5: Hyperlink target preservation**
    - Hypothesis でハイパーリンクを含む Markdown に対して、翻訳後にリンクターゲット（URL・相対パス）が変更されていないことを検証
    - **Validates: Requirements 7.4**

- [x] 5. Checkpoint - コアロジックとプロパティテスト確認
  - Ensure all tests pass, ask the user if questions arise.
  - LanguageSwitcherInjector と MarkdownTranslator のコアロジックが正しく動作することを確認

- [x] 6. ReadmeGenerator オーケストレーターの実装
  - [x] 6.1 ReadmeGenerator クラスを実装する
    - `generate_for_folder(folder_path)` メソッド: 1 UC フォルダの全7言語版を生成
    - `generate_all()` メソッド: 全14フォルダを処理
    - Source README 検出、翻訳パイプライン実行、ファイル書き出しを統合
    - 既存ファイルがある場合は Language Switcher のみ更新（内容は上書きしない）
    - エラーハンドリング: フォルダ単位でスキップ、`TranslationResult` で結果収集
    - 処理完了後のサマリーレポート出力と `translation_errors.log` 記録
    - _Requirements: 1.1, 1.5, 3.2_

  - [x] 6.2 CLI インターフェースを実装する
    - argparse で対象フォルダ指定（`--folders`）、全フォルダ実行（`--all`）オプション
    - `--dry-run` オプションで実際のファイル書き出しをスキップ
    - 進捗表示（処理中フォルダ名、完了数/全体数）
    - _Requirements: 1.5_

  - [x]* 6.3 Unit tests for ReadmeGenerator
    - 単一フォルダの生成フローをモック Bedrock でテスト
    - 既存ファイルの Language Switcher 更新が正しく動作することをテスト
    - エラー時のスキップとレポート出力をテスト
    - _Requirements: 1.1, 1.5, 3.2_

- [x] 7. semiconductor-eda フォルダの README 生成（優先実行）
  - [x] 7.1 semiconductor-eda の多言語 README を生成する
    - `semiconductor-eda/README.md` を source として7言語版を生成
    - 既存の `semiconductor-eda/README.en.md` は Language Switcher を追加して更新
    - 生成されたファイルの Language Switcher リンクが正しいことを確認
    - EDA 固有の技術用語（GDSII, DRC, OASIS, tapeout 等）が保持されていることを確認
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 2.1, 2.2, 2.3, 3.2, 3.3, 7.1, 7.2, 7.3, 7.4, 7.5_

- [x] 8. 残り13 UC フォルダの README 生成
  - [x] 8.1 全 UC フォルダの多言語 README を生成する
    - 残り13フォルダ（financial-idp, legal-compliance, healthcare-dicom, genomics-pipeline, media-vfx, autonomous-driving, construction-bim, education-research, energy-seismic, insurance-claims, logistics-ocr, manufacturing-analytics, retail-catalog）を処理
    - 各フォルダで7言語版 README を生成
    - 全ファイルの Language Switcher が統一フォーマットであることを確認
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 2.1, 2.2, 2.3, 7.1, 7.2, 7.3, 7.4, 7.5_

- [x] 9. Final checkpoint - 全体確認
  - Ensure all tests pass, ask the user if questions arise.
  - 全14フォルダ × 8言語の README が正しく生成されていることを確認
  - EDA デモ企画書が全要件を満たしていることを確認

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties defined in the design document
- Unit tests validate specific examples and edge cases
- EDA デモ企画書（Task 1）は EDA Summit が来週のため最優先で完成させる
- 翻訳は semiconductor-eda を先行実行し、残りは段階的に処理する
- Bedrock API のレート制限を考慮し、フォルダ間に適切な間隔を設ける

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "3.1"] },
    { "id": 1, "tasks": ["3.2", "4.1"] },
    { "id": 2, "tasks": ["3.3", "3.4", "3.5", "4.2", "4.3"] },
    { "id": 3, "tasks": ["4.4", "4.5", "4.6", "6.1"] },
    { "id": 4, "tasks": ["6.2", "6.3"] },
    { "id": 5, "tasks": ["7.1"] },
    { "id": 6, "tasks": ["8.1"] }
  ]
}
```
