#!/usr/bin/env python3
"""Generate multilingual demo-guide files for 9 use cases in 6 languages."""
import os
from pathlib import Path

BASE_DIR = Path('/Users/yoshiki/Downloads/fsxn-s3ap-serverless-patterns')
LANGUAGES = ['ko', 'zh-CN', 'zh-TW', 'fr', 'de', 'es']

LANG_SWITCHERS = {
    'ko': '[日本語](demo-guide.md) | [English](demo-guide.en.md) | 한국어 | [简体中文](demo-guide.zh-CN.md) | [繁體中文](demo-guide.zh-TW.md) | [Français](demo-guide.fr.md) | [Deutsch](demo-guide.de.md) | [Español](demo-guide.es.md)',
    'zh-CN': '[日本語](demo-guide.md) | [English](demo-guide.en.md) | [한국어](demo-guide.ko.md) | 简体中文 | [繁體中文](demo-guide.zh-TW.md) | [Français](demo-guide.fr.md) | [Deutsch](demo-guide.de.md) | [Español](demo-guide.es.md)',
    'zh-TW': '[日本語](demo-guide.md) | [English](demo-guide.en.md) | [한국어](demo-guide.ko.md) | [简体中文](demo-guide.zh-CN.md) | 繁體中文 | [Français](demo-guide.fr.md) | [Deutsch](demo-guide.de.md) | [Español](demo-guide.es.md)',
    'fr': '[日本語](demo-guide.md) | [English](demo-guide.en.md) | [한국어](demo-guide.ko.md) | [简体中文](demo-guide.zh-CN.md) | [繁體中文](demo-guide.zh-TW.md) | Français | [Deutsch](demo-guide.de.md) | [Español](demo-guide.es.md)',
    'de': '[日本語](demo-guide.md) | [English](demo-guide.en.md) | [한국어](demo-guide.ko.md) | [简体中文](demo-guide.zh-CN.md) | [繁體中文](demo-guide.zh-TW.md) | [Français](demo-guide.fr.md) | Deutsch | [Español](demo-guide.es.md)',
    'es': '[日本語](demo-guide.md) | [English](demo-guide.en.md) | [한국어](demo-guide.ko.md) | [简体中文](demo-guide.zh-CN.md) | [繁體中文](demo-guide.zh-TW.md) | [Français](demo-guide.fr.md) | [Deutsch](demo-guide.de.md) | Español',
}

LANG_LABELS = {
    'ko': {'core': '핵심 메시지', 'duration': '예상 시간', 'footer': '*본 문서는 기술 프레젠테이션용 데모 영상 제작 가이드입니다.*'},
    'zh-CN': {'core': '核心信息', 'duration': '预计时间', 'footer': '*本文档是技术演示视频的制作指南。*'},
    'zh-TW': {'core': '核心訊息', 'duration': '預計時間', 'footer': '*本文件是技術演示影片的製作指南。*'},
    'fr': {'core': 'Message clé', 'duration': 'Durée prévue', 'footer': '*Ce document sert de guide de production pour les vidéos de démonstration technique.*'},
    'de': {'core': 'Kernbotschaft', 'duration': 'Voraussichtliche Dauer', 'footer': '*Dieses Dokument dient als Produktionsleitfaden für technische Demonstrationsvideos.*'},
    'es': {'core': 'Mensaje clave', 'duration': 'Duración prevista', 'footer': '*Este documento sirve como guía de producción para videos de demostración técnica.*'},
}

