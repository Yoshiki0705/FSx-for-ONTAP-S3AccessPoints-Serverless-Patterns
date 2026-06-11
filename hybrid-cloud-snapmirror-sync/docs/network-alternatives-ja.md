# 会場ネットワーク — VPN 代替接続方式

[日本語](network-alternatives-ja.md) | [English](network-alternatives-en.md)

イベント会場のネットワークでは Site-to-Site VPN の構成が困難な場合があります（ルーターへのアクセス権がない等）。本ドキュメントでは代替方式を解説します。

---

## 接続要件の整理

Sync Server（会場 PC）から FSx for ONTAP の管理エンドポイントに HTTPS (TCP 443) で到達する必要があります。

| 方式 | 要件 | 難易度 | 推奨場面 |
|------|------|--------|---------|
| Site-to-Site VPN | 会場ルーターに設定可能 | 高 | 自社オフィスでの常設デモ |
| **AWS Client VPN** | PC にクライアントインストール | 中 | **イベント会場（推奨）** |
| SSH トンネル | 踏み台 EC2 + SSH 接続 | 低 | 緊急時のバックアップ |
| WireGuard on EC2 | EC2 に WireGuard サーバー | 中 | モバイル回線バックアップ |

---

## 方式 1: AWS Client VPN（推奨）

PC 単体で AWS VPC に接続可能。会場ネットワークの変更不要。

### セットアップ手順

```bash
# 1. 証明書を生成（ACM に登録）
git clone https://github.com/OpenVPN/easy-rsa.git
cd easy-rsa/easyrsa3
./easyrsa init-pki
./easyrsa build-ca nopass
./easyrsa build-server-full server nopass
./easyrsa build-client-full client1 nopass

# 2. ACM に証明書をインポート
aws acm import-certificate \
  --certificate fileb://pki/issued/server.crt \
  --private-key fileb://pki/private/server.key \
  --certificate-chain fileb://pki/ca.crt \
  --region ap-northeast-1

# 3. Client VPN Endpoint を作成（コンソールまたは CLI）
aws ec2 create-client-vpn-endpoint \
  --client-cidr-block 10.100.0.0/16 \
  --server-certificate-arn <ACM_SERVER_CERT_ARN> \
  --authentication-options 'Type=certificate-authentication,MutualAuthentication={ClientRootCertificateChainArn=<ACM_CA_ARN>}' \
  --connection-log-options 'Enabled=false' \
  --vpc-id <VPC_ID> \
  --region ap-northeast-1

# 4. VPN エンドポイントにサブネットを関連付け
aws ec2 associate-client-vpn-target-network \
  --client-vpn-endpoint-id <ENDPOINT_ID> \
  --subnet-id <PRIVATE_SUBNET_1_ID>

# 5. 認可ルール追加（全 VPC CIDR へのアクセス許可）
aws ec2 authorize-client-vpn-ingress \
  --client-vpn-endpoint-id <ENDPOINT_ID> \
  --target-network-cidr 10.0.0.0/16 \
  --authorize-all-groups

# 6. クライアント設定ファイルをダウンロード
aws ec2 export-client-vpn-client-configuration \
  --client-vpn-endpoint-id <ENDPOINT_ID> \
  --output text > client-vpn-config.ovpn

# 7. クライアント証明書を設定ファイルに追加
echo "<cert>" >> client-vpn-config.ovpn
cat pki/issued/client1.crt >> client-vpn-config.ovpn
echo "</cert>" >> client-vpn-config.ovpn
echo "<key>" >> client-vpn-config.ovpn
cat pki/private/client1.key >> client-vpn-config.ovpn
echo "</key>" >> client-vpn-config.ovpn
```

### PC からの接続

```bash
# macOS: AWS VPN Client アプリをインストール
# https://aws.amazon.com/vpn/client-vpn-download/

# または OpenVPN クライアント
brew install openvpn
sudo openvpn --config client-vpn-config.ovpn
```

接続後、FSx 管理エンドポイントに到達可能:
```bash
curl -k https://management.fs-xxx.fsx.ap-northeast-1.amazonaws.com/api/cluster
```

### コスト

- Client VPN Endpoint: ~$0.10/時間 (~$72/月)
- 接続あたり: ~$0.05/時間
- デモ期間のみ起動で $5-10 程度

---

## 方式 2: SSH トンネル（踏み台 EC2 経由）

最もシンプルな緊急手段。EC2 を踏み台にして FSx 管理 LIF にポートフォワード。

### 前提

- VPC 内に t3.micro 等の EC2 を起動（パブリックサブネット or Session Manager）
- セキュリティグループで SSH (22) を許可

### 接続

```bash
# EC2 経由で FSx 管理 LIF の 443 をローカルにフォワード
ssh -i key.pem -L 8443:<FSx_Management_IP>:443 ec2-user@<EC2_PUBLIC_IP>

# 別ターミナルで .env を変更
ONTAP_HOST=localhost:8443
```

または Systems Manager Session Manager 経由（SSH 鍵不要）:
```bash
aws ssm start-session \
  --target <EC2_INSTANCE_ID> \
  --document-name AWS-StartPortForwardingSessionToRemoteHost \
  --parameters '{"host":["<FSx_Management_IP>"],"portNumber":["443"],"localPortNumber":["8443"]}'
```

### コスト

- t3.micro: ~$0.013/時間 (デモ日のみで $1 未満)

---

## 方式 3: WireGuard on EC2（モバイル回線バックアップ）

モバイルテザリングからも AWS VPC に接続可能にする軽量 VPN。

### EC2 に WireGuard サーバーを構築

```bash
# EC2 (Amazon Linux 2023) で実行
sudo dnf install -y wireguard-tools
wg genkey | tee /etc/wireguard/server_private.key | wg pubkey > /etc/wireguard/server_public.key

# /etc/wireguard/wg0.conf を作成
sudo systemctl enable --now wg-quick@wg0
```

### PC からの接続

```bash
brew install wireguard-tools
# 設定ファイルを /etc/wireguard/wg0.conf に配置
sudo wg-quick up wg0
```

---

## イベント当日の推奨構成

```
[会場 PC]
  ├─ 通常時: AWS Client VPN (会場 WiFi 経由)
  └─ バックアップ: SSH トンネル (モバイルテザリング経由)
```

**Day -1 のリハーサルで両方の接続を確認しておくこと。**
