# OCR de documents japonais × agents IA — Textract (Tokyo) sur S3 Access Points

🌐 **Language / 言語**: [日本語](README.md) | [English](README.en.md) | [한국어](README.ko.md) | [简体中文](README.zh-CN.md) | [繁體中文](README.zh-TW.md) | Français | [Deutsch](README.de.md) | [Español](README.es.md)

Un exemple qui lit des documents numérisés (images, PDF, TIFF) situés sur des FSx for ONTAP S3 Access Points avec
Amazon Textract dans la région de Tokyo, et expose cette exécution comme outils d'agent IA via le connecteur
Step Functions d'Amazon Bedrock AgentCore Gateway. La prise en charge du japonais par Textract et sa disponibilité à
Tokyo ont été annoncées le 2026-11-02.

L'agent décide uniquement quelle collection lire, avec quel profil et combien de documents. La machine d'états gère
l'ordre des étapes, les nouvelles tentatives et le traitement des échecs. Le texte OCR n'est jamais transmis à
l'agent : il est écrit dans un bucket de résultats.

## Cas d'usage

- Appliquer l'OCR japonais à des numérisations (factures, contrats, notes) sans les déplacer du serveur de fichiers
- Faire dresser par un agent la liste des documents à faire vérifier par une personne, avec le motif de chacun
- Extraire, avec leur preuve, des champs comme le total d'une facture japonaise, là où Textract Forms n'est pas
  disponible (optionnel)

## Architecture

```
Agent IA ──MCP──▶ AgentCore Gateway (NONE | AWS_IAM)
                       │ GatewayServiceRole : states:StartExecution, etc.
                       ▼
           Standard StateMachine (Discover → Map → Report)
                       │
   Images : bytes vers Textract (sync)    PDF / TIFF : copie temporaire → Textract (async)
                       │
   S3 Access Points (S3 ordinaire en DemoMode) ──▶ bucket de résultats (result.json / text.txt / manifest.json)
```

Voir [docs/architecture.md](docs/architecture.md) pour le détail (en japonais).

## Outils exposés

| Outil | Entrée | Usage |
|---|---|---|
| `ocr___StartExecution` | `input` (chaîne JSON) | Lance l'OCR. Renvoie `executionArn` |
| `ocr___DescribeExecution` | `executionArn`, `includedData: "ALL_DATA"` | État et résultat |
| `ocr___ListExecutions` | `statusFilter` (optionnel) | Exécutions récentes |
| `ocr___GetExecutionHistory` | `executionArn` | Trouver où une exécution s'est arrêtée (sortie volumineuse) |
| `ocr___DescribeStateMachine` | `includedData` (optionnel) | Consulter la définition |

L'ARN de la machine d'états est fixé et ne figure dans aucun outil : l'agent ne peut pas le modifier.
`DescribeExecution` sans `includedData: "ALL_DATA"` ne renvoie ni `output` ni, pour une exécution FAILED, `error` et `cause`.

## Entrée transmise par l'agent

```json
{"collection": "invoices", "profile": "structure", "max_files": 20, "modified_after": "2026-10-01"}
```

| Clé | Obligatoire | Règle |
|---|---|---|
| `collection` | Oui | Identifiant ASCII (`^[A-Za-z0-9][A-Za-z0-9_-]{0,31}$`) présent dans la liste autorisée (`CollectionsJson`) |
| `profile` | Non | `text` (caractères seuls) ou `structure` (caractères, tableaux, mise en page). Par défaut, celui de la collection |
| `max_files` | Non | Entier de 1 à `MaxFilesPerExecution`. Les documents sont pris dans l'ordre des clés |
| `modified_after` | Non | `YYYY-MM-DD`. Seuls les documents modifiés à cette date ou après |

Les chemins et clés S3 ne sont pas acceptés. Une clé inconnue ou une règle non respectée termine l'exécution en FAILED,
et `Cause` indique comment corriger.

## Parcours et profils

| Document | Parcours | Remarque |
|---|---|---|
| PNG / JPEG, jusqu'à 5 MiB | Sync, bytes transmis directement | Aucune copie |
| PNG / JPEG, de plus de 5 MiB à 10 MiB | Async, copie temporaire | |
| PDF / TIFF | Async, copie temporaire | Le nombre de pages n'est pas estimé |

