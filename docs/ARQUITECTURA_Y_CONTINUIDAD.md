# Smart Glosas AI — Documento de continuidad V0.1.0

## Objetivo aprobado

Construir una aplicación IPS-first con dos capacidades igual de importantes: **Smart Prevent** (analiza cuentas después del Armado de Cuentas y antes de la radicación) y **Smart Respond** (analiza y prepara contestaciones o subsanaciones a glosas y devoluciones, de forma masiva). El producto es independiente: no requiere licencia de Smart Contract, conexión con una EPS ni uso de Smart Finance.

La evolución prevista incluye llamadas tempranas desde Validación de Derechos, Autorizaciones y etapas clínicas, además de operación centralizada EPS con portal multi-IPS. No se implementan estas capacidades ahora.

## Núcleo de reglas y fuentes

- Catálogos y reglas sin codificar EPS, modalidad contractual o tarifa.
- Regla con alcance por payer, modality, service_type, objection_kind, objection_code, vigencia, versión, evidencia requerida y referencia de fuente.
- Aplicar norma obligatoria diferente de condiciones privadas contractuales; las reglas tienen que verificarse y aprobarse antes de incorporarlas al catálogo legal operativo.
- Un contrato, anexo o nota técnica es **fuente contextual opcional**. No disponer de ellos no bloquea todas las otras evaluaciones, pero sí las conclusiones que dependan de ellos.
- Tipos de resultado: REVIEW_REQUIRED, INSUFFICIENT_EVIDENCE, NO_ALERTS_DETECTED, NO_RULES. Ausencia de reglas no equivale a ausencia de riesgo.
- Resultados de Prevent deben contrastarse con glosas/devoluciones efectivamente recibidas. Probabilidad calibrada exige datos históricos etiquetados, entrenamiento, evaluación y métricas por EPS y causal.

## Integraciones futuras (contratos desacoplados)

- **MAIRA:** exportará versiones de cláusulas contractuales, tarifas, nota técnica y vigencias, siempre con autorización y tenant bien identificado.
- **Armando:** invocará un endpoint de prevención con referencia de cuenta, hechos, eventos y manifiesto de soportes, sin imponer esquema de ERP o estructura por EPS.
- **Glosas AI:** publicará riesgos, hallazgos y resultados por interfaces versionadas y permisos explícitos.
- Estas integraciones NO están construidas. Datos compartidos únicamente por autorización, no acceso directo entre bases.

## Hito 1 entregado en código

- Código Python y Vue3 independiente.
- Autenticación Google validada en API; membership comprobado con tenant.
- Creación de institución de desarrollo bajo lista blanca explícita.
- Motor de reglas extensible, con versionamiento y snapshot por análisis.
- Importador de cuentas y objeciones CSV/JSON con mapeo variable.
- Dos APIs para análisis masivos (500 por solicitud), bitácora de cambios, aprobación humana y exportación resumen.
- UI inicial de IPS: Inicio, Prevenir glosas, Responder glosas, Seguimiento y Configuración.
- Pruebas unitarias/integración para ámbitos, vigencias, faltantes, importación y permisos.

## Límites y siguiente paquete

1. Validación normativa 2026, catálogo oficial de códigos y términos con versión por vigencia; aprobación de experto regulatorio.
2. Ingesta segura de PDF, RIPS y FEV y relación documental de anexos, observaciones y pacientes; datos sensibles solo en infraestructura controlada.
3. Agente Gemini con gobernanza de datos, referencias de evidencia exactas y contestaciones sustentadas editables, sin invenciones.
4. Configuración UX avanzada y ciclo de corrección/respuesta parcial, incluyendo exportación en formatos formalmente exigibles.
5. Integración con salida real de Armado de Cuentas sin paquete quemado; prueba con datos sintéticos y después datos autorizados.

## Estado

Hito de base en archivo local, aún no desplegado ni migrado a GitHub/Railway por inexistencia de repositorio nuevo. No modificar el repo de Smart Contract en manos del director tecnológico.

## Preparación de interoperabilidad y despliegue

Se añadieron contratos JSON Schema independientes para la cuenta armada, el contexto de contrato/nota técnica y el resultado de Glosas AI. Estas especificaciones permiten definir interfaces entre MAIRA, Armando y Glosas sin acoplar repositorios. No existen llamadas cruzadas todavía.

El backend incluye migración Alembic inicial (`0001_initial`) ejecutable en PostgreSQL, independiente de Smart Contract.
