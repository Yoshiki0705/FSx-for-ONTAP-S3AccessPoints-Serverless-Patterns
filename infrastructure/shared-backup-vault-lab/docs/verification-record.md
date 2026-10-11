# Real-environment run: not yet done (status source: docs/verification-record.md)

> Language / 言語: 日本語 | [English](verification-record.en.md)

この文書は、共有ボールト検証ラボの状態の唯一の出所です。README と手順書の状態の行は、この文書を指します。

## 状態

実機での通しの日付と環境: 未実施。実機の記録の行は現在 0 件です。記録の行が 1 件も成立していない間、ラボ配下に `verified` / `検証済み` / `確認済み` と書くとテストが落ちます（下の「機械的な強制の限界」の規則）。

状態の行の文法には、全項目が成立するまでの中間状態があります。環境が排他で全項目を同時に満たせないため、成立した項目だけを並べます。

- 成立した記録が 0 件: `# Real-environment run: not yet done (status source: docs/verification-record.md)`
- 一部が成立: `# Real-environment run: recorded [V1][V4]; not recorded [E13] (status source: docs/verification-record.md)`
- `recorded` に並ぶのは現行のコードの digest で成立している項目、`not recorded` は残りです。`recorded` が空のときだけ `not yet done` と書きます。

## 検証項目の定義

公開側の V / E の定義はこの表が正です。README・手順書・06 / 07 の出力に出る番号は、全てここで引けます。`scripts:` の列は、その項目を出すスクリプトの番号です。`07-ui` は 07 の画面確認（`--ui`）のモードを指します。

| 項目 | 内容 | scripts |
|---|---|---|
| V1 | 受け手の `--by-shared` に共有ボールトが 1 件出て、ARN のアカウントが所有者、`VaultType` が LAG であること | scripts: 06 |
| V2 | 所有者の `--by-shared` が空であること（共有の方向の確認） | scripts: 06 |
| V3 | ポータルのロールで、共有ボールトの ARN が無い状態は拒否、足した状態は成功すること（2 段） | scripts: 07, 07-ui |
| V4 | `--backup-vault-account-id` を付けない呼び出しが `AccessDeniedException`、付けた呼び出しが成功すること | scripts: 06 |
| V5 | 配備済みの関数で `listSharedBackupVaults` がエラーなく成功し、画面でも共有ボールトが選べること | scripts: 07, 07-ui |
| V6 | 共有の取り消しから一覧に出なくなるまでの秒数と、その間のエラーコード、画面側の通知 | scripts: 07, 07-ui, 09 |
| V7 | 共有ボールトの復旧ポイントを受け手の SVM に復元できること | scripts: 06, 08 |
| V8 | AWS 管理キーの FS からのバックアップの扱い（否定側）。第 2 の FS が要るため別の判断とします | scripts: MANUAL（直接の API 観測。本ラボのスクリプトは出しません） |
| E1 | `aws cloudformation deploy` が `Rules` の不一致を拒否し、LAG ボールトのスタックが AVAILABLE まで進むこと | scripts: 03 |
| E2 | `AWS::RAM::ResourceShare` の `ResourceArns` / `Principals` で LAG ボールトを共有でき、組織共有が無効な環境で招待が PENDING になること | scripts: 03, 05 |
| E3 | CloudFormation で作った FS・SVM・ボリュームのタグが `fsx list-tags-for-resource` で読めること | scripts: 02 |
| E4 | `BackupRole` のインライン KMS ポリシーで、同一リージョンと別リージョンのコピーが成功すること | scripts: 04 |
| E5 | 別リージョンのコピーの所要時間と、失効日がコピー元の作成時刻 + N 日になること | scripts: 04, 06 |
| E6 | 別リージョンの復旧ポイントを、そのリージョンの受け手 FS に復元できること | scripts: 08 |
| E7 | 失敗したコピージョブを同じ冪等トークンで再試行したときの挙動（新しいジョブか、元のジョブか） | scripts: MANUAL（直接の `start-copy-job` でしか観測できません） |
| E8 | 受け手の専用ロール（Restores の管理ポリシーのみ）で復元が通ること | scripts: 08 |
| E9 | 復元メタデータの読み取りと書き込みのキーの差、ポータル経路が組み立てるメタデータでも通ること | scripts: 08 |
| E10 | LAG へのコピーのジョブに `StatusMessage` が付くかどうか（付けば「Completed with issues」の確認） | scripts: 04 |
| E11 | 共有を `ram delete-resource-share` で消した後の `delete-stack` が通ること | scripts: 10 |
| E12 | CloudFormation のボリューム削除の挙動と、API 削除の後にスタック削除する順序が通ること | scripts: 10 |
| E13 | 組織共有が有効な環境で招待なしにアクセスでき、`AllowExternalPrincipals=false` が通ること | scripts: 03, 05 |
| E14 | SSO トークンの残り分数の計算が、実際のキャッシュと一致すること | scripts: 01 |
| E15 | 価格 API の属性名と、見積もりの行の対応 | scripts: 01 |
| E16 | `describe-type` が、提供されないリージョンで `TypeNotFoundException` を返すこと。`SINGLE_AZ_1` が使えないリージョンで 02 の作成要求がその場で拒否されること | scripts: 01, 02 |
| E17 | `ResourceTypeOptInPreference` の `FSx` が `false` でも、ARN 指定のオンデマンドのバックアップが通ること | scripts: 01, 04 |
| E18 | `iam simulate-principal-policy` が SSO のロールに意味のある結果を返すこと、SCP / RCP が評価に含まれるか | scripts: 01 |
| E19 | 組織共有の状態が所有者のプロファイルから読めること（管理アカウントのとき） | scripts: 01 |
| E20 | Playwright spec が、実際のポータルの画面に対して通ること、`rpRestoreConfirm` が確認の前に無効であること | scripts: 07-ui |
| E21 | `ShareEnabled` の切り替えで、既に無い共有の削除が成功し、新しい共有と招待が作られること | scripts: 03, 05 |
| E22 | `aws cloudformation deploy --parameter-overrides file://…` が例ファイルを受理すること | scripts: MANUAL（直接デプロイの経路で観測。スクリプトは出しません） |
| E23 | CloudFormation の資源の権限の列挙が、実際に必要な権限を過不足なく覆うこと | scripts: MANUAL（権限不足はデプロイの実行でのみ観測。01 のシミュレーションは足りる保証になりません） |
| E24 | 別リージョンのコピージョブが、どのリージョンの `list-copy-jobs` に出るか（送信元、宛先、両方） | scripts: MANUAL（直接の `list-copy-jobs` の観測。04 / 10 は両方を読みますが、どちらに出るかは出力しません） |
| E25 | 07 `--ui` の起動経路が実機で働くこと（dev サーバーの起動、chromium の導入判定、レポートの読み取り） | scripts: 07-ui |
| E26 | `ce get-cost-and-usage` が `Project` タグのフィルタで値を返すこと、タグの付かない費用の扱い | scripts: 06 |

