# Variables de Entorno para Heroku - Chat Agent Service

Configura las siguientes variables de entorno en Heroku para el servicio de agente de chat.

## Comando rápido para configurar todas las variables

```bash
heroku config:set \
  ENVIRONMENT=production \
  SERVICE_NAME="Chat Agent Service" \
  SERVICE_VERSION="1.0.0" \
  LOG_LEVEL="INFO" \
  BACKEND_SERVICE_URL_PROD="https://horizon-backend-316b23e32b8b.herokuapp.com" \
  GEMINI_API_KEY="tu_gemini_api_key" \
  SUPABASE_URL="https://tu-proyecto.supabase.co" \
  SUPABASE_SERVICE_ROLE_KEY="tu_service_role_key" \
  -a chat-agent-horizon-cc5e16d4b37e
```

## Variables requeridas

### Configuración básica
- `ENVIRONMENT=production` - **IMPORTANTE**: Esto hace que use las URLs de producción
- `SERVICE_NAME="Chat Agent Service"`
- `SERVICE_VERSION="1.0.0"`
- `LOG_LEVEL="INFO"`

### Backend Service (Comunicación entre servicios)
- `BACKEND_SERVICE_URL_PROD="https://horizon-backend-316b23e32b8b.herokuapp.com"`

### Google AI
- `GEMINI_API_KEY` - API key de Google Gemini
- `GOOGLE_API_KEY` - (alternativo a GEMINI_API_KEY)

### Supabase
- `SUPABASE_URL` - URL de tu proyecto Supabase
- `SUPABASE_SERVICE_ROLE_KEY` - Service role key de Supabase

## Variables opcionales

```bash
heroku config:set \
  SUPABASE_ANON_KEY="tu_anon_key" \
  SUPABASE_BUCKET_NAME="portfolio-files" \
  SUPABASE_BASE_PREFIX="Graficos" \
  ENABLE_SUPABASE_UPLOAD=true \
  MODEL_FLASH="gemini-2.5-flash" \
  MODEL_PRO="gemini-2.5-pro" \
  DEFAULT_CURRENCY="USD" \
  -a chat-agent-horizon-cc5e16d4b37e
```

## Variables que NO debes configurar en Heroku

Las siguientes variables son para desarrollo local solamente:
- ❌ `SERVICE_HOST` - Heroku maneja esto automáticamente
- ❌ `SERVICE_PORT` - Heroku usa $PORT automáticamente
- ❌ `CORS_ORIGINS` - Se configura automáticamente en el código

## Verificar configuración

```bash
# Ver todas las variables configuradas
heroku config -a chat-agent-horizon-cc5e16d4b37e

# Ver una variable específica
heroku config:get ENVIRONMENT -a chat-agent-horizon-cc5e16d4b37e
```

## Obtener API Keys

### Google AI (Gemini)
1. Ir a https://aistudio.google.com/app/apikey
2. Crear o copiar tu API key
3. Configurar como `GEMINI_API_KEY`

### Supabase
1. Ir a tu proyecto en https://supabase.com
2. Settings → API
3. Copiar:
   - Project URL → `SUPABASE_URL`
   - service_role key → `SUPABASE_SERVICE_ROLE_KEY`
   - anon public key → `SUPABASE_ANON_KEY` (opcional)

## Notas importantes

1. **ENVIRONMENT=production** es CRÍTICO - sin esto, el servicio intentará conectarse a localhost:8000 en lugar del backend de Heroku
2. El `GEMINI_API_KEY` es obligatorio para que el agente funcione
3. Las configuraciones CORS ya incluyen ambas URLs de Heroku automáticamente
4. No configures `SERVICE_PORT` - Heroku asigna el puerto automáticamente vía `$PORT`
5. Nunca compartas tus API keys o service role keys públicamente

## CORS automático

El servicio ya está configurado para aceptar peticiones desde:
- ✅ Desarrollo local (localhost:3000, localhost:8000, localhost:5173)
- ✅ Backend de producción (https://horizon-backend-316b23e32b8b.herokuapp.com)
- ✅ Chat Agent de producción (https://chat-agent-horizon-cc5e16d4b37e.herokuapp.com)

No necesitas configurar CORS_ORIGINS manualmente.
