# Smart Glosas AI - Development

Repositorio independiente: `andresmartalliance/smart-glosas-ai` (rama `main`).

- Frontend: https://web-development-02304355.up.railway.app
- API: https://api-development-79b4c191.up.railway.app
- Healthcheck: https://api-development-79b4c191.up.railway.app/health
- Base de datos: PostgreSQL dedicado dentro del proyecto Railway `smart-glosas-ai`, ambiente `development`.
- Servicios Railway: `web`, `api` y `Postgres`.
- Variables de compilacion web: `VITE_API_URL` con URL publica de esta API.
- CORS API: solo dominio de este frontend.

## Ingreso Google

El frontend utiliza Google Identity Services y el backend valida el ID token. Para que funcione el boton Google se debe autorizar en Google Cloud el origen `https://web-development-02304355.up.railway.app` en el cliente OAuth configurado para Smart Glosas AI. La cuenta bootstrap en development debe tener acceso a la creacion de instituciones. No se cargan pacientes ni facturas reales en el piloto.

## Alcance real V0.2

- Prevent y Respond disponibles con motor de reglas institucionales parametrizables.
- Respuesta de tipo borrador basada en plantillas internas y evidencias, siempre con validacion humana.
- No disponible aun: lectura completa de PDF clinicos, respuesta generativa con Gemini, prediccion probabilistica entrenada, integraciones ERP/EPS ni envio automatico.
- Nunca utilizar bases de datos ni secretos de Smart Contract.

## Verificaciones

- Confirmar 3 servicios de Railway en `SUCCESS`.
- Confirmar API `/health` devuelve `status: ok`.
- Ejecutar CI GitHub para `backend` y `frontend`.
- Probar acceso Google y flujo completo Prevent y Respond con datos sinteticos.