## 実機の記録

1 行 = 1 回の実行における 1 項目の結果です。行は 1 回の実行の結果であり、他の環境や規模への一般化ではありません。行は `python3 scripts/lib/lab_helpers.py record-row` が `lab-run.local.jsonl` から候補を印字し、アカウント ID と ARN をマスクして人が貼ります。自動では書きません。

項目は上の定義表の閉じた集合に含まれ、`結果` は `N✅ N❌ N⚠` の形で、`❌` が 0 かつ `✅` が 1 以上のとき、その項目を主張の根拠に使えます。`コードの digest` は 12 桁の 16 進で、現行のコードの digest と一致する行だけが成立します。`portal-ref` は V3・V5・V6・V7 の行で埋め、他は `-` です。

| 実施日（UTC） | リージョン | 構成 | AWS CLI | コードの digest | portal-ref | 項目 | 結果 | 所要 | 備考 |
|---|---|---|---|---|---|---|---|---|---|

（記録なし。実機での通しは未実施です。）

## 参考: 初回の手動観測

次は、スクリプト以外の手段での観測です。日付と n=1 を併記します。**これらは `verified` の根拠になりません**（これらのスクリプトの出力ではないため、最低ラインの第 3 項に照らして根拠にできません）。README のパラメータ表はこれらの値を写さず、この節へのリンクを持ちます。

| 観測 | 値 | 条件 |
|---|---|---|
| `LAB_ALLOW_EXTERNAL_PRINCIPALS=false` の成立条件 | 組織共有が有効なときだけ成立 | 2026-10-11、1 回観測。再現は未確認 |
| SSO トークンの寿命 | 1 時間 | 2026-10-11、1 回観測。`LAB_MIN_SSO_MINUTES` の既定 30 分はこの観測より短く置いています |
| ポータルのサインイン URL（`PORTAL_URL`） | 空のときローカルの dev サーバー | 2026-10-11、1 回観測。ブラウザでの実行は未実機 |
| 失効日 | 元バックアップの作成時刻 + 保持日数 N（N = 7） | 2026-10-11、1 回観測。コピー元のキーを早く削除したときの影響は未検証 |
| FS が AVAILABLE になるまで | 約 15 分 | 2026-10-11、1 回観測。タイムアウトは 60 分 |
| 同一リージョンのコピージョブ | 13 分 45 秒 | 2026-10-11、1 回観測。別リージョンは未観測 |
| 復元ジョブ | 21 分 17 秒 | 2026-10-11、1 回観測。同一リージョン・AWS 所有キーのボールトのみ |
| 共有の取り消しから一覧に出なくなるまで | 1〜8 秒 | 2026-10-11、1 回観測。5 秒間隔のポーリング |

## 機械的な強制の限界

`test_verification_record.py` が検査するのは、記録の行の形式、閉じた集合、プレースホルダーの不在、現行のコードの digest との一致です。**行が実機の実行に由来することは検査しません。** 行は人が実行の出力から作ります。したがって根拠の強さは、記録を貼る人の誠実さに依存する部分が残ります。これを減らすため、スクリプトは終了時に `digest=<12 桁> run=<ISO 8601 UTC>` を出力し、同じ内容を `lab-run.local.jsonl` に記録します。`record-row` はその記録から日付・digest・項目・結果の件数を写しますが、`lab-run.local.jsonl` 自体も実行した人のローカルファイルであり、偽造できないわけではありません。