`text` appelle `DetectDocumentText` ; `structure` appelle `AnalyzeDocument` (`TABLES` et `LAYOUT`). Forms, Queries,
AnalyzeExpense et AnalyzeID ne sont pas proposés (non pris en charge pour le japonais, ou non autorisés à Tokyo).

## Ce que reçoit l'agent

Le `output` de `DescribeExecution` (`ALL_DATA`) contient l'état, les compteurs, la confiance moyenne, la liste à faire
vérifier avec le motif de chacun, et l'URI S3 du résultat de chaque document. Il ne contient aucun texte OCR, mais
inclut la clé d'origine (nom de fichier). Avec l'extraction de champs activée, il contient aussi les valeurs des champs
(60 caractères au plus). La liste complète se trouve dans `manifest.json`, dans le bucket de résultats.

## Paramètres

| Paramètre | Description | Valeur par défaut |
|---|---|---|
| `S3AccessPointAlias` | Alias des S3 Access Points (nom d'un bucket ordinaire en DemoMode) | (obligatoire) |
| `DemoMode` | `true` fonctionne sans FSx for ONTAP | `false` |
| `CollectionsJson` | Liste autorisée de collections (JSON). Si vide, une collection est construite depuis `FilePrefix` | `""` |
| `MaxFilesPerExecution` | Nombre maximal de documents par exécution (1–100) | `50` |
| `MapConcurrency` | Documents traités en parallèle. L'API sync de Tokyo est limitée à 1 TPS | `2` |
| `AsyncJobMaxSeconds` | Durée d'attente d'un job asynchrone | `600` |
| `EnableFieldExtraction` | Extraction de champs avec Bedrock. Désactivée : aucune permission Bedrock n'est accordée | `false` |
| `BedrockModelId` | ID de modèle ou de profil d'inférence pour l'extraction ([docs/bedrock-inference-profiles.md](../../../docs/bedrock-inference-profiles.md)) | `apac.amazon.nova-pro-v1:0` |
| `DataClassification` | Étiquette de classification des données par défaut sur les sorties | `INTERNAL` |
| `ReviewAutoApproveThreshold` / `ReviewRejectThreshold` | Seuils de confiance moyenne | `0.95` / `0.30` |
| `LowConfidenceLineThreshold` / `LowConfidenceCharRatioLimit` | Ce qui compte comme ligne à faible confiance, et la part de caractères qui envoie un document en revue | `90` / `0.05` |
| `HandwritingWordRatioLimit` | Part maximale de mots détectés comme manuscrits | `0.05` |
| `GatewayAuthorizerType` | `NONE` (PoC uniquement) ou `AWS_IAM` | `NONE` |
| `GatewayName` | Nom de la Gateway | `ja-ocr-agent-gateway` |
| `NotificationEmail` | Adresse de notification SNS (vide pour ignorer) | `""` |

## Déploiement

Le script de déploiement exécute `sam build`, `sam package` puis `aws cloudformation deploy`, puis vérifie la valeur
enregistrée de `CollectionsJson` et `tools/list`.

```bash
# DemoMode (sans FSx for ONTAP)
./scripts/deploy-japanese-document-ocr-agent.sh --s3ap-alias <demo-bucket> --demo-mode \
  --collections-file collections.json --stack-name ja-ocr-agent-demo

# S3 Access Points. Exiger des appels signés et activer l'extraction de champs
./scripts/deploy-japanese-document-ocr-agent.sh --s3ap-alias <your-ap>-ext-s3alias \
  --collections-file collections.json --auth iam --enable-field-extraction --stack-name ja-ocr-agent

# Nettoyage (--delete-results supprime aussi le bucket de résultats, qui contient le texte OCR)
./scripts/deploy-japanese-document-ocr-agent.sh --cleanup --stack-name ja-ocr-agent --delete-results
```

La rédaction des collections, le prompt système de l'agent et des exemples de conversation sont dans
[docs/demo-guide.md](docs/demo-guide.md) (en japonais).

## Seuils de Human Review

La confiance moyenne de l'OCR (pondérée par le nombre de caractères) est évaluée avec `shared/human_review.py`, puis
relevée selon les conditions suivantes.

| Condition | Décision |
|---|---|
| Confiance moyenne supérieure ou égale à `ReviewAutoApproveThreshold` (0.95) et aucune des conditions ci-dessous | AUTO_APPROVE |
| Confiance moyenne inférieure à 0.95 | HUMAN_REVIEW |
| Confiance moyenne inférieure à `ReviewRejectThreshold` (0.30) | REJECT |
| Plus de 5 % des caractères sont dans des lignes de confiance inférieure à 90 | Relevé à HUMAN_REVIEW |
| Plus de 5 % des mots sont détectés comme manuscrits | Relevé à HUMAN_REVIEW |
| Un tableau à la structure douteuse, par exemple une cellule fusionnée | Relevé à HUMAN_REVIEW |
| Aucune ligne détectée | HUMAN_REVIEW |
| L'extraction de champs a un champ sans preuve, ou a échoué | Relevé à HUMAN_REVIEW (REJECT n'est pas modifié) |

