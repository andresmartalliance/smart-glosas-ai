# Smart Glosas AI · Desarrollo inicial independiente (0.1.0)

Producto IPS-first. Conserva la posibilidad de conectar MAIRA (contratos y nota técnica) y Armando (ciclo económico), **sin depender de ninguno de ellos**.

## Dos capacidades del MVP

- **Smart Prevent:** analiza cuentas listas para radicar. Reglas versionadas por IPS, EPS, modalidad y servicio, verificando evidencias disponibles. La categoría `NO_RULES` **no es aprobación de una cuenta**. Las alertas son riesgos explicables, no probabilidades estadísticas.
- **Smart Respond:** recibe glosas y devoluciones independientes de las EPS, clasifica su tipo y aplica las mismas reglas. Puede preparar un borrador **solo mediante plantillas institucionales expresas con referencias y evidencias**. Todas las respuestas requieren revisión humana. No existe envío automático ni aceptación tácita por IA.

## Stack

FastAPI + SQLAlchemy + PostgreSQL en producción; Vue 3 + Vite; autenticación Google ID token; aislamiento lógico por institución y auditoría. El backend tiene SQLite únicamente para desarrollo local. No hay bases clínicas ni expedientes reales incluidos.

## Inicio local backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Definir SMART_GOOGLE_CLIENT_ID y SMART_GLOSAS_BOOTSTRAP_EMAILS en el entorno.
alembic upgrade head
uvicorn app.main:app --reload --port 8080
```

No crear instituciones con datos reales durante el piloto. `POST /api/v1/institutions` está limitado a cuentas autorizadas y `APP_ENV=development`.

## Inicio local frontend

```bash
cd frontend
npm install
cp .env.example .env
npm run dev
```

## Pruebas

```bash
cd backend && PYTHONPATH=. pytest -q
cd frontend && npm run build
```

## API

- `GET /api/v1/config`, `GET /api/v1/session`
- `POST /api/v1/institutions` (administración inicial en desarrollo)
- `POST /api/v1/rules`, `GET /api/v1/rules` — catálogo institucional versionado
- `POST /api/v1/mappings`, `GET /api/v1/mappings` — perfiles de importación versionados
- `POST /api/v1/imports/preview` — mapeo de cuentas CSV/JSON sin asumir columnas
- `POST /api/v1/imports/objections/preview` — mapeo de glosas/devoluciones CSV/JSON
- `POST /api/v1/analyses/prevent` — una o hasta 500 cuentas
- `POST /api/v1/analyses/respond` — una o hasta 500 objeciones
- `GET /api/v1/analyses`, `GET /api/v1/analyses/{id}`
- `POST /api/v1/analyses/{id}/approve` — aprobación interna, **no transmite**
- `GET /api/v1/exports/analyses.csv` — resumen de análisis, no contestaciones formales

Todas las rutas institucionales requieren Google ID token válido y el encabezado `X-Tenant-Id`, comprobado contra membership en DB.

## Seguridad / estado real

Este paquete todavía **no está listo para pacientes ni cuentas reales**: falta RLS/PostgreSQL, migraciones productivas, evaluación de privacidad y manejo de historias clínicas/soportes PDF, controles completos de acceso, versionamiento normativo validado por expertos, carga segura de adjuntos, evidencia a nivel de documento y confirmación de integraciones. Las tablas se crean mediante migraciones Alembic tanto en desarrollo como en producción.

Tampoco hay predicción estadística entrenada ni contestación generativa con Gemini en esta versión: se está consolidando la base auditable que evitará respuestas inventadas. Si no hay reglas, la salida es explícitamente `NO_RULES`.

### Para llevarlo a un repositorio y Railway

Crear repositorio GitHub independiente (ej. `smart-glosas-ai`), cargar el contenido de esta carpeta y agregar CI. En Railway crear **un nuevo proyecto** con servicios backend, frontend y PostgreSQL, sin compartir bases ni secretos con Smart Contract. Configurar `SMART_GOOGLE_CLIENT_ID`, las URLs CORS y `DATABASE_URL` en API; configurar `VITE_API_URL` como argumento de compilación web. **No reutilizar un DATABASE_URL ni una clave privada de otros productos.**

### Migraciones de base de datos

Para un despliegue nuevo con PostgreSQL y variables configuradas, ejecutar **antes de arrancar la API**:

```bash
cd backend
alembic upgrade head
```

En Railway, preferir un `preDeployCommand` de migración. El Dockerfile incluye `migrations/` y `alembic.ini`. Nunca utilizar el volumen de PostgreSQL de Smart Contract.

### Contratos entre agentes

En `contracts/` se incluyen especificaciones iniciales JSON Schema (`assembled-account.v1`, `contract-context.v1` y `glosas-analysis.v1`). Son **contratos de intercambio para futuro**, no conexiones activas con MAIRA ni Armando.


## Entrega a GitHub / GitLab (rama main)

El codigo se entrega en un repositorio Git independiente con rama principal `main` y en un `.bundle` transportable. **La existencia de un commit local no equivale a una publicacion remota**. Para crear un repo privado GitHub, publicar `main`, crear los servicios en Railway e integrar con GitLab, seguir `docs/INTEGRACION_GITHUB_GITLAB.md`.

El frontend Vue 3 esta conectado a rutas API reales y no utiliza informacion de prueba precargada. Para ingresar requiere Google OAuth y una institucion autorizada. El compilado Vite y el navegador autenticado deben validarse una vez publicados en un CI con dependencias npm disponibles.

## V0.3 - Smart integrado y Gemini

Frontend sin Google Sign-In propio: recibe contexto firmado desde la plataforma Smart, con IPS y rol validados por backend. Servicio de Gemini en FastAPI mediante POST /api/v1/analyses/{id}/ai-review (manual y auditado). No se envian respuestas a EPS. Requiere variables SMART_AUTH_MODE=platform, SMART_PLATFORM_JWT_SECRET, VITE_SMART_HOST_ORIGIN y GEMINI_API_KEY. Ver docs/INTEGRACION_SMART.md. Datos sinteticos unicamente hasta validacion de privacidad.
