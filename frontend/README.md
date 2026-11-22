# Smart Glosas AI — Frontend Vue 3

Interfaz web vinculada a las APIs reales de Smart Glosas AI. **No es un demo de datos simulados** y, por seguridad, requiere un backend funcional, una institucion autorizada y Google Sign-In. Sin estos servicios, el login no puede completarse.

## Modulos

- Inicio — resumen institucional.
- Prevenir glosas — analisis individual o masivo desde salida de Armado de Cuentas u otros sistemas.
- Responder glosas — analisis individual o masivo de objeciones de EPS; respuestas basadas en reglas configuradas con evidencia.
- Seguimiento — historial, consulta y exportacion de analisis.
- Configuracion — reglas versionadas por EPS, modalidad y tipo de servicio.

## Ejecutar localmente

```bash
cp .env.example .env
npm install
npm run dev
```

El backend debe responder en `VITE_API_URL`, generalmente `http://localhost:8080`. Consultar `../README.md` para la configuracion de acceso Google y backend.

## Compilar

```bash
npm install
npm run build
```

El frontend usa `vue-tsc` y `vite`, con CI configurado para verificar la compilacion en `main` al publicar el repositorio.

## Desplegar en Railway

1. Crear un servicio Web a partir del repositorio **independiente** de Smart Glosas AI.
2. Root Directory: `frontend`.
3. Dockerfile: `frontend/Dockerfile` relativo a la raiz del repositorio, o `Dockerfile` si la configuracion interpreta la ruta desde el root.
4. Definir `VITE_API_URL` con la URL HTTPS publica de la API; este valor se incorpora en **build time**. Volver a compilar al cambiarlo.
5. Exponer el dominio HTTPS generado. Configurar ese dominio en `CORS_ORIGINS` del backend.
6. Configurar el dominio del frontend como origen autorizado del cliente OAuth web Google.

**IMPORTANTE:** No publicar el frontend como aplicacion operacional antes de configurar Google, PostgreSQL, reglas revisadas y controles de privacidad. No introducir datos reales de pacientes en esta version.

## Compartir con el equipo

El repositorio tiene como rama principal `main`, e incluye los servicios en directorios distintos. No copiar estos archivos sobre el repositorio `smart-contract`.