Les valeurs par défaut sont un point de départ, pas des optimums mesurés. Dans une exécution sur quatre documents
fictifs, les quatre sont passés en HUMAN_REVIEW avec les valeurs par défaut, y compris un contrat sans aucune erreur de
caractère ([docs/success-metrics.md](docs/success-metrics.md)). Mesurez la distribution sur vos propres documents avant
de choisir. La décision est seulement incluse dans le résultat ; le modèle ne prend pas la décision finale. `result.json`
contient la décision fondée sur l'OCR seul. La décision finale, extraction de champs comprise, figure dans
`manifest.json` et dans le résultat d'exécution.

## Classification des données

Les sorties portent un `data_classification` issu de `shared/data_classification.py`. La valeur par défaut est
`INTERNAL` ; modifiez-la avec `DataClassification`, ou remplacez-la par collection avec `classification`. Le bucket de
résultats utilise SSE-KMS, bloque l'accès public, refuse les requêtes non TLS et est conservé à la suppression de la
pile.

## Extraction de champs (optionnelle)

Avec `EnableFieldExtraction=true`, les champs listés dans `fields` d'une collection (20 au plus, 40 caractères chacun au
plus) sont extraits avec l'API Bedrock Converse. Le modèle renvoie chaque valeur avec une citation du texte source, et le
code vérifie mécaniquement que la citation existe dans le texte OCR (correspondance de sous-chaîne après normalisation NFKC
et suppression des espaces). Un champ dont la citation est introuvable est `grounded: false`, et un seul suffit à envoyer
le document en HUMAN_REVIEW. Un champ que le document ne contient pas compte aussi comme sans preuve : ne listez dans
`fields` que des éléments présents dans tous les documents de la collection.

## Governance Note

- La confiance de l'OCR est un signal d'aide, pas une décision finale. Dans l'exécution mesurée, un document sans aucune
  erreur avait 22,6 % de ses caractères dans des lignes de confiance inférieure à 90, et une ligne mal lue (« 括孤 »)
  avait une confiance de 98,2. Ne faites pas de la confiance la seule condition d'approbation automatique.
- Les valeurs de champs extraites sont une sortie de LLM. La vérification des citations réduit les inventions mais ne
  garantit pas l'exactitude.
- Les valeurs tirées du contenu d'un document sont une entrée non fiable pour un agent. Indiquez dans son prompt système
  de ne pas suivre les instructions qui apparaîtraient dans une valeur. Le comportement avec un document contenant des
  instructions n'a pas été mesuré.
- Les PDF et TIFF sont copiés dans un bucket temporaire du même compte et de la même région pendant leur traitement
  (SSE-KMS, accès public bloqué, suppression à la fin du job, règle de cycle de vie de 1 jour en filet de sécurité). Si
  votre politique n'autorise pas les copies, limitez les `suffixes` de la collection aux images.
