# Smart Glosas AI - Frontend Vue 3

Modulo embebible en la plataforma Smart. No contiene Google Sign-In independiente.
La plataforma anfitriona transmite un JWT efimero firmado por postMessage con origen verificado. Ver docs/INTEGRACION_SMART.md.

Pantallas: Inicio, Prevenir glosas, Responder glosas, Seguimiento, Configuracion. No contiene datos precargados.

Build: npm install && npm run build. Variables Vite: VITE_API_URL y VITE_SMART_HOST_ORIGIN (origen exacto).
La URL directa muestra "Este modulo se abre desde la plataforma Smart". Sin contexto de la plataforma no se permite consultar cuentas.
El boton Analizar con Gemini aparece al configurar GEMINI_API_KEY en la API. Su propuesta requiere aprobacion humana.
