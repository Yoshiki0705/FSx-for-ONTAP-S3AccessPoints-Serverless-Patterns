# Step Functions × AgentCore Gateway — Des workflows comme outils d'agent IA

🌐 **Language / 言語**: [日本語](README.md) | [English](README.en.md) | [한국어](README.ko.md) | [简体中文](README.zh-CN.md) | [繁體中文](README.zh-TW.md) | Français | [Deutsch](README.de.md) | [Español](README.es.md)

Un exemple qui expose un workflow Step Functions Standard (Découverte → Traitement →
Rapport) portant sur des fichiers sur FSx for ONTAP S3 Access Points comme outils
d'agent IA, via le connecteur Step Functions intégré d'Amazon Bedrock AgentCore Gateway.

L'agent décide quand exécuter le workflow et quelle entrée transmettre ; la machine à
états garantit l'ordre des étapes. La séquence approuvée reste dans le workflow, la
décision de lancement revient à l'agent.

## Cas d'usage

- Déclencher un workflow Step Functions existant depuis un agent sans modifier la machine à états
- Garder les étapes et les approbations dans le workflow, ne déléguer que la décision d'exécution
- Laisser l'agent inspecter la progression d'une exécution via l'historique

## Architecture

```
Agent IA ──MCP──▶ AgentCore Gateway (connecteur Step Functions)
                    │ GatewayServiceRole → states:StartExecution, etc.
                    ▼
           Standard StateMachine (Discover→Choice→Map→Report)
                    │
       Discovery / Processing / Report Lambda
                    │
              S3 Access Point (FSx for ONTAP / S3 ordinaire en DemoMode)
```

Voir [docs/architecture.md](docs/architecture.md) pour les détails.

## Outils exposés

| Outil | Entrée | Usage |
|---|---|---|
| `workflow___StartExecution` | `input` (chaîne JSON) | Démarrer le workflow |
| `workflow___ListExecutions` | `statusFilter` (optionnel) | Lister les exécutions (Standard uniquement) |
| `workflow___DescribeStateMachine` | `includedData` (optionnel) | Métadonnées/définition de la machine à états |
| `workflow___DescribeExecution` | `executionArn`, `includedData` | Vérifier l'état et le résultat |
| `workflow___GetExecutionHistory` | `executionArn` | Historique des étapes |

L'ARN épinglé de la machine à états n'apparaît pas dans l'outil et l'agent ne peut pas le changer.

## Paramètres

| Paramètre | Description | Par défaut |
|---|---|---|
| `S3AccessPointAlias` | Alias S3 AP du volume FSx for ONTAP (nom de bucket ordinaire en DemoMode) | (requis) |
| `DemoMode` | `true` fonctionne sans FSx for ONTAP (bucket S3 ordinaire) | `false` |
| `FilePrefix` | Préfixe à parcourir | `input/` |
| `BedrockModelId` | Modèle de résumé / ID de profil d'inférence ([docs/bedrock-inference-profiles.md](../../../docs/bedrock-inference-profiles.md)) | `apac.amazon.nova-pro-v1:0` |
| `MaxFilesPerExecution` | Nombre max de fichiers par exécution | `100` |
| `NotificationEmail` | Destinataire SNS (vide pour ignorer) | `""` |
| `GatewayName` | Nom du Gateway (utilisé par le script de déploiement) | `sfn-agentcore-tools-gateway` |

## Déploiement

Le Gateway et la cible connecteur sont des ressources CloudFormation de première
classe (`AWS::BedrockAgentCore::Gateway` / `GatewayTarget`), donc tout le motif tient
dans un seul modèle déclaratif. Le script de déploiement est un wrapper
`sam build` + `sam deploy` qui vérifie `tools/list` ensuite.

```bash
# DemoMode (sans FSx for ONTAP)
./scripts/deploy-stepfunctions-agentcore.sh \
  --s3ap-alias my-demo-bucket --demo-mode --stack-name sfn-agentcore-tools-demo

# Production (S3 AP)
./scripts/deploy-stepfunctions-agentcore.sh \
  --s3ap-alias <your-ap>-ext-s3alias --stack-name sfn-agentcore-tools

# Nettoyage
./scripts/deploy-stepfunctions-agentcore.sh --cleanup --stack-name sfn-agentcore-tools
```

Les exemples de conversation et les étapes de vérification sont dans [docs/demo-guide.md](docs/demo-guide.md).

## Seuils de Human Review

Le Lambda Processing évalue la confiance du résumé avec `shared/human_review.py`.

| Confiance | Décision |
|---|---|
| `>= 0.85` (par défaut `HUMAN_REVIEW_AUTO_APPROVE_THRESHOLD`) | AUTO_APPROVE |
| `>= 0.30` (par défaut `HUMAN_REVIEW_REJECT_THRESHOLD`) et `< 0.85` | HUMAN_REVIEW |
| `< 0.30` | REJECT |

Les seuils sont modifiables via des variables d'environnement. La décision est portée
dans le résultat ; ce modèle n'agit pas automatiquement dessus.

## Classification des données

Le Lambda Report étiquette la sortie avec `data_classification` de
`shared/data_classification.py` (par défaut `INTERNAL`, modifiable via `DATA_CLASSIFICATION`).

## Governance Note

- L'agent ne décide que du moment d'exécution et vérifie l'état. L'ordre, les branches
  et les approbations sont garantis par la machine à états ; l'agent ne peut ni les
  sauter ni les réordonner.
- L'ARN épinglé n'est pas exposé, donc l'agent ne peut pas démarrer une autre machine à états.
- Le résumé/classement IA est un **signal d'assistance**, pas une décision finale.
  Une confiance sous le seuil est routée vers la revue humaine.
- Les opérations par jeton de tâche (`SendTaskSuccess`, etc.) ne sont pas exposées ici,
  car IAM ne peut pas les limiter à des exécutions spécifiques.
- Il s'agit d'orientations de gouvernance, pas d'un avis juridique ou de conformité.

## Tests

```bash
python3 -m pytest solutions/genai/stepfunctions-agentcore-tools/tests/ -v
```

## Points d'attention connus

La contrainte de même région, un pin par opération, le mojibake `?` des entrées
japonaises et le contournement `\uXXXX`, et la limite Cedar sur `input` sont réunis dans
[docs/demo-guide.md](docs/demo-guide.md#既知の注意点).

## Références

- [AWS Step Functions as Connector Target (officiel)](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/gateway-target-connector-step-functions.html)
- [AWS Step Functions workflows now available as AI agent tools (What's New)](https://aws.amazon.com/about-aws/whats-new/2026/10/step-functions-workflows-ai-agent-tools/)