# UC definitions
USE_CASES = {
    'healthcare-dicom': {
        'titles': {
            'ko': 'DICOM 익명화 워크플로우',
            'zh-CN': 'DICOM 匿名化工作流',
            'zh-TW': 'DICOM 匿名化工作流程',
            'fr': "Workflow d'anonymisation DICOM",
            'de': 'DICOM-Anonymisierungs-Workflow',
            'es': 'Flujo de trabajo de anonimización DICOM',
        },
        'summaries': {
            'ko': '본 데모는 의료 영상(DICOM) 파일의 자동 익명화 파이프라인을 시연합니다. 환자 식별 정보를 제거하여 연구 데이터 공유를 안전하게 수행합니다.',
            'zh-CN': '本演示展示医学影像（DICOM）文件的自动匿名化流水线。通过移除患者身份信息，实现安全的研究数据共享。',
            'zh-TW': '本演示展示醫學影像（DICOM）檔案的自動匿名化流程。透過移除病患識別資訊，實現安全的研究資料共享。',
            'fr': "Cette démo présente un pipeline d'anonymisation automatique de fichiers DICOM. Les informations patient sont supprimées pour un partage sécurisé des données de recherche.",
            'de': 'Diese Demo zeigt eine automatische Anonymisierungs-Pipeline für DICOM-Dateien. Patientenidentifikationsdaten werden entfernt, um einen sicheren Forschungsdatenaustausch zu ermöglichen.',
            'es': 'Esta demo presenta un pipeline de anonimización automática de archivos DICOM. Se eliminan los datos de identificación del paciente para compartir datos de investigación de forma segura.',
        },
        'core_messages': {
            'ko': 'DICOM 파일에서 환자 정보를 자동 제거하여 규정을 준수하면서 연구 데이터를 안전하게 공유합니다.',
            'zh-CN': '自动移除 DICOM 文件中的患者信息，在合规前提下安全共享研究数据。',
            'zh-TW': '自動移除 DICOM 檔案中的病患資訊，在合規前提下安全共享研究資料。',
            'fr': 'Supprimer automatiquement les informations patient des fichiers DICOM pour un partage conforme et sécurisé.',
            'de': 'Patientendaten automatisch aus DICOM-Dateien entfernen für konformen und sicheren Datenaustausch.',
            'es': 'Eliminar automáticamente la información del paciente de archivos DICOM para un intercambio seguro y conforme.',
        },
        'workflows': {
            'ko': 'DICOM 업로드 → 메타데이터 추출 → PHI 검출 → 익명화 처리 → 검증 리포트',
            'zh-CN': 'DICOM 上传 → 元数据提取 → PHI 检测 → 匿名化处理 → 验证报告',
            'zh-TW': 'DICOM 上傳 → 中繼資料擷取 → PHI 偵測 → 匿名化處理 → 驗證報告',
            'fr': 'Upload DICOM → Extraction métadonnées → Détection PHI → Anonymisation → Rapport de validation',
            'de': 'DICOM-Upload → Metadaten-Extraktion → PHI-Erkennung → Anonymisierung → Validierungsbericht',
            'es': 'Carga DICOM → Extracción de metadatos → Detección PHI → Anonimización → Informe de validación',
        },
        'sections': {
            'ko': ['문제 제기: 연구 데이터 공유 시 환자 개인정보 보호 규정 준수가 필수', '파일 업로드: DICOM 파일 배치로 자동 처리 시작', 'PHI 검출 및 익명화: AI 기반 개인정보 검출 및 자동 마스킹 처리', '결과 확인: 익명화 완료 파일과 처리 통계 확인', '검증 리포트: 규정 준수 검증 보고서 생성 및 데이터 공유 승인'],
            'zh-CN': ['问题提出：研究数据共享时必须遵守患者隐私保护法规', '文件上传：放置 DICOM 文件即可启动自动处理', 'PHI 检测与匿名化：AI 驱动的隐私信息检测与自动脱敏', '结果确认：查看匿名化完成文件及处理统计', '验证报告：生成合规验证报告并批准数据共享'],
            'zh-TW': ['問題提出：研究資料共享時必須遵守病患隱私保護法規', '檔案上傳：放置 DICOM 檔案即可啟動自動處理', 'PHI 偵測與匿名化：AI 驅動的隱私資訊偵測與自動遮蔽', '結果確認：查看匿名化完成檔案及處理統計', '驗證報告：產生合規驗證報告並核准資料共享'],
            'fr': ['Problématique : Le partage de données de recherche exige la conformité aux réglementations', 'Upload : Placer les fichiers DICOM pour démarrer le traitement automatique', "Détection PHI et anonymisation : Détection IA des informations personnelles et masquage automatique", 'Résultats : Vérification des fichiers anonymisés et statistiques de traitement', 'Rapport de validation : Génération du rapport de conformité et approbation du partage'],
            'de': ['Problemstellung: Forschungsdatenaustausch erfordert Einhaltung der Patientenschutzvorschriften', 'Upload: DICOM-Dateien ablegen startet automatische Verarbeitung', 'PHI-Erkennung und Anonymisierung: KI-gestützte Erkennung und automatische Maskierung', 'Ergebnisse: Überprüfung anonymisierter Dateien und Verarbeitungsstatistiken', 'Validierungsbericht: Compliance-Bericht erstellen und Datenaustausch genehmigen'],
            'es': ['Problema: El intercambio de datos de investigación requiere cumplimiento normativo', 'Carga: Colocar archivos DICOM inicia el procesamiento automático', 'Detección PHI y anonimización: Detección IA de información personal y enmascaramiento automático', 'Resultados: Verificación de archivos anonimizados y estadísticas de procesamiento', 'Informe de validación: Generación de informe de cumplimiento y aprobación de intercambio'],
        },
        'tech_notes': {
            'ko': [('Step Functions', '워크플로우 오케스트레이션'), ('Lambda (DICOM Parser)', 'DICOM 메타데이터 추출'), ('Lambda (PHI Detector)', 'AI 기반 개인정보 검출'), ('Lambda (Anonymizer)', '익명화 처리 실행'), ('Amazon Athena', '처리 결과 집계 분석')],
            'zh-CN': [('Step Functions', '工作流编排'), ('Lambda (DICOM Parser)', 'DICOM 元数据提取'), ('Lambda (PHI Detector)', 'AI 驱动隐私信息检测'), ('Lambda (Anonymizer)', '匿名化处理执行'), ('Amazon Athena', '处理结果聚合分析')],
            'zh-TW': [('Step Functions', '工作流程編排'), ('Lambda (DICOM Parser)', 'DICOM 中繼資料擷取'), ('Lambda (PHI Detector)', 'AI 驅動隱私資訊偵測'), ('Lambda (Anonymizer)', '匿名化處理執行'), ('Amazon Athena', '處理結果彙總分析')],
            'fr': [('Step Functions', 'Orchestration du workflow'), ('Lambda (DICOM Parser)', 'Extraction métadonnées DICOM'), ('Lambda (PHI Detector)', "Détection IA des informations personnelles"), ('Lambda (Anonymizer)', "Exécution de l'anonymisation"), ('Amazon Athena', 'Analyse agrégée des résultats')],
            'de': [('Step Functions', 'Workflow-Orchestrierung'), ('Lambda (DICOM Parser)', 'DICOM-Metadaten-Extraktion'), ('Lambda (PHI Detector)', 'KI-gestützte Erkennung personenbezogener Daten'), ('Lambda (Anonymizer)', 'Anonymisierungsverarbeitung'), ('Amazon Athena', 'Aggregierte Ergebnisanalyse')],
            'es': [('Step Functions', 'Orquestación del flujo de trabajo'), ('Lambda (DICOM Parser)', 'Extracción de metadatos DICOM'), ('Lambda (PHI Detector)', 'Detección IA de información personal'), ('Lambda (Anonymizer)', 'Ejecución de anonimización'), ('Amazon Athena', 'Análisis agregado de resultados')],
        },
    },
    'autonomous-driving': {
        'titles': {
            'ko': '자율주행 데이터 전처리 파이프라인',
            'zh-CN': '自动驾驶数据预处理流水线',
            'zh-TW': '自動駕駛資料前處理流程',
            'fr': 'Pipeline de prétraitement des données de conduite autonome',
            'de': 'Datenvorverarbeitungs-Pipeline für autonomes Fahren',
            'es': 'Pipeline de preprocesamiento de datos de conducción autónoma',
        },
        'summaries': {
            'ko': '본 데모는 자율주행 센서 데이터의 전처리 및 어노테이션 파이프라인을 시연합니다. 대용량 주행 데이터를 자동으로 분류하고 학습용 데이터셋을 생성합니다.',
            'zh-CN': '本演示展示自动驾驶传感器数据的预处理与标注流水线。自动分类大规模驾驶数据并生成训练数据集。',
            'zh-TW': '本演示展示自動駕駛感測器資料的前處理與標註流程。自動分類大規模駕駛資料並產生訓練資料集。',
            'fr': "Cette démo présente un pipeline de prétraitement et d'annotation pour les données de capteurs de conduite autonome. Les données sont automatiquement classifiées pour générer des jeux de données d'entraînement.",
            'de': 'Diese Demo zeigt eine Vorverarbeitungs- und Annotations-Pipeline für autonome Fahrsensordaten. Große Fahrdatenmengen werden automatisch klassifiziert und Trainingsdatensätze erstellt.',
            'es': 'Esta demo presenta un pipeline de preprocesamiento y anotación para datos de sensores de conducción autónoma. Los datos se clasifican automáticamente para generar conjuntos de datos de entrenamiento.',
        },
        'core_messages': {
            'ko': '대용량 주행 센서 데이터를 자동 전처리하여 AI 학습에 즉시 활용 가능한 어노테이션 데이터셋을 생성합니다.',
            'zh-CN': '自动预处理大规模驾驶传感器数据，生成可直接用于 AI 训练的标注数据集。',
            'zh-TW': '自動前處理大規模駕駛感測器資料，產生可直接用於 AI 訓練的標註資料集。',
            'fr': "Prétraiter automatiquement les données de capteurs pour générer des jeux de données annotés prêts pour l'entraînement IA.",
            'de': 'Sensordaten automatisch vorverarbeiten und annotierte Datensätze für KI-Training erstellen.',
            'es': 'Preprocesar automáticamente datos de sensores para generar conjuntos de datos anotados listos para entrenamiento IA.',
        },
        'workflows': {
            'ko': '센서 데이터 수집 → 포맷 변환 → 프레임 분류 → 어노테이션 생성 → 데이터셋 리포트',
            'zh-CN': '传感器数据采集 → 格式转换 → 帧分类 → 标注生成 → 数据集报告',
            'zh-TW': '感測器資料收集 → 格式轉換 → 影格分類 → 標註產生 → 資料集報告',
            'fr': 'Collecte capteurs → Conversion format → Classification frames → Génération annotations → Rapport dataset',
            'de': 'Sensordatenerfassung → Formatkonvertierung → Frame-Klassifikation → Annotation-Generierung → Dataset-Bericht',
            'es': 'Recopilación sensores → Conversión formato → Clasificación frames → Generación anotaciones → Informe dataset',
        },
        'sections': {
            'ko': ['문제 제기: 대용량 주행 데이터의 수동 전처리는 병목 구간', '데이터 업로드: 센서 로그 파일 배치로 파이프라인 시작', '전처리 및 분류: 자동 포맷 변환과 AI 기반 프레임 분류', '어노테이션 결과: 생성된 라벨 데이터와 품질 통계 확인', '데이터셋 리포트: 학습 준비 완료 보고서 및 품질 메트릭'],
            'zh-CN': ['问题提出：大规模驾驶数据的手动预处理是瓶颈', '数据上传：放置传感器日志文件启动流水线', '预处理与分类：自动格式转换和 AI 驱动帧分类', '标注结果：查看生成的标签数据和质量统计', '数据集报告：训练就绪报告及质量指标'],
            'zh-TW': ['問題提出：大規模駕駛資料的手動前處理是瓶頸', '資料上傳：放置感測器日誌檔案啟動流程', '前處理與分類：自動格式轉換和 AI 驅動影格分類', '標註結果：查看產生的標籤資料和品質統計', '資料集報告：訓練就緒報告及品質指標'],
            'fr': ['Problématique : Le prétraitement manuel des données massives est un goulot', 'Upload : Placer les fichiers de logs capteurs pour démarrer le pipeline', "Prétraitement et classification : Conversion automatique et classification IA des frames", 'Résultats annotation : Vérification des labels générés et statistiques qualité', "Rapport dataset : Rapport de préparation à l'entraînement et métriques qualité"],
            'de': ['Problemstellung: Manuelle Vorverarbeitung großer Fahrdaten ist ein Engpass', 'Upload: Sensor-Logdateien ablegen startet die Pipeline', 'Vorverarbeitung und Klassifikation: Automatische Formatkonvertierung und KI-Frame-Klassifikation', 'Annotationsergebnisse: Überprüfung generierter Labels und Qualitätsstatistiken', 'Dataset-Bericht: Trainingsbereitschaftsbericht und Qualitätsmetriken'],
            'es': ['Problema: El preprocesamiento manual de datos masivos es un cuello de botella', 'Carga: Colocar archivos de logs de sensores inicia el pipeline', 'Preprocesamiento y clasificación: Conversión automática y clasificación IA de frames', 'Resultados de anotación: Verificación de etiquetas generadas y estadísticas de calidad', 'Informe dataset: Informe de preparación para entrenamiento y métricas de calidad'],
        },
        'tech_notes': {
            'ko': [('Step Functions', '워크플로우 오케스트레이션'), ('Lambda (Format Converter)', '센서 데이터 포맷 변환'), ('Lambda (Frame Classifier)', 'AI 기반 프레임 분류'), ('Lambda (Annotation Generator)', '어노테이션 자동 생성'), ('Amazon Athena', '데이터셋 통계 분석')],
            'zh-CN': [('Step Functions', '工作流编排'), ('Lambda (Format Converter)', '传感器数据格式转换'), ('Lambda (Frame Classifier)', 'AI 驱动帧分类'), ('Lambda (Annotation Generator)', '标注自动生成'), ('Amazon Athena', '数据集统计分析')],
            'zh-TW': [('Step Functions', '工作流程編排'), ('Lambda (Format Converter)', '感測器資料格式轉換'), ('Lambda (Frame Classifier)', 'AI 驅動影格分類'), ('Lambda (Annotation Generator)', '標註自動產生'), ('Amazon Athena', '資料集統計分析')],
            'fr': [('Step Functions', 'Orchestration du workflow'), ('Lambda (Format Converter)', 'Conversion format données capteurs'), ('Lambda (Frame Classifier)', 'Classification IA des frames'), ('Lambda (Annotation Generator)', "Génération automatique d'annotations"), ('Amazon Athena', 'Analyse statistique du dataset')],
            'de': [('Step Functions', 'Workflow-Orchestrierung'), ('Lambda (Format Converter)', 'Sensordaten-Formatkonvertierung'), ('Lambda (Frame Classifier)', 'KI-gestützte Frame-Klassifikation'), ('Lambda (Annotation Generator)', 'Automatische Annotation-Generierung'), ('Amazon Athena', 'Dataset-Statistikanalyse')],
            'es': [('Step Functions', 'Orquestación del flujo de trabajo'), ('Lambda (Format Converter)', 'Conversión de formato de datos de sensores'), ('Lambda (Frame Classifier)', 'Clasificación IA de frames'), ('Lambda (Annotation Generator)', 'Generación automática de anotaciones'), ('Amazon Athena', 'Análisis estadístico del dataset')],
        },
    },
    'construction-bim': {
        'titles': {
            'ko': 'BIM 모델 변경 감지 및 안전 준수 검사',
            'zh-CN': 'BIM 模型变更检测与安全合规检查',
            'zh-TW': 'BIM 模型變更偵測與安全合規檢查',
            'fr': 'Détection de changements BIM et vérification de conformité sécurité',
            'de': 'BIM-Modelländerungserkennung und Sicherheits-Compliance-Prüfung',
            'es': 'Detección de cambios BIM y verificación de cumplimiento de seguridad',
        },
        'summaries': {
            'ko': '본 데모는 BIM 모델의 변경 감지 및 안전 규정 준수 자동 검사 파이프라인을 시연합니다. 설계 변경 시 안전 기준 위반을 자동으로 검출합니다.',
            'zh-CN': '本演示展示 BIM 模型变更检测与安全合规自动检查流水线。设计变更时自动检测安全标准违规。',
            'zh-TW': '本演示展示 BIM 模型變更偵測與安全合規自動檢查流程。設計變更時自動偵測安全標準違規。',
            'fr': "Cette démo présente un pipeline de détection de changements BIM et de vérification automatique de conformité sécurité. Les violations sont détectées automatiquement lors des modifications.",
            'de': 'Diese Demo zeigt eine Pipeline zur BIM-Änderungserkennung und automatischen Sicherheits-Compliance-Prüfung. Verstöße werden bei Designänderungen automatisch erkannt.',
            'es': 'Esta demo presenta un pipeline de detección de cambios BIM y verificación automática de cumplimiento de seguridad. Las violaciones se detectan automáticamente durante las modificaciones.',
        },
        'core_messages': {
            'ko': 'BIM 모델 변경 시 안전 규정 위반을 자동 검출하여 설계 단계에서 리스크를 사전에 제거합니다.',
            'zh-CN': 'BIM 模型变更时自动检测安全违规，在设计阶段提前消除风险。',
            'zh-TW': 'BIM 模型變更時自動偵測安全違規，在設計階段提前消除風險。',
            'fr': "Détecter automatiquement les violations de sécurité lors des modifications BIM pour éliminer les risques dès la conception.",
            'de': 'Sicherheitsverstöße bei BIM-Änderungen automatisch erkennen und Risiken bereits in der Entwurfsphase eliminieren.',
            'es': 'Detectar automáticamente violaciones de seguridad en cambios BIM para eliminar riesgos desde la fase de diseño.',
        },
        'workflows': {
            'ko': 'BIM 파일 업로드 → 변경 감지 → 안전 규정 매칭 → 위반 검출 → 준수 리포트',
            'zh-CN': 'BIM 文件上传 → 变更检测 → 安全规范匹配 → 违规检出 → 合规报告',
            'zh-TW': 'BIM 檔案上傳 → 變更偵測 → 安全規範比對 → 違規檢出 → 合規報告',
            'fr': 'Upload BIM → Détection changements → Matching réglementaire → Détection violations → Rapport conformité',
            'de': 'BIM-Upload → Änderungserkennung → Vorschriftenabgleich → Verstoßerkennung → Compliance-Bericht',
            'es': 'Carga BIM → Detección cambios → Matching normativo → Detección violaciones → Informe cumplimiento',
        },
        'sections': {
            'ko': ['문제 제기: 설계 변경마다 수동 안전 검토는 비효율적', 'BIM 업로드: 변경된 모델 파일 배치로 검사 시작', '변경 감지 및 규정 매칭: 자동 diff 분석과 안전 기준 대조', '위반 사항 확인: 검출된 안전 규정 위반 목록과 심각도', '준수 리포트: 시정 조치 권고 포함 종합 보고서 생성'],
            'zh-CN': ['问题提出：每次设计变更都手动安全审查效率低下', 'BIM 上传：放置变更模型文件启动检查', '变更检测与规范匹配：自动 diff 分析和安全标准对照', '违规确认：检出的安全违规列表及严重程度', '合规报告：包含整改建议的综合报告生成'],
            'zh-TW': ['問題提出：每次設計變更都手動安全審查效率低下', 'BIM 上傳：放置變更模型檔案啟動檢查', '變更偵測與規範比對：自動 diff 分析和安全標準對照', '違規確認：檢出的安全違規清單及嚴重程度', '合規報告：包含改善建議的綜合報告產生'],
            'fr': ['Problématique : La revue manuelle de sécurité à chaque modification est inefficace', 'Upload BIM : Placer les fichiers modifiés pour démarrer la vérification', 'Détection et matching : Analyse diff automatique et comparaison aux normes de sécurité', 'Violations détectées : Liste des non-conformités et niveaux de gravité', 'Rapport conformité : Génération du rapport avec recommandations correctives'],
            'de': ['Problemstellung: Manuelle Sicherheitsprüfung bei jeder Änderung ist ineffizient', 'BIM-Upload: Geänderte Modelldateien ablegen startet die Prüfung', 'Erkennung und Abgleich: Automatische Diff-Analyse und Sicherheitsstandard-Vergleich', 'Erkannte Verstöße: Liste der Sicherheitsverstöße und Schweregrade', 'Compliance-Bericht: Erstellung des Berichts mit Korrekturempfehlungen'],
            'es': ['Problema: La revisión manual de seguridad en cada cambio es ineficiente', 'Carga BIM: Colocar archivos de modelo modificados inicia la verificación', 'Detección y matching: Análisis diff automático y comparación con normas de seguridad', 'Violaciones detectadas: Lista de incumplimientos y niveles de gravedad', 'Informe cumplimiento: Generación del informe con recomendaciones correctivas'],
        },
        'tech_notes': {
            'ko': [('Step Functions', '워크플로우 오케스트레이션'), ('Lambda (Change Detector)', 'BIM 모델 변경 감지'), ('Lambda (Rule Matcher)', '안전 규정 매칭 엔진'), ('Lambda (Report Generator)', '준수 리포트 생성'), ('Amazon Athena', '위반 이력 집계 분석')],
            'zh-CN': [('Step Functions', '工作流编排'), ('Lambda (Change Detector)', 'BIM 模型变更检测'), ('Lambda (Rule Matcher)', '安全规范匹配引擎'), ('Lambda (Report Generator)', '合规报告生成'), ('Amazon Athena', '违规历史聚合分析')],
            'zh-TW': [('Step Functions', '工作流程編排'), ('Lambda (Change Detector)', 'BIM 模型變更偵測'), ('Lambda (Rule Matcher)', '安全規範比對引擎'), ('Lambda (Report Generator)', '合規報告產生'), ('Amazon Athena', '違規歷史彙總分析')],
            'fr': [('Step Functions', 'Orchestration du workflow'), ('Lambda (Change Detector)', 'Détection changements BIM'), ('Lambda (Rule Matcher)', 'Moteur de matching réglementaire'), ('Lambda (Report Generator)', 'Génération rapport conformité'), ('Amazon Athena', "Analyse agrégée de l'historique des violations")],
            'de': [('Step Functions', 'Workflow-Orchestrierung'), ('Lambda (Change Detector)', 'BIM-Änderungserkennung'), ('Lambda (Rule Matcher)', 'Vorschriften-Matching-Engine'), ('Lambda (Report Generator)', 'Compliance-Berichterstellung'), ('Amazon Athena', 'Aggregierte Verstoßhistorie-Analyse')],
            'es': [('Step Functions', 'Orquestación del flujo de trabajo'), ('Lambda (Change Detector)', 'Detección de cambios BIM'), ('Lambda (Rule Matcher)', 'Motor de matching normativo'), ('Lambda (Report Generator)', 'Generación de informe de cumplimiento'), ('Amazon Athena', 'Análisis agregado del historial de violaciones')],
        },
    },
    'education-research': {
        'titles': {
            'ko': '논문 분류 및 인용 네트워크 분석',
            'zh-CN': '论文分类与引用网络分析',
            'zh-TW': '論文分類與引用網路分析',
            'fr': 'Classification de publications et analyse de réseau de citations',
            'de': 'Publikationsklassifikation und Zitationsnetzwerk-Analyse',
            'es': 'Clasificación de publicaciones y análisis de red de citas',
        },
        'summaries': {
            'ko': '본 데모는 학술 논문의 자동 분류 및 인용 네트워크 분석 파이프라인을 시연합니다. 대량의 논문을 주제별로 분류하고 인용 관계를 시각화합니다.',
            'zh-CN': '本演示展示学术论文的自动分类与引用网络分析流水线。对大量论文按主题分类并可视化引用关系。',
            'zh-TW': '本演示展示學術論文的自動分類與引用網路分析流程。對大量論文按主題分類並視覺化引用關係。',
            'fr': "Cette démo présente un pipeline de classification automatique de publications et d'analyse de réseau de citations. Les publications sont classifiées par thème et les relations de citation visualisées.",
            'de': 'Diese Demo zeigt eine Pipeline zur automatischen Klassifikation von Publikationen und Zitationsnetzwerk-Analyse. Publikationen werden thematisch klassifiziert und Zitationsbeziehungen visualisiert.',
            'es': 'Esta demo presenta un pipeline de clasificación automática de publicaciones y análisis de red de citas. Las publicaciones se clasifican por tema y se visualizan las relaciones de citación.',
        },
        'core_messages': {
            'ko': '대량의 학술 논문을 AI로 자동 분류하고 인용 네트워크를 분석하여 연구 동향을 즉시 파악합니다.',
            'zh-CN': '通过 AI 自动分类大量学术论文并分析引用网络，即时掌握研究趋势。',
            'zh-TW': '透過 AI 自動分類大量學術論文並分析引用網路，即時掌握研究趨勢。',
            'fr': "Classifier automatiquement les publications par IA et analyser le réseau de citations pour identifier instantanément les tendances de recherche.",
            'de': 'Publikationen automatisch per KI klassifizieren und Zitationsnetzwerke analysieren, um Forschungstrends sofort zu erkennen.',
            'es': 'Clasificar automáticamente publicaciones con IA y analizar la red de citas para identificar tendencias de investigación al instante.',
        },
        'workflows': {
            'ko': '논문 업로드 → 메타데이터 추출 → AI 주제 분류 → 인용 네트워크 구축 → 분석 리포트',
            'zh-CN': '论文上传 → 元数据提取 → AI 主题分类 → 引用网络构建 → 分析报告',
            'zh-TW': '論文上傳 → 中繼資料擷取 → AI 主題分類 → 引用網路建構 → 分析報告',
            'fr': 'Upload publications → Extraction métadonnées → Classification IA → Construction réseau citations → Rapport analyse',
            'de': 'Publikations-Upload → Metadaten-Extraktion → KI-Klassifikation → Zitationsnetzwerk-Aufbau → Analysebericht',
            'es': 'Carga publicaciones → Extracción metadatos → Clasificación IA → Construcción red citas → Informe análisis',
        },
        'sections': {
            'ko': ['문제 제기: 수천 편의 논문을 수동으로 분류하고 관계를 파악하는 것은 비현실적', '논문 업로드: PDF 파일 배치로 분석 파이프라인 시작', 'AI 분류 및 네트워크 구축: 주제 자동 분류와 인용 관계 추출', '분석 결과: 주제별 클러스터와 핵심 논문 식별', '연구 동향 리포트: 분야별 트렌드 분석 및 추천 논문 목록'],
            'zh-CN': ['问题提出：手动分类数千篇论文并理清关系不现实', '论文上传：放置 PDF 文件启动分析流水线', 'AI 分类与网络构建：主题自动分类和引用关系提取', '分析结果：主题聚类和核心论文识别', '研究趋势报告：领域趋势分析及推荐论文列表'],
            'zh-TW': ['問題提出：手動分類數千篇論文並釐清關係不切實際', '論文上傳：放置 PDF 檔案啟動分析流程', 'AI 分類與網路建構：主題自動分類和引用關係擷取', '分析結果：主題聚類和核心論文識別', '研究趨勢報告：領域趨勢分析及推薦論文清單'],
            'fr': ['Problématique : Classifier manuellement des milliers de publications est irréaliste', 'Upload : Placer les fichiers PDF pour démarrer le pipeline', 'Classification IA et construction réseau : Classification thématique et extraction des citations', 'Résultats : Clusters thématiques et identification des publications clés', 'Rapport tendances : Analyse des tendances par domaine et liste de publications recommandées'],
            'de': ['Problemstellung: Tausende Publikationen manuell zu klassifizieren ist unrealistisch', 'Upload: PDF-Dateien ablegen startet die Analyse-Pipeline', 'KI-Klassifikation und Netzwerkaufbau: Thematische Klassifikation und Zitationsextraktion', 'Ergebnisse: Thematische Cluster und Identifikation von Schlüsselpublikationen', 'Trendbericht: Trendanalyse nach Fachgebiet und empfohlene Publikationsliste'],
            'es': ['Problema: Clasificar manualmente miles de publicaciones es poco realista', 'Carga: Colocar archivos PDF inicia el pipeline de análisis', 'Clasificación IA y construcción de red: Clasificación temática y extracción de citas', 'Resultados: Clusters temáticos e identificación de publicaciones clave', 'Informe de tendencias: Análisis de tendencias por área y lista de publicaciones recomendadas'],
        },
        'tech_notes': {
            'ko': [('Step Functions', '워크플로우 오케스트레이션'), ('Lambda (PDF Parser)', '논문 메타데이터 추출'), ('Lambda (Topic Classifier)', 'AI 기반 주제 분류'), ('Lambda (Citation Analyzer)', '인용 네트워크 구축'), ('Amazon Athena', '연구 동향 집계 분석')],
            'zh-CN': [('Step Functions', '工作流编排'), ('Lambda (PDF Parser)', '论文元数据提取'), ('Lambda (Topic Classifier)', 'AI 驱动主题分类'), ('Lambda (Citation Analyzer)', '引用网络构建'), ('Amazon Athena', '研究趋势聚合分析')],
            'zh-TW': [('Step Functions', '工作流程編排'), ('Lambda (PDF Parser)', '論文中繼資料擷取'), ('Lambda (Topic Classifier)', 'AI 驅動主題分類'), ('Lambda (Citation Analyzer)', '引用網路建構'), ('Amazon Athena', '研究趨勢彙總分析')],
            'fr': [('Step Functions', 'Orchestration du workflow'), ('Lambda (PDF Parser)', 'Extraction métadonnées publications'), ('Lambda (Topic Classifier)', 'Classification IA thématique'), ('Lambda (Citation Analyzer)', 'Construction réseau de citations'), ('Amazon Athena', 'Analyse agrégée des tendances')],
            'de': [('Step Functions', 'Workflow-Orchestrierung'), ('Lambda (PDF Parser)', 'Publikations-Metadaten-Extraktion'), ('Lambda (Topic Classifier)', 'KI-gestützte thematische Klassifikation'), ('Lambda (Citation Analyzer)', 'Zitationsnetzwerk-Aufbau'), ('Amazon Athena', 'Aggregierte Trendanalyse')],
            'es': [('Step Functions', 'Orquestación del flujo de trabajo'), ('Lambda (PDF Parser)', 'Extracción de metadatos de publicaciones'), ('Lambda (Topic Classifier)', 'Clasificación IA temática'), ('Lambda (Citation Analyzer)', 'Construcción de red de citas'), ('Amazon Athena', 'Análisis agregado de tendencias')],
        },
    },
    'energy-seismic': {
        'titles': {
            'ko': '검층 이상 감지 및 규정 준수 보고',
            'zh-CN': '测井异常检测与合规报告',
            'zh-TW': '測井異常偵測與合規報告',
            'fr': "Détection d'anomalies de diagraphie et rapport de conformité",
            'de': 'Bohrloch-Anomalieerkennung und Compliance-Berichterstattung',
            'es': 'Detección de anomalías de registro de pozo y reporte de cumplimiento',
        },
        'summaries': {
            'ko': '본 데모는 검층(Well Log) 데이터의 이상 감지 및 규정 준수 보고 파이프라인을 시연합니다. 센서 데이터에서 이상 패턴을 자동 검출하고 규정 보고서를 생성합니다.',
            'zh-CN': '本演示展示测井数据的异常检测与合规报告流水线。从传感器数据中自动检测异常模式并生成合规报告。',
            'zh-TW': '本演示展示測井資料的異常偵測與合規報告流程。從感測器資料中自動偵測異常模式並產生合規報告。',
            'fr': "Cette démo présente un pipeline de détection d'anomalies dans les données de diagraphie et de génération de rapports de conformité.",
            'de': 'Diese Demo zeigt eine Pipeline zur Anomalieerkennung in Bohrlochdaten und automatischen Compliance-Berichterstellung.',
            'es': 'Esta demo presenta un pipeline de detección de anomalías en datos de registro de pozo y generación de reportes de cumplimiento.',
        },
        'core_messages': {
            'ko': '검층 데이터에서 이상 패턴을 자동 감지하여 규정 준수 보고서를 즉시 생성합니다.',
            'zh-CN': '自动检测测井数据中的异常模式，即时生成合规报告。',
            'zh-TW': '自動偵測測井資料中的異常模式，即時產生合規報告。',
            'fr': "Détecter automatiquement les anomalies dans les données de diagraphie et générer instantanément les rapports de conformité.",
            'de': 'Anomalien in Bohrlochdaten automatisch erkennen und Compliance-Berichte sofort erstellen.',
            'es': 'Detectar automáticamente anomalías en datos de registro de pozo y generar reportes de cumplimiento al instante.',
        },
        'workflows': {
            'ko': '검층 데이터 수집 → 신호 전처리 → 이상 감지 → 규정 매칭 → 준수 리포트',
            'zh-CN': '测井数据采集 → 信号预处理 → 异常检测 → 法规匹配 → 合规报告',
            'zh-TW': '測井資料收集 → 訊號前處理 → 異常偵測 → 法規比對 → 合規報告',
            'fr': 'Collecte diagraphie → Prétraitement signal → Détection anomalies → Matching réglementaire → Rapport conformité',
            'de': 'Bohrlochdaten-Erfassung → Signalvorverarbeitung → Anomalieerkennung → Vorschriftenabgleich → Compliance-Bericht',
            'es': 'Recopilación datos pozo → Preprocesamiento señal → Detección anomalías → Matching normativo → Reporte cumplimiento',
        },
        'sections': {
            'ko': ['문제 제기: 대량의 검층 데이터에서 이상을 수동으로 찾는 것은 비효율적', '데이터 업로드: 검층 로그 파일 배치로 분석 시작', '이상 감지: AI 기반 패턴 분석으로 이상 구간 자동 검출', '결과 확인: 검출된 이상 목록과 심각도 분류', '규정 준수 리포트: 규정 기준 대조 결과 및 시정 조치 권고'],
            'zh-CN': ['问题提出：从大量测井数据中手动查找异常效率低下', '数据上传：放置测井日志文件启动分析', '异常检测：AI 驱动模式分析自动检出异常区间', '结果确认：检出的异常列表及严重程度分类', '合规报告：法规标准对照结果及整改建议'],
            'zh-TW': ['問題提出：從大量測井資料中手動查找異常效率低下', '資料上傳：放置測井日誌檔案啟動分析', '異常偵測：AI 驅動模式分析自動檢出異常區間', '結果確認：檢出的異常清單及嚴重程度分類', '合規報告：法規標準對照結果及改善建議'],
            'fr': ["Problématique : Rechercher manuellement des anomalies dans de grandes quantités de données est inefficace", 'Upload : Placer les fichiers de diagraphie pour démarrer', "Détection : Analyse IA des patterns pour détecter automatiquement les anomalies", 'Résultats : Liste des anomalies détectées et classification par gravité', 'Rapport conformité : Résultats de comparaison réglementaire et recommandations'],
            'de': ['Problemstellung: Manuelle Anomaliesuche in großen Datenmengen ist ineffizient', 'Upload: Bohrloch-Logdateien ablegen startet die Analyse', 'Erkennung: KI-gestützte Musteranalyse erkennt Anomalien automatisch', 'Ergebnisse: Liste erkannter Anomalien und Schweregradklassifikation', 'Compliance-Bericht: Vorschriftenvergleich und Korrekturempfehlungen'],
            'es': ['Problema: Buscar anomalías manualmente en grandes volúmenes de datos es ineficiente', 'Carga: Colocar archivos de registro de pozo inicia el análisis', 'Detección: Análisis IA de patrones detecta anomalías automáticamente', 'Resultados: Lista de anomalías detectadas y clasificación por gravedad', 'Reporte cumplimiento: Resultados de comparación normativa y recomendaciones'],
        },
        'tech_notes': {
            'ko': [('Step Functions', '워크플로우 오케스트레이션'), ('Lambda (Signal Processor)', '검층 신호 전처리'), ('Lambda (Anomaly Detector)', 'AI 기반 이상 감지'), ('Lambda (Compliance Checker)', '규정 기준 대조'), ('Amazon Athena', '이상 이력 집계 분석')],
            'zh-CN': [('Step Functions', '工作流编排'), ('Lambda (Signal Processor)', '测井信号预处理'), ('Lambda (Anomaly Detector)', 'AI 驱动异常检测'), ('Lambda (Compliance Checker)', '法规标准对照'), ('Amazon Athena', '异常历史聚合分析')],
            'zh-TW': [('Step Functions', '工作流程編排'), ('Lambda (Signal Processor)', '測井訊號前處理'), ('Lambda (Anomaly Detector)', 'AI 驅動異常偵測'), ('Lambda (Compliance Checker)', '法規標準對照'), ('Amazon Athena', '異常歷史彙總分析')],
            'fr': [('Step Functions', 'Orchestration du workflow'), ('Lambda (Signal Processor)', 'Prétraitement signal diagraphie'), ('Lambda (Anomaly Detector)', "Détection IA d'anomalies"), ('Lambda (Compliance Checker)', 'Vérification conformité réglementaire'), ('Amazon Athena', "Analyse agrégée de l'historique des anomalies")],
            'de': [('Step Functions', 'Workflow-Orchestrierung'), ('Lambda (Signal Processor)', 'Bohrloch-Signalvorverarbeitung'), ('Lambda (Anomaly Detector)', 'KI-gestützte Anomalieerkennung'), ('Lambda (Compliance Checker)', 'Vorschriften-Compliance-Prüfung'), ('Amazon Athena', 'Aggregierte Anomaliehistorie-Analyse')],
            'es': [('Step Functions', 'Orquestación del flujo de trabajo'), ('Lambda (Signal Processor)', 'Preprocesamiento de señal de pozo'), ('Lambda (Anomaly Detector)', 'Detección IA de anomalías'), ('Lambda (Compliance Checker)', 'Verificación de cumplimiento normativo'), ('Amazon Athena', 'Análisis agregado del historial de anomalías')],
        },
    },
    'genomics-pipeline': {
        'titles': {
            'ko': '시퀀싱 QC 및 변이 집계',
            'zh-CN': '测序 QC 与变异聚合',
            'zh-TW': '定序 QC 與變異彙總',
            'fr': 'QC de séquençage et agrégation de variants',
            'de': 'Sequenzierungs-QC und Varianten-Aggregation',
            'es': 'QC de secuenciación y agregación de variantes',
        },
        'summaries': {
            'ko': '본 데모는 유전체 시퀀싱 데이터의 품질 관리(QC) 및 변이 집계 파이프라인을 시연합니다. 대량의 시퀀싱 결과를 자동으로 검증하고 변이 통계를 생성합니다.',
            'zh-CN': '本演示展示基因组测序数据的质量控制（QC）与变异聚合流水线。自动验证大量测序结果并生成变异统计。',
            'zh-TW': '本演示展示基因體定序資料的品質管控（QC）與變異彙總流程。自動驗證大量定序結果並產生變異統計。',
            'fr': "Cette démo présente un pipeline de contrôle qualité (QC) et d'agrégation de variants pour les données de séquençage génomique.",
            'de': 'Diese Demo zeigt eine Pipeline zur Qualitätskontrolle (QC) und Varianten-Aggregation für Genomsequenzierungsdaten.',
            'es': 'Esta demo presenta un pipeline de control de calidad (QC) y agregación de variantes para datos de secuenciación genómica.',
        },
        'core_messages': {
            'ko': '시퀀싱 데이터의 품질을 자동 검증하고 변이를 집계하여 연구자가 분석에 집중할 수 있게 합니다.',
            'zh-CN': '自动验证测序数据质量并聚合变异，让研究人员专注于分析。',
            'zh-TW': '自動驗證定序資料品質並彙總變異，讓研究人員專注於分析。',
            'fr': "Valider automatiquement la qualité des données de séquençage et agréger les variants pour que les chercheurs se concentrent sur l'analyse.",
            'de': 'Sequenzierungsdatenqualität automatisch validieren und Varianten aggregieren, damit Forscher sich auf die Analyse konzentrieren können.',
            'es': 'Validar automáticamente la calidad de datos de secuenciación y agregar variantes para que los investigadores se concentren en el análisis.',
        },
        'workflows': {
            'ko': 'FASTQ 업로드 → QC 검증 → 변이 호출 → 통계 집계 → QC 리포트',
            'zh-CN': 'FASTQ 上传 → QC 验证 → 变异调用 → 统计聚合 → QC 报告',
            'zh-TW': 'FASTQ 上傳 → QC 驗證 → 變異呼叫 → 統計彙總 → QC 報告',
            'fr': 'Upload FASTQ → Validation QC → Appel variants → Agrégation statistique → Rapport QC',
            'de': 'FASTQ-Upload → QC-Validierung → Varianten-Calling → Statistische Aggregation → QC-Bericht',
            'es': 'Carga FASTQ → Validación QC → Llamada variantes → Agregación estadística → Reporte QC',
        },
        'sections': {
            'ko': ['문제 제기: 대량 시퀀싱 데이터의 수동 QC는 시간 소모적', '데이터 업로드: FASTQ 파일 배치로 파이프라인 시작', 'QC 및 변이 분석: 자동 품질 검증과 변이 호출 실행', '결과 확인: QC 메트릭과 변이 통계 확인', 'QC 리포트: 종합 품질 보고서 및 후속 분석 권고'],
            'zh-CN': ['问题提出：大量测序数据的手动 QC 耗时费力', '数据上传：放置 FASTQ 文件启动流水线', 'QC 与变异分析：自动质量验证和变异调用执行', '结果确认：查看 QC 指标和变异统计', 'QC 报告：综合质量报告及后续分析建议'],
            'zh-TW': ['問題提出：大量定序資料的手動 QC 耗時費力', '資料上傳：放置 FASTQ 檔案啟動流程', 'QC 與變異分析：自動品質驗證和變異呼叫執行', '結果確認：查看 QC 指標和變異統計', 'QC 報告：綜合品質報告及後續分析建議'],
            'fr': ['Problématique : Le QC manuel de grandes quantités de données de séquençage est chronophage', 'Upload : Placer les fichiers FASTQ pour démarrer le pipeline', 'QC et analyse variants : Validation qualité automatique et appel de variants', 'Résultats : Métriques QC et statistiques de variants', 'Rapport QC : Rapport qualité complet et recommandations pour analyses ultérieures'],
            'de': ['Problemstellung: Manuelle QC großer Sequenzierungsdaten ist zeitaufwändig', 'Upload: FASTQ-Dateien ablegen startet die Pipeline', 'QC und Variantenanalyse: Automatische Qualitätsvalidierung und Varianten-Calling', 'Ergebnisse: QC-Metriken und Variantenstatistiken', 'QC-Bericht: Umfassender Qualitätsbericht und Empfehlungen für Folgeanalysen'],
            'es': ['Problema: El QC manual de grandes volúmenes de datos de secuenciación consume mucho tiempo', 'Carga: Colocar archivos FASTQ inicia el pipeline', 'QC y análisis de variantes: Validación automática de calidad y llamada de variantes', 'Resultados: Métricas QC y estadísticas de variantes', 'Reporte QC: Informe de calidad completo y recomendaciones para análisis posteriores'],
        },
        'tech_notes': {
            'ko': [('Step Functions', '워크플로우 오케스트레이션'), ('Lambda (QC Validator)', '시퀀싱 품질 검증'), ('Lambda (Variant Caller)', '변이 호출 실행'), ('Lambda (Stats Aggregator)', '변이 통계 집계'), ('Amazon Athena', 'QC 메트릭 분석')],
            'zh-CN': [('Step Functions', '工作流编排'), ('Lambda (QC Validator)', '测序质量验证'), ('Lambda (Variant Caller)', '变异调用执行'), ('Lambda (Stats Aggregator)', '变异统计聚合'), ('Amazon Athena', 'QC 指标分析')],
            'zh-TW': [('Step Functions', '工作流程編排'), ('Lambda (QC Validator)', '定序品質驗證'), ('Lambda (Variant Caller)', '變異呼叫執行'), ('Lambda (Stats Aggregator)', '變異統計彙總'), ('Amazon Athena', 'QC 指標分析')],
            'fr': [('Step Functions', 'Orchestration du workflow'), ('Lambda (QC Validator)', 'Validation qualité séquençage'), ('Lambda (Variant Caller)', 'Appel de variants'), ('Lambda (Stats Aggregator)', 'Agrégation statistiques variants'), ('Amazon Athena', 'Analyse métriques QC')],
            'de': [('Step Functions', 'Workflow-Orchestrierung'), ('Lambda (QC Validator)', 'Sequenzierungs-Qualitätsvalidierung'), ('Lambda (Variant Caller)', 'Varianten-Calling'), ('Lambda (Stats Aggregator)', 'Variantenstatistik-Aggregation'), ('Amazon Athena', 'QC-Metrik-Analyse')],
            'es': [('Step Functions', 'Orquestación del flujo de trabajo'), ('Lambda (QC Validator)', 'Validación de calidad de secuenciación'), ('Lambda (Variant Caller)', 'Llamada de variantes'), ('Lambda (Stats Aggregator)', 'Agregación de estadísticas de variantes'), ('Amazon Athena', 'Análisis de métricas QC')],
        },
    },
    'insurance-claims': {
        'titles': {
            'ko': '사고 사진 손해 평가 및 청구 보고서',
            'zh-CN': '事故照片损害评估与理赔报告',
            'zh-TW': '事故照片損害評估與理賠報告',
            'fr': "Évaluation des dommages par photo d'accident et rapport de réclamation",
            'de': 'Unfallbild-Schadensbewertung und Schadenmeldungsbericht',
            'es': 'Evaluación de daños por foto de accidente e informe de reclamación',
        },
        'summaries': {
            'ko': '본 데모는 사고 사진 기반 손해 평가 및 자동 청구 보고서 생성 파이프라인을 시연합니다. AI가 사진에서 손상 정도를 분석하고 청구 보고서를 자동 작성합니다.',
            'zh-CN': '本演示展示基于事故照片的损害评估与自动理赔报告生成流水线。AI 分析照片中的损伤程度并自动生成理赔报告。',
            'zh-TW': '本演示展示基於事故照片的損害評估與自動理賠報告產生流程。AI 分析照片中的損傷程度並自動產生理賠報告。',
            'fr': "Cette démo présente un pipeline d'évaluation des dommages basé sur les photos d'accident et de génération automatique de rapports de réclamation.",
            'de': 'Diese Demo zeigt eine Pipeline zur fotobasierten Schadensbewertung und automatischen Schadenmeldungsberichterstellung.',
            'es': 'Esta demo presenta un pipeline de evaluación de daños basado en fotos de accidentes y generación automática de informes de reclamación.',
        },
        'core_messages': {
            'ko': '사고 사진에서 AI가 손상을 자동 분석하여 청구 보고서를 즉시 생성하고 처리 시간을 단축합니다.',
            'zh-CN': 'AI 自动分析事故照片中的损伤，即时生成理赔报告并缩短处理时间。',
            'zh-TW': 'AI 自動分析事故照片中的損傷，即時產生理賠報告並縮短處理時間。',
            'fr': "L'IA analyse automatiquement les dommages sur les photos pour générer instantanément les rapports de réclamation.",
            'de': 'KI analysiert automatisch Schäden auf Unfallfotos und erstellt sofort Schadenmeldungsberichte.',
            'es': 'La IA analiza automáticamente los daños en fotos de accidentes para generar informes de reclamación al instante.',
        },
        'workflows': {
            'ko': '사고 사진 업로드 → 손상 영역 검출 → 심각도 평가 → 비용 추정 → 청구 리포트',
            'zh-CN': '事故照片上传 → 损伤区域检测 → 严重程度评估 → 费用估算 → 理赔报告',
            'zh-TW': '事故照片上傳 → 損傷區域偵測 → 嚴重程度評估 → 費用估算 → 理賠報告',
            'fr': "Upload photos → Détection zones endommagées → Évaluation gravité → Estimation coûts → Rapport réclamation",
            'de': 'Foto-Upload → Schadensbereich-Erkennung → Schweregradbewertung → Kostenschätzung → Schadenmeldungsbericht',
            'es': 'Carga fotos → Detección zonas dañadas → Evaluación gravedad → Estimación costos → Informe reclamación',
        },
        'sections': {
            'ko': ['문제 제기: 사고 사진 기반 손해 평가의 수동 처리는 시간이 오래 걸림', '사진 업로드: 사고 현장 사진 배치로 평가 시작', 'AI 손상 분석: 손상 영역 자동 검출 및 심각도 분류', '평가 결과: 손상 부위별 비용 추정과 종합 평가', '청구 리포트: 자동 생성된 청구 보고서와 처리 권고'],
            'zh-CN': ['问题提出：基于事故照片的手动损害评估耗时长', '照片上传：放置事故现场照片启动评估', 'AI 损伤分析：自动检测损伤区域并分类严重程度', '评估结果：各损伤部位费用估算和综合评估', '理赔报告：自动生成的理赔报告及处理建议'],
            'zh-TW': ['問題提出：基於事故照片的手動損害評估耗時長', '照片上傳：放置事故現場照片啟動評估', 'AI 損傷分析：自動偵測損傷區域並分類嚴重程度', '評估結果：各損傷部位費用估算和綜合評估', '理賠報告：自動產生的理賠報告及處理建議'],
            'fr': ["Problématique : L'évaluation manuelle des dommages par photo est chronophage", "Upload : Placer les photos d'accident pour démarrer l'évaluation", 'Analyse IA : Détection automatique des zones endommagées et classification de gravité', 'Résultats : Estimation des coûts par zone et évaluation globale', 'Rapport réclamation : Rapport généré automatiquement avec recommandations de traitement'],
            'de': ['Problemstellung: Manuelle fotobasierte Schadensbewertung ist zeitaufwändig', 'Upload: Unfallfotos ablegen startet die Bewertung', 'KI-Schadensanalyse: Automatische Erkennung von Schadensbereichen und Schweregradklassifikation', 'Ergebnisse: Kostenschätzung pro Bereich und Gesamtbewertung', 'Schadenmeldungsbericht: Automatisch erstellter Bericht mit Bearbeitungsempfehlungen'],
            'es': ['Problema: La evaluación manual de daños por foto consume mucho tiempo', 'Carga: Colocar fotos del accidente inicia la evaluación', 'Análisis IA: Detección automática de zonas dañadas y clasificación de gravedad', 'Resultados: Estimación de costos por zona y evaluación global', 'Informe reclamación: Informe generado automáticamente con recomendaciones de procesamiento'],
        },
        'tech_notes': {
            'ko': [('Step Functions', '워크플로우 오케스트레이션'), ('Lambda (Damage Detector)', 'AI 기반 손상 영역 검출'), ('Lambda (Severity Assessor)', '손상 심각도 평가'), ('Lambda (Cost Estimator)', '수리 비용 추정'), ('Amazon Athena', '청구 이력 집계 분석')],
            'zh-CN': [('Step Functions', '工作流编排'), ('Lambda (Damage Detector)', 'AI 驱动损伤区域检测'), ('Lambda (Severity Assessor)', '损伤严重程度评估'), ('Lambda (Cost Estimator)', '维修费用估算'), ('Amazon Athena', '理赔历史聚合分析')],
            'zh-TW': [('Step Functions', '工作流程編排'), ('Lambda (Damage Detector)', 'AI 驅動損傷區域偵測'), ('Lambda (Severity Assessor)', '損傷嚴重程度評估'), ('Lambda (Cost Estimator)', '維修費用估算'), ('Amazon Athena', '理賠歷史彙總分析')],
            'fr': [('Step Functions', 'Orchestration du workflow'), ('Lambda (Damage Detector)', 'Détection IA des zones endommagées'), ('Lambda (Severity Assessor)', 'Évaluation de la gravité'), ('Lambda (Cost Estimator)', 'Estimation des coûts de réparation'), ('Amazon Athena', "Analyse agrégée de l'historique des réclamations")],
            'de': [('Step Functions', 'Workflow-Orchestrierung'), ('Lambda (Damage Detector)', 'KI-gestützte Schadensbereich-Erkennung'), ('Lambda (Severity Assessor)', 'Schweregradbewertung'), ('Lambda (Cost Estimator)', 'Reparaturkostenschätzung'), ('Amazon Athena', 'Aggregierte Schadenhistorie-Analyse')],
            'es': [('Step Functions', 'Orquestación del flujo de trabajo'), ('Lambda (Damage Detector)', 'Detección IA de zonas dañadas'), ('Lambda (Severity Assessor)', 'Evaluación de gravedad'), ('Lambda (Cost Estimator)', 'Estimación de costos de reparación'), ('Amazon Athena', 'Análisis agregado del historial de reclamaciones')],
        },
    },
    'logistics-ocr': {
        'titles': {
            'ko': '배송 전표 OCR 및 재고 분석',
            'zh-CN': '运单 OCR 与库存分析',
            'zh-TW': '出貨單 OCR 與庫存分析',
            'fr': 'OCR de bordereaux de livraison et analyse des stocks',
            'de': 'Lieferschein-OCR und Bestandsanalyse',
            'es': 'OCR de albaranes de envío y análisis de inventario',
        },
        'summaries': {
            'ko': '본 데모는 배송 전표의 OCR 처리 및 재고 분석 파이프라인을 시연합니다. 종이 전표를 자동 디지털화하여 재고 현황을 실시간으로 파악합니다.',
            'zh-CN': '本演示展示运单的 OCR 处理与库存分析流水线。自动数字化纸质运单，实时掌握库存状况。',
            'zh-TW': '本演示展示出貨單的 OCR 處理與庫存分析流程。自動數位化紙本出貨單，即時掌握庫存狀況。',
            'fr': "Cette démo présente un pipeline OCR pour bordereaux de livraison et analyse des stocks. Les documents papier sont automatiquement numérisés pour un suivi en temps réel.",
            'de': 'Diese Demo zeigt eine OCR-Pipeline für Lieferscheine und Bestandsanalyse. Papierdokumente werden automatisch digitalisiert für Echtzeit-Bestandsübersicht.',
            'es': 'Esta demo presenta un pipeline OCR para albaranes de envío y análisis de inventario. Los documentos en papel se digitalizan automáticamente para seguimiento en tiempo real.',
        },
        'core_messages': {
            'ko': '배송 전표를 자동 OCR 처리하여 재고 데이터를 실시간으로 업데이트하고 물류 효율을 향상시킵니다.',
            'zh-CN': '自动 OCR 处理运单，实时更新库存数据并提升物流效率。',
            'zh-TW': '自動 OCR 處理出貨單，即時更新庫存資料並提升物流效率。',
            'fr': "Traiter automatiquement les bordereaux par OCR pour mettre à jour les stocks en temps réel et améliorer l'efficacité logistique.",
            'de': 'Lieferscheine automatisch per OCR verarbeiten, Bestandsdaten in Echtzeit aktualisieren und Logistikeffizienz steigern.',
            'es': 'Procesar automáticamente albaranes por OCR para actualizar inventario en tiempo real y mejorar la eficiencia logística.',
        },
        'workflows': {
            'ko': '전표 스캔 업로드 → OCR 텍스트 추출 → 필드 파싱 → 재고 업데이트 → 분석 리포트',
            'zh-CN': '运单扫描上传 → OCR 文本提取 → 字段解析 → 库存更新 → 分析报告',
            'zh-TW': '出貨單掃描上傳 → OCR 文字擷取 → 欄位解析 → 庫存更新 → 分析報告',
            'fr': 'Upload scan → Extraction OCR → Parsing champs → Mise à jour stocks → Rapport analyse',
            'de': 'Scan-Upload → OCR-Extraktion → Feld-Parsing → Bestandsaktualisierung → Analysebericht',
            'es': 'Carga escaneo → Extracción OCR → Parsing campos → Actualización inventario → Informe análisis',
        },
        'sections': {
            'ko': ['문제 제기: 종이 전표의 수동 입력은 오류가 많고 시간 소모적', '전표 업로드: 스캔된 전표 이미지 배치로 처리 시작', 'OCR 및 파싱: 텍스트 추출과 구조화 데이터 변환', '재고 업데이트: 추출 데이터 기반 실시간 재고 반영', '분석 리포트: 물류 현황 대시보드 및 이상 감지 알림'],
            'zh-CN': ['问题提出：纸质运单的手动录入容易出错且耗时', '运单上传：放置扫描运单图像启动处理', 'OCR 与解析：文本提取和结构化数据转换', '库存更新：基于提取数据实时更新库存', '分析报告：物流现状仪表板及异常检测告警'],
            'zh-TW': ['問題提出：紙本出貨單的手動輸入容易出錯且耗時', '出貨單上傳：放置掃描出貨單影像啟動處理', 'OCR 與解析：文字擷取和結構化資料轉換', '庫存更新：基於擷取資料即時更新庫存', '分析報告：物流現況儀表板及異常偵測告警'],
            'fr': ['Problématique : La saisie manuelle des bordereaux papier est source d erreurs et chronophage', 'Upload : Placer les images scannées pour démarrer le traitement', 'OCR et parsing : Extraction texte et conversion en données structurées', 'Mise à jour stocks : Actualisation en temps réel basée sur les données extraites', 'Rapport analyse : Tableau de bord logistique et alertes de détection d anomalies'],
            'de': ['Problemstellung: Manuelle Eingabe von Papierdokumenten ist fehleranfällig und zeitaufwändig', 'Upload: Gescannte Lieferschein-Bilder ablegen startet die Verarbeitung', 'OCR und Parsing: Textextraktion und Konvertierung in strukturierte Daten', 'Bestandsaktualisierung: Echtzeit-Aktualisierung basierend auf extrahierten Daten', 'Analysebericht: Logistik-Dashboard und Anomalie-Erkennungsalarme'],
            'es': ['Problema: La entrada manual de documentos en papel es propensa a errores y consume tiempo', 'Carga: Colocar imágenes escaneadas de albaranes inicia el procesamiento', 'OCR y parsing: Extracción de texto y conversión a datos estructurados', 'Actualización inventario: Actualización en tiempo real basada en datos extraídos', 'Informe análisis: Dashboard logístico y alertas de detección de anomalías'],
        },
        'tech_notes': {
            'ko': [('Step Functions', '워크플로우 오케스트레이션'), ('Lambda (OCR Engine)', '전표 텍스트 추출'), ('Lambda (Field Parser)', '구조화 데이터 파싱'), ('Lambda (Inventory Updater)', '재고 데이터 업데이트'), ('Amazon Athena', '물류 통계 분석')],
            'zh-CN': [('Step Functions', '工作流编排'), ('Lambda (OCR Engine)', '运单文本提取'), ('Lambda (Field Parser)', '结构化数据解析'), ('Lambda (Inventory Updater)', '库存数据更新'), ('Amazon Athena', '物流统计分析')],
            'zh-TW': [('Step Functions', '工作流程編排'), ('Lambda (OCR Engine)', '出貨單文字擷取'), ('Lambda (Field Parser)', '結構化資料解析'), ('Lambda (Inventory Updater)', '庫存資料更新'), ('Amazon Athena', '物流統計分析')],
            'fr': [('Step Functions', 'Orchestration du workflow'), ('Lambda (OCR Engine)', 'Extraction texte bordereaux'), ('Lambda (Field Parser)', 'Parsing données structurées'), ('Lambda (Inventory Updater)', 'Mise à jour données stocks'), ('Amazon Athena', 'Analyse statistique logistique')],
            'de': [('Step Functions', 'Workflow-Orchestrierung'), ('Lambda (OCR Engine)', 'Lieferschein-Textextraktion'), ('Lambda (Field Parser)', 'Strukturierte Daten-Parsing'), ('Lambda (Inventory Updater)', 'Bestandsdaten-Aktualisierung'), ('Amazon Athena', 'Logistik-Statistikanalyse')],
            'es': [('Step Functions', 'Orquestación del flujo de trabajo'), ('Lambda (OCR Engine)', 'Extracción de texto de albaranes'), ('Lambda (Field Parser)', 'Parsing de datos estructurados'), ('Lambda (Inventory Updater)', 'Actualización de datos de inventario'), ('Amazon Athena', 'Análisis estadístico logístico')],
        },
    },
    'retail-catalog': {
        'titles': {
            'ko': '상품 이미지 태깅 및 카탈로그 메타데이터 생성',
            'zh-CN': '商品图片标签与目录元数据生成',
            'zh-TW': '商品圖片標籤與目錄中繼資料產生',
            'fr': 'Étiquetage d images produit et génération de métadonnées catalogue',
            'de': 'Produktbild-Tagging und Katalog-Metadaten-Generierung',
            'es': 'Etiquetado de imágenes de producto y generación de metadatos de catálogo',
        },
        'summaries': {
            'ko': '본 데모는 상품 이미지의 자동 태깅 및 카탈로그 메타데이터 생성 파이프라인을 시연합니다. AI가 상품 사진을 분석하여 속성 태그와 설명을 자동 생성합니다.',
            'zh-CN': '本演示展示商品图片的自动标签与目录元数据生成流水线。AI 分析商品照片自动生成属性标签和描述。',
            'zh-TW': '本演示展示商品圖片的自動標籤與目錄中繼資料產生流程。AI 分析商品照片自動產生屬性標籤和描述。',
            'fr': "Cette démo présente un pipeline d'étiquetage automatique d'images produit et de génération de métadonnées catalogue. L'IA analyse les photos pour générer tags et descriptions.",
            'de': 'Diese Demo zeigt eine Pipeline zum automatischen Produktbild-Tagging und zur Katalog-Metadaten-Generierung. KI analysiert Produktfotos und erstellt automatisch Tags und Beschreibungen.',
            'es': 'Esta demo presenta un pipeline de etiquetado automático de imágenes de producto y generación de metadatos de catálogo. La IA analiza fotos de productos para generar etiquetas y descripciones.',
        },
        'core_messages': {
            'ko': '상품 이미지에서 AI가 속성을 자동 추출하여 카탈로그 메타데이터를 즉시 생성하고 상품 등록을 가속화합니다.',
            'zh-CN': 'AI 自动从商品图片中提取属性，即时生成目录元数据并加速商品上架。',
            'zh-TW': 'AI 自動從商品圖片中擷取屬性，即時產生目錄中繼資料並加速商品上架。',
            'fr': "L'IA extrait automatiquement les attributs des images pour générer instantanément les métadonnées catalogue et accélérer la mise en ligne.",
            'de': 'KI extrahiert automatisch Attribute aus Produktbildern, erstellt sofort Katalog-Metadaten und beschleunigt die Produktregistrierung.',
            'es': 'La IA extrae automáticamente atributos de imágenes de productos para generar metadatos de catálogo al instante y acelerar el registro de productos.',
        },
        'workflows': {
            'ko': '상품 이미지 업로드 → 시각 분석 → 속성 태깅 → 설명 생성 → 카탈로그 리포트',
            'zh-CN': '商品图片上传 → 视觉分析 → 属性标签 → 描述生成 → 目录报告',
            'zh-TW': '商品圖片上傳 → 視覺分析 → 屬性標籤 → 描述產生 → 目錄報告',
            'fr': 'Upload images → Analyse visuelle → Étiquetage attributs → Génération descriptions → Rapport catalogue',
            'de': 'Bild-Upload → Visuelle Analyse → Attribut-Tagging → Beschreibungsgenerierung → Katalogbericht',
            'es': 'Carga imágenes → Análisis visual → Etiquetado atributos → Generación descripciones → Informe catálogo',
        },
        'sections': {
            'ko': ['문제 제기: 수천 개 상품의 수동 태깅과 설명 작성은 병목 구간', '이미지 업로드: 상품 사진 배치로 처리 시작', 'AI 분석 및 태깅: 시각 AI로 색상, 소재, 카테고리 등 자동 추출', '메타데이터 생성: 상품 설명과 검색 키워드 자동 생성', '카탈로그 리포트: 처리 완료 통계 및 품질 검증 결과'],
            'zh-CN': ['问题提出：数千商品的手动标签和描述编写是瓶颈', '图片上传：放置商品照片启动处理', 'AI 分析与标签：视觉 AI 自动提取颜色、材质、类别等', '元数据生成：自动生成商品描述和搜索关键词', '目录报告：处理完成统计及质量验证结果'],
            'zh-TW': ['問題提出：數千商品的手動標籤和描述撰寫是瓶頸', '圖片上傳：放置商品照片啟動處理', 'AI 分析與標籤：視覺 AI 自動擷取顏色、材質、類別等', '中繼資料產生：自動產生商品描述和搜尋關鍵字', '目錄報告：處理完成統計及品質驗證結果'],
            'fr': ['Problématique : L étiquetage manuel de milliers de produits est un goulot', 'Upload : Placer les photos produit pour démarrer le traitement', 'Analyse IA et étiquetage : Extraction automatique couleur, matière, catégorie par vision IA', 'Génération métadonnées : Descriptions produit et mots-clés de recherche automatiques', 'Rapport catalogue : Statistiques de traitement et résultats de validation qualité'],
            'de': ['Problemstellung: Manuelles Tagging tausender Produkte ist ein Engpass', 'Upload: Produktfotos ablegen startet die Verarbeitung', 'KI-Analyse und Tagging: Automatische Extraktion von Farbe, Material, Kategorie per Vision-KI', 'Metadaten-Generierung: Automatische Produktbeschreibungen und Suchbegriffe', 'Katalogbericht: Verarbeitungsstatistiken und Qualitätsvalidierungsergebnisse'],
            'es': ['Problema: El etiquetado manual de miles de productos es un cuello de botella', 'Carga: Colocar fotos de productos inicia el procesamiento', 'Análisis IA y etiquetado: Extracción automática de color, material, categoría por visión IA', 'Generación metadatos: Descripciones de producto y palabras clave de búsqueda automáticas', 'Informe catálogo: Estadísticas de procesamiento y resultados de validación de calidad'],
        },
        'tech_notes': {
            'ko': [('Step Functions', '워크플로우 오케스트레이션'), ('Lambda (Image Analyzer)', 'AI 기반 시각 분석'), ('Lambda (Tag Generator)', '속성 태그 생성'), ('Lambda (Description Writer)', '상품 설명 자동 작성'), ('Amazon Athena', '카탈로그 통계 분석')],
            'zh-CN': [('Step Functions', '工作流编排'), ('Lambda (Image Analyzer)', 'AI 驱动视觉分析'), ('Lambda (Tag Generator)', '属性标签生成'), ('Lambda (Description Writer)', '商品描述自动生成'), ('Amazon Athena', '目录统计分析')],
            'zh-TW': [('Step Functions', '工作流程編排'), ('Lambda (Image Analyzer)', 'AI 驅動視覺分析'), ('Lambda (Tag Generator)', '屬性標籤產生'), ('Lambda (Description Writer)', '商品描述自動產生'), ('Amazon Athena', '目錄統計分析')],
            'fr': [('Step Functions', 'Orchestration du workflow'), ('Lambda (Image Analyzer)', 'Analyse visuelle IA'), ('Lambda (Tag Generator)', "Génération d'étiquettes attributs"), ('Lambda (Description Writer)', 'Rédaction automatique descriptions'), ('Amazon Athena', 'Analyse statistique catalogue')],
            'de': [('Step Functions', 'Workflow-Orchestrierung'), ('Lambda (Image Analyzer)', 'KI-gestützte visuelle Analyse'), ('Lambda (Tag Generator)', 'Attribut-Tag-Generierung'), ('Lambda (Description Writer)', 'Automatische Beschreibungserstellung'), ('Amazon Athena', 'Katalog-Statistikanalyse')],
            'es': [('Step Functions', 'Orquestación del flujo de trabajo'), ('Lambda (Image Analyzer)', 'Análisis visual IA'), ('Lambda (Tag Generator)', 'Generación de etiquetas de atributos'), ('Lambda (Description Writer)', 'Redacción automática de descripciones'), ('Amazon Athena', 'Análisis estadístico de catálogo')],
        },
    },
}


