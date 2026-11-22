# Integracion de repositorios — Smart Glosas AI

**Producto independiente:** `smart-glosas-ai`; rama principal: `main`.

Ningun archivo de Smart Contract ni su repositorio GitHub/Railway se modifica para publicar este producto.

## Estado de publicacion

Este paquete incluye un repositorio Git local, preparado con un commit en `main`, y un archivo `.bundle` con su historia. **No implica que exista aun un repositorio remoto**. El conector GitHub disponible en esta sesion no dispone de una operacion para crear repositorios, y el nuevo repo no fue encontrado.

## Publicar el bundle en GitHub

1. Crear en GitHub un repositorio **privado y vacio** llamado `smart-glosas-ai` dentro de la cuenta u organizacion que vaya a mantenerlo. No inicializarlo con README para evitar un historial divergente.
2. Descomprimir el archivo ZIP de la entrega y localizar el archivo `Smart_Glosas_AI_main.bundle`.
3. Desde una terminal con Git y permisos de escritura:

```bash
git clone Smart_Glosas_AI_main.bundle smart-glosas-ai
cd smart-glosas-ai
git branch --show-current             # debe mostrar main
git remote rename origin bundle
# Sustituir la URL siguiente por la URL real del repo privado recien creado.
git remote add origin https://github.com/ORGANIZACION/smart-glosas-ai.git
git push -u origin main
```

4. Verificar que GitHub muestre `main` como rama por defecto, que CI se ejecute y que los archivos esten visibles.

## Integrar con GitLab

Recomendada: configurar en GitLab el espejo de este repositorio GitHub o importar el repo privado con las credenciales y permisos pertinentes. No crear un proyecto con historias distintas para el mismo codigo.

Alternativa: despues de crear el proyecto **vacio** en GitLab, agregarlo como remoto y publicar:

```bash
git remote add gitlab git@gitlab.com:GRUPO/smart-glosas-ai.git
git push -u gitlab main
```

Para sincronizacion continua, configurar el mirroring en el servicio que vaya a ser la fuente de verdad. Evitar ediciones divergentes en los dos repositorios.

## Railway

Crear un proyecto nuevo llamado `smart-glosas-ai` con servicios independientes `api`, `web` y `Postgres`:

- API usa root `backend`, Dockerfile propio, predeploy `alembic upgrade head`, `DATABASE_URL` de Postgres **nuevo**, `SMART_GOOGLE_CLIENT_ID`, `SMART_GLOSAS_BOOTSTRAP_EMAILS` y `CORS_ORIGINS`.
- Web usa root `frontend`, Dockerfile propio, `VITE_API_URL` como variable para la compilacion.
- Crear un cliente de Google OAuth autorizado para el dominio del proyecto, o configurar apropiadamente uno existente sin compartir credenciales privadas.
- No compartir base de datos ni secretos con `smart-contract` o `smart-service-desk`.

## Calidad y limites

Antes de la prueba web real deben aprobarse la compilacion de Vue/Vite en CI, la API en Railway, Google Sign-In y una primera cuenta autorizada. No utilizar datos clinicos reales. Actualmente la IA generativa Gemini y el motor de prediccion estadistica aun no estan integrados en el backend V0.1.
