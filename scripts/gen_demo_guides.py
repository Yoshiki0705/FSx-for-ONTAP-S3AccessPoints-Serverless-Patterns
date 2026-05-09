#!/usr/bin/env python3
"""Generate multilingual demo-guide files for all UCs."""

import os

BASE = "/Users/yoshiki/Downloads/fsxn-s3ap-serverless-patterns"

# UC configurations: (dir_name, title_ja, title_en, title_ko, title_zhCN, title_zhTW, title_fr, title_de, title_es, workflow_desc)
UCS = [
    ("legal-compliance",
     "파일 서버 권한 감사",
     "文件服务器权限审计",
     "檔案伺服器權限稽核",
     "Audit des permissions du serveur de fichiers",
     "Dateiserverberechtigungs-Audit",
     "Auditoría de permisos del servidor de archivos",
     "파일 서버의 과도한 접근 권한을 자동 감지하는 감사 워크플로우를 시연합니다. NTFS ACL을 분석하여 최소 권한 원칙을 위반하는 항목을 식별하고 컴플라이언스 보고서를 자동 생성합니다.",
     "本演示展示了自动检测文件服务器过度访问权限的审计工作流。分析NTFS ACL，识别违反最小权限原则的条目，并自动生成合规报告。",
     "本演示展示了自動偵測檔案伺服器過度存取權限的稽核工作流程。分析NTFS ACL，識別違反最小權限原則的項目，並自動產生合規報告。",
     "Cette démo présente un workflow d'audit automatisé qui détecte les permissions d'accès excessives sur les serveurs de fichiers. Il analyse les ACL NTFS, identifie les entrées violant le principe du moindre privilège et génère automatiquement des rapports de conformité.",
     "Diese Demo zeigt einen automatisierten Audit-Workflow, der übermäßige Zugriffsberechtigungen auf Dateiservern erkennt. Er analysiert NTFS-ACLs, identifiziert Einträge, die das Prinzip der geringsten Berechtigung verletzen, und generiert automatisch Compliance-Berichte.",
     "Esta demo muestra un flujo de trabajo de auditoría automatizado que detecta permisos de acceso excesivos en servidores de archivos. Analiza las ACL NTFS, identifica entradas que violan el principio de mínimo privilegio y genera automáticamente informes de cumplimiento.",
     "수주가 걸리는 파일 서버 권한 감사를 자동화하여 과도한 권한 리스크를 즉시 가시화합니다.",
     "将需要数周的文件服务器权限审计自动化，即时可视化过度权限风险。",
     "將需要數週的檔案伺服器權限稽核自動化，即時視覺化過度權限風險。",
     "Automatiser les audits de permissions de serveurs de fichiers qui prendraient des semaines manuellement, visualisant instantanément les risques de permissions excessives.",
     "Automatisierung von Dateiserver-Berechtigungsaudits, die manuell Wochen dauern würden, mit sofortiger Visualisierung übermäßiger Berechtigungsrisiken.",
     "Automatizar auditorías de permisos de servidores de archivos que tomarían semanas manualmente, visualizando instantáneamente los riesgos de permisos excesivos.",
     # Workflow
     "파일 서버 → ACL 수집 → 권한 분석 → 감사 보고서",
     "文件服务器 → ACL收集 → 权限分析 → 审计报告",
     "檔案伺服器 → ACL收集 → 權限分析 → 稽核報告",
     "Serveur de fichiers → Collecte ACL → Analyse des permissions → Rapport d'audit",
     "Dateiserver → ACL-Sammlung → Berechtigungsanalyse → Audit-Bericht",
     "Servidor de archivos → Recopilación ACL → Análisis de permisos → Informe de auditoría",
     # Storyboard sections
     ["문제 제기: 수천 개 폴더의 권한 감사를 수동으로 수행하는 것은 비현실적",
      "워크플로우 트리거: 대상 볼륨을 지정하고 감사 시작",
      "ACL 분석: ACL을 자동 수집하고 정책 위반 감지",
      "결과 검토: 위반 건수와 리스크 레벨 즉시 파악",
      "컴플라이언스 보고서: 우선순위별 액션을 포함한 감사 보고서 자동 생성"],
     ["问题陈述：手动审计数千个文件夹的权限不切实际",
      "工作流触发：指定目标卷并启动审计",
      "ACL分析：自动收集ACL并检测策略违规",
      "结果审查：即时掌握违规数量和风险等级",
      "合规报告：自动生成包含优先级操作的审计报告"],
     ["問題陳述：手動稽核數千個資料夾的權限不切實際",
      "工作流程觸發：指定目標磁碟區並啟動稽核",
      "ACL分析：自動收集ACL並偵測策略違規",
      "結果審查：即時掌握違規數量和風險等級",
      "合規報告：自動產生包含優先順序操作的稽核報告"],
     ["Problématique : L'audit manuel des permissions de milliers de dossiers est irréaliste",
      "Déclenchement : Spécifier le volume cible et lancer l'audit",
      "Analyse ACL : Collecter automatiquement les ACL et détecter les violations",
      "Revue des résultats : Saisir instantanément le nombre de violations et les niveaux de risque",
      "Rapport de conformité : Générer automatiquement un rapport d'audit avec actions prioritaires"],
     ["Problemstellung: Manuelle Berechtigungsaudits für Tausende von Ordnern sind unrealistisch",
      "Workflow-Auslösung: Zielvolumen angeben und Audit starten",
      "ACL-Analyse: ACLs automatisch sammeln und Richtlinienverstöße erkennen",
      "Ergebnisüberprüfung: Sofortige Erfassung von Verstößen und Risikostufen",
      "Compliance-Bericht: Automatische Generierung eines Audit-Berichts mit priorisierten Maßnahmen"],
     ["Planteamiento: La auditoría manual de permisos de miles de carpetas es poco realista",
      "Activación: Especificar el volumen objetivo e iniciar la auditoría",
      "Análisis ACL: Recopilar automáticamente ACL y detectar violaciones de políticas",
      "Revisión de resultados: Captar instantáneamente el número de violaciones y niveles de riesgo",
      "Informe de cumplimiento: Generar automáticamente informe de auditoría con acciones priorizadas"],
     # Components
     "Step Functions, Lambda (ACL Collector), Lambda (Policy Checker), Lambda (Report Generator), Amazon Athena",
    ),
]

# This approach is too complex. Let me use a simpler template-based approach.
print("Use direct file creation instead")