- `GatewayAuthorizerType=NONE` permet à toute personne connaissant l'URL de lancer des exécutions OCR (aucun texte n'est
  renvoyé). À réserver à un PoC ; utilisez `AWS_IAM` dans les environnements partagés. Le type d'authorizer ne peut pas
  être modifié après la création.
- Textract ne peut pas annuler un job démarré. Cesser d'attendre à `AsyncJobMaxSeconds` n'arrête pas la facturation.
- Ceci est une orientation de gouvernance, pas un substitut à une appréciation juridique ou de conformité.

## Performance Considerations

- L'API sync de Tokyo est limitée à 1 TPS. Sur 20 appels consécutifs, un client sans nouvelle tentative a été limité 4
  fois avec 2 workers et 7 fois avec 5 ; un client adaptive (5 tentatives au plus) l'a été 0 fois avec 1, 2 et 5.
  `MapConcurrency` vaut 2 par défaut.
- Un PDF de 3 pages (async) s'est terminé en environ 12 secondes via le modèle.
- Événements d'historique d'exécution : 13 par document sync, et 20 + 9 × interrogations par document async. Le pire cas
  pour 100 documents est estimé à environ 23 200, sous la limite Standard de 25 000.
- Pour garder l'état du Map sous 256 KiB, des clés très longues amènent discovery à sélectionner moins de documents que
  `max_files` et à renvoyer `truncated`.
- Le coût Textract est calculé par page. Le Price List de Tokyo indique 0,0015 USD par page pour `text` et 0,019 USD par
  page pour `structure` (Tables plus Layout), en vigueur depuis le 2026-10-01 ; non rapproché d'une facture.

## Tests

```bash
python3 -m pytest solutions/genai/japanese-document-ocr-agent/tests/ shared/tests/test_textract_helper.py -v
```

## Points d'attention connus

- Forms ne prend pas en charge le japonais. La requête est acceptée, mais sur la note elle a renvoyé des paires coupées au
  milieu d'une phrase.
- `DescribeExecution` exige `includedData: "ALL_DATA"`. `GetExecutionHistory` ne peut pas être paginé.
- Le japonais dans une entrée de Gateway devient `??`. Ce modèle ne transmet que des identifiants ASCII.
- `max_files` prend les documents dans l'ordre des clés : un premier document corrompu est donc choisi à chaque fois.
- Les S3 Access Points de l'environnement de vérification ne contenaient ni image ni PDF ; un succès de l'OCR sur un
  Access Point réel n'a donc pas été confirmé (la liste, la lecture et la suppression de la copie temporaire l'ont été).
  Voir « 既知の注意点 » dans [docs/demo-guide.md](docs/demo-guide.md).

## Références

- [Amazon Textract ajoute le japonais et d'autres langues et arrive à Tokyo (What's New)](https://aws.amazon.com/jp/about-aws/whats-new/2026/11/textract-tokyo-zurich/)
- [AWS Step Functions as Connector Target (officiel)](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/gateway-target-connector-step-functions.html)
- Modèle associé : [stepfunctions-agentcore-tools](../stepfunctions-agentcore-tools/)

---

<!-- playbook-reading:start -->
## À lire avant la mise en production

La façon de traduire en décisions de conception les contraintes qui apparaissent après le déploiement est documentée dans le [FSx for ONTAP Adoption Playbook](https://github.com/Yoshiki0705/FSx-for-ONTAP-Adoption-Playbook). Un même contenu présent à deux endroits laisse survivre la copie qui a cessé d'être mise à jour.

- [Exploitation des données](https://github.com/Yoshiki0705/FSx-for-ONTAP-Adoption-Playbook/tree/main/docs/en/domains/data-utilization) — contraintes de l'accès via un access point (tous les patterns)
- [Sécurité et gouvernance](https://github.com/Yoshiki0705/FSx-for-ONTAP-Adoption-Playbook/tree/main/docs/en/domains/security-governance) — là où se concentrent les décisions pour ce pattern
- [Construire](https://github.com/Yoshiki0705/FSx-for-ONTAP-Adoption-Playbook/tree/main/docs/en/playbooks/04-build) — à parcourir avant la production (tous les patterns)
<!-- playbook-reading:end -->
