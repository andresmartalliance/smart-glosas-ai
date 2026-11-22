# Registro de validación V0.1.0

## Verificado en la entrega

- Backend FastAPI: `PYTHONPATH=. pytest -q` **17 pruebas exitosas**.
- Migración Alembic `0001_initial` ejecutada sobre base SQLite limpia de validación; `alembic check` no halló diferencias.
- Código TypeScript de `frontend/src/App.vue`: análisis sintáctico por compilador TypeScript global sin errores.
- JSON Schema de contratos de intercambio incluidos para evolución hacia Armando y MAIRA.
- No se han usado datos clínicos, credenciales reales ni información de clientes.

## No verificado / pendiente

- `npm run build` Vue/Vite: no ejecutable en este entorno porque las dependencias de npm no están instaladas y no hay acceso a registries externos. El CI queda preparado para ejecutarlo cuando se cargue a un repositorio con acceso a internet.
- No hay despliegue Railway ni repositorio remoto nuevo para Glosas AI; este paquete es independiente del repo Smart Contract.
- No se verificó PostgreSQL real, Google Sign-In real, navegador autenticado, archivos reales de IPS, PDF/RIPS/FEV, normativa completa ni Gemini.
- La generación de contestaciones sólo utiliza plantillas institucionales configuradas, con referencias declaradas y revisión humana; no equivale a un agente autónomo generativo.
- No existe aún un predictor entrenado ni conexión con Smart Contract o Smart Finance.
- Sin controles de privacidad completos no ingresar historias clínicas ni identificadores reales de pacientes.

## Próximo paquete técnico

1. Repositorio privado independiente y despliegue Development con CI y PostgreSQL propios.
2. Compilar frontend, habilitar Google para IPS y validar perfiles en navegador.
3. Ingesta documental segura FEV/RIPS/soportes y parser de fuentes heterogéneas; auditoría del contenido, no solo referencias.
4. Catálogo normativo verificable y versionado por vigencia, con reglas clínicas/administrativas revisadas por expertos.
5. Agente de respuestas con Gemini, trazabilidad de citas y mecanismos contra alucinaciones; aprobación y exportación formal masiva.
6. Medir alertas preventivas contra glosas reales para entrenar y calibrar predicción por causal/pagador.