def generate_demo_guide(uc_dir, lang, uc_data):
    """Generate a single demo-guide file."""
    title = uc_data['titles'][lang]
    summary = uc_data['summaries'][lang]
    core_msg = uc_data['core_messages'][lang]
    workflow = uc_data['workflows'][lang]
    sections = uc_data['sections'][lang]
    tech_notes = uc_data['tech_notes'][lang]
    switcher = LANG_SWITCHERS[lang]
    labels = LANG_LABELS[lang]

    # Build tech notes table
    tech_rows = ""
    for comp, role in tech_notes:
        tech_rows += f"| {comp} | {role} |\n"

    content = f"""# {title} -- Demo Guide

\U0001f310 **Language / \u8a00\u8a9e**: {switcher}

## Executive Summary

{summary}

**{labels['core']}**: {core_msg}

**{labels['duration']}**: 3\u20135 min

---

## Workflow

```
{workflow}
```

---

## Storyboard (5 Sections / 3\u20135 min)

### Section 1 (0:00\u20130:45)
> {sections[0]}

### Section 2 (0:45\u20131:30)
> {sections[1]}

### Section 3 (1:30\u20132:30)
> {sections[2]}

### Section 4 (2:30\u20133:45)
> {sections[3]}

### Section 5 (3:45\u20135:00)
> {sections[4]}

---

## Technical Notes

| Component | Role |
|-----------|------|
{tech_rows}
---

{labels['footer']}
"""
    return content


def main():
    count = 0
    for uc_dir, uc_data in USE_CASES.items():
        docs_dir = BASE_DIR / uc_dir / 'docs'
        docs_dir.mkdir(parents=True, exist_ok=True)

        for lang in LANGUAGES:
            filename = f'demo-guide.{lang}.md'
            filepath = docs_dir / filename
            content = generate_demo_guide(uc_dir, lang, uc_data)
            filepath.write_text(content, encoding='utf-8')
            count += 1

    print(f"\n{'='*50}")
    print(f"  Generated {count} demo-guide files")
    print(f"  ({len(USE_CASES)} use cases x {len(LANGUAGES)} languages)")
    print(f"{'='*50}")


if __name__ == '__main__':
    main()
