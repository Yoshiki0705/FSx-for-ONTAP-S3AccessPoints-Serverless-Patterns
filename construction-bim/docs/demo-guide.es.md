# Detección de cambios BIM y verificación de cumplimiento de seguridad -- Demo Guide

🌐 **Language / 言語**: [日本語](demo-guide.md) | [English](demo-guide.en.md) | [한국어](demo-guide.ko.md) | [简体中文](demo-guide.zh-CN.md) | [繁體中文](demo-guide.zh-TW.md) | [Français](demo-guide.fr.md) | [Deutsch](demo-guide.de.md) | Español

## Executive Summary

Esta demo presenta un pipeline de detección de cambios BIM y verificación automática de cumplimiento de seguridad. Las violaciones se detectan automáticamente durante las modificaciones.

**Mensaje clave**: Detectar automáticamente violaciones de seguridad en cambios BIM para eliminar riesgos desde la fase de diseño.

**Duración prevista**: 3–5 min

---

## Workflow

```
Carga BIM → Detección cambios → Matching normativo → Detección violaciones → Informe cumplimiento
```

---

## Storyboard (5 Sections / 3–5 min)

### Section 1 (0:00–0:45)
> Problema: La revisión manual de seguridad en cada cambio es ineficiente

### Section 2 (0:45–1:30)
> Carga BIM: Colocar archivos de modelo modificados inicia la verificación

### Section 3 (1:30–2:30)
> Detección y matching: Análisis diff automático y comparación con normas de seguridad

### Section 4 (2:30–3:45)
> Violaciones detectadas: Lista de incumplimientos y niveles de gravedad

### Section 5 (3:45–5:00)
> Informe cumplimiento: Generación del informe con recomendaciones correctivas

---

## Technical Notes

| Component | Role |
|-----------|------|
| Step Functions | Orquestación del flujo de trabajo |
| Lambda (Change Detector) | Detección de cambios BIM |
| Lambda (Rule Matcher) | Motor de matching normativo |
| Lambda (Report Generator) | Generación de informe de cumplimiento |
| Amazon Athena | Análisis agregado del historial de violaciones |

---

*Este documento sirve como guía de producción para videos de demostración técnica.*
