# SAP/ERP Adjacent テストデータ

## ファイル一覧

| ファイル | カテゴリ | 説明 |
|---------|---------|------|
| `sample-idoc-orders.txt` | sap_idoc | SAP IDoc ORDERS05 形式のサンプル受注データ |
| `sample-hulft-transfer.csv` | hulft_transfer | HULFT 転送ログ CSV |
| `sample-edi-x12.edi` | edi_document | X12 850 (Purchase Order) EDI ドキュメント |

## 使用方法

1. FSx for ONTAP ボリュームの対象プレフィックス配下にファイルを配置
2. NFS/SMB マウント経由でコピー:

```bash
cp test-data/sap-erp-adjacent/* /mnt/fsxn/idoc-export/
```

3. Step Functions ワークフローを実行

## 注意事項

- これらはテスト用の合成データであり、実際の SAP/ERP データではありません
- 実環境では IDoc フォーマットは SAP システムのカスタマイズにより異なります
- EDI X12 フォーマットは取引先ごとにセグメント構成が異なる場合があります
