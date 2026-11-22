# Smart Glosas AI - Integracion con plataforma Smart V0.3

No se construye otro login. Smart autentica al usuario y entrega un JWT firmado y corto al frontend embebido; no colocar secretos permanentes en navegador, URL, localStorage o repositorio.

## Intercambio de contexto
1. Configurar VITE_SMART_HOST_ORIGIN con el ORIGEN HTTPS exacto de la plataforma Smart y recompilar el web.
2. El iframe emite {type:'SMART_GLOSAS_READY'} al host.
3. El host responde con iframe.contentWindow.postMessage({type:'SMART_GLOSAS_CONTEXT',token:jwt}, 'https://web-development-02304355.up.railway.app').
4. El frontend retiene el token solo en memoria y adjunta Authorization: Bearer a la API. Renovar antes de 15 minutos.

## JWT HS256 de la plataforma
Header exacto: {"alg":"HS256","typ":"JWT"}.
Payload requerido:
- iss: smart-platform
- aud: smart-glosas-ai
- sub: identificador del usuario (correo u otro id estable)
- tenant_id: identificador opaco de IPS (maximo 36 caracteres)
- tenant_name: nombre IPS, para provision inicial desde usuario ADMIN
- roles: lista con ADMIN, CONFIGURADOR, AUDITOR o ANALISTA
- exp: Unix time de vencimiento en menos de 15 minutos
- nbf: opcional, Unix time

API variable: SMART_AUTH_MODE=platform; SMART_PLATFORM_JWT_SECRET (aleatorio >=32 bytes) compartido SOLO por servidores Smart y Smart Glosas AI. La API valida firma, audiencia, exp, tenant, rol y auditoria. Nunca exponga el secreto en Vue ni use la clave Gemini como secreto JWT.

## Gemini
En la API de Railway Smart Glosas AI configurar GEMINI_API_KEY y GEMINI_MODEL (nombre disponible para la cuenta). La clave va SOLO en backend.
POST /api/v1/analyses/{id}/ai-review recibe un analisis existente de la IPS, minimiza datos y retorna borrador sujeto a revision humana; no hace envios a EPS.
No se envian a Gemini documentos, datos crudos de historia clinica ni campos abiertos de pacientes. El filtro de identificadores es preventivo, no garantiza anonimizacion; NO procesar informacion real hasta completar evaluacion de privacidad y tratamiento de texto libre.

## Estado
No hay integracion activa con host hasta definir su origen HTTPS y provisionar el secreto de firma en ambos servicios. La prueba de Gemini real requiere asignar la clave en el nuevo proyecto.
