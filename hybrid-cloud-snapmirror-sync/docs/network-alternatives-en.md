# Venue Network — VPN Alternative Connection Methods

[日本語](network-alternatives-ja.md) | [English](network-alternatives-en.md)

At event venues, configuring Site-to-Site VPN may be difficult (e.g., no access to the venue router). This document covers alternative methods.

---

## Connection Requirements

The Sync Server (venue PC) needs HTTPS (TCP 443) connectivity to the FSx for ONTAP management endpoint.

| Method | Requirements | Difficulty | Recommended For |
|--------|-------------|-----------|-----------------|
| Site-to-Site VPN | Router configuration access at venue | High | Permanent demos at own office |
| **AWS Client VPN** | Client software installed on PC | Medium | **Event venues (recommended)** |
| SSH Tunnel | Bastion EC2 + SSH access | Low | Emergency backup |
| WireGuard on EC2 | WireGuard server on EC2 | Medium | Mobile connection backup |

---

## Method 1: AWS Client VPN (Recommended)

Single PC can connect to AWS VPC. No venue network changes required.

### Setup Steps

```bash
# 1. Generate certificates (register with ACM)
git clone https://github.com/OpenVPN/easy-rsa.git
cd easy-rsa/easyrsa3
./easyrsa init-pki
./easyrsa build-ca nopass
./easyrsa build-server-full server nopass
./easyrsa build-client-full client1 nopass

# 2. Import certificate to ACM
aws acm import-certificate \
  --certificate fileb://pki/issued/server.crt \
  --private-key fileb://pki/private/server.key \
  --certificate-chain fileb://pki/ca.crt \
  --region ap-northeast-1

# 3. Create Client VPN Endpoint (console or CLI)
aws ec2 create-client-vpn-endpoint \
  --client-cidr-block 10.100.0.0/16 \
  --server-certificate-arn <ACM_SERVER_CERT_ARN> \
  --authentication-options 'Type=certificate-authentication,MutualAuthentication={ClientRootCertificateChainArn=<ACM_CA_ARN>}' \
  --connection-log-options 'Enabled=false' \
  --vpc-id <VPC_ID> \
  --region ap-northeast-1

# 4. Associate subnet with VPN endpoint
aws ec2 associate-client-vpn-target-network \
  --client-vpn-endpoint-id <ENDPOINT_ID> \
  --subnet-id <PRIVATE_SUBNET_1_ID>

# 5. Add authorization rule (allow access to entire VPC CIDR)
aws ec2 authorize-client-vpn-ingress \
  --client-vpn-endpoint-id <ENDPOINT_ID> \
  --target-network-cidr 10.0.0.0/16 \
  --authorize-all-groups

# 6. Download client configuration file
aws ec2 export-client-vpn-client-configuration \
  --client-vpn-endpoint-id <ENDPOINT_ID> \
  --output text > client-vpn-config.ovpn

# 7. Append client certificate to configuration file
echo "<cert>" >> client-vpn-config.ovpn
cat pki/issued/client1.crt >> client-vpn-config.ovpn
echo "</cert>" >> client-vpn-config.ovpn
echo "<key>" >> client-vpn-config.ovpn
cat pki/private/client1.key >> client-vpn-config.ovpn
echo "</key>" >> client-vpn-config.ovpn
```

### Connect from PC

```bash
# macOS: Install AWS VPN Client app
# https://aws.amazon.com/vpn/client-vpn-download/

# Or OpenVPN client
brew install openvpn
sudo openvpn --config client-vpn-config.ovpn
```

Once connected, the FSx management endpoint is reachable:
```bash
curl -k https://management.fs-xxx.fsx.ap-northeast-1.amazonaws.com/api/cluster
```

### Cost

- Client VPN Endpoint: ~$0.10/hour (~$72/month)
- Per connection: ~$0.05/hour
- Demo-period only: ~$5-10

---

## Method 2: SSH Tunnel (via Bastion EC2)

Simplest emergency method. Port-forward FSx management LIF through an EC2 bastion.

### Prerequisites

- EC2 instance (t3.micro, etc.) running in the VPC (public subnet or Session Manager)
- Security group allows SSH (22)

### Connection

```bash
# Forward FSx management LIF port 443 to local via EC2
ssh -i key.pem -L 8443:<FSx_Management_IP>:443 ec2-user@<EC2_PUBLIC_IP>

# In another terminal, modify .env
ONTAP_HOST=localhost:8443
```

Or via Systems Manager Session Manager (no SSH key needed):
```bash
aws ssm start-session \
  --target <EC2_INSTANCE_ID> \
  --document-name AWS-StartPortForwardingSessionToRemoteHost \
  --parameters '{"host":["<FSx_Management_IP>"],"portNumber":["443"],"localPortNumber":["8443"]}'
```

### Cost

- t3.micro: ~$0.013/hour (under $1 for demo day only)

---

## Method 3: WireGuard on EC2 (Mobile Connection Backup)

Lightweight VPN that enables connection to AWS VPC even from mobile tethering.

### Build WireGuard Server on EC2

```bash
# Run on EC2 (Amazon Linux 2023)
sudo dnf install -y wireguard-tools
wg genkey | tee /etc/wireguard/server_private.key | wg pubkey > /etc/wireguard/server_public.key

# Create /etc/wireguard/wg0.conf
sudo systemctl enable --now wg-quick@wg0
```

### Connect from PC

```bash
brew install wireguard-tools
# Place config file at /etc/wireguard/wg0.conf
sudo wg-quick up wg0
```

---

## Recommended Configuration for Demo Day

```
[Venue PC]
  ├─ Primary: AWS Client VPN (via venue WiFi)
  └─ Backup: SSH Tunnel (via mobile tethering)
```

**Verify both connections during Day -1 rehearsal.**
