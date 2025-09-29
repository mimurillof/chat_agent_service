# Guía de Despliegue en Heroku - Chat Agent Service

## Requisitos previos
- Cuenta de Heroku
- Heroku CLI instalado
- Git configurado

## Pasos para desplegar

### 1. Iniciar sesión en Heroku
```bash
heroku login
```

### 2. Crear la aplicación en Heroku
```bash
heroku create chat-agent-service
```

O si quieres un nombre específico:
```bash
heroku create tu-nombre-agent-service
```

### 3. Configurar las variables de entorno
Necesitas configurar las siguientes variables de entorno en Heroku:

```bash
# Configuración de Supabase
heroku config:set SUPABASE_URL=tu_supabase_url
heroku config:set SUPABASE_SERVICE_ROLE_KEY=tu_service_role_key

# Configuración de Google AI
heroku config:set GEMINI_API_KEY=tu_gemini_api_key

# Configuración del proyecto
heroku config:set PROJECT_NAME="Chat Agent Service"
heroku config:set ENVIRONMENT=production

# Configuración adicional (opcional)
heroku config:set LOG_LEVEL=info
heroku config:set MAX_WORKERS=4
```

### 4. Desplegar la aplicación
```bash
# Si estás en el directorio del proyecto
git push heroku main

# Si estás en un subdirectorio o en un monorepo
git subtree push --prefix=chat_agent_service heroku main
```

### 5. Ver los logs
```bash
heroku logs --tail
```

### 6. Abrir la aplicación
```bash
heroku open
```

## Configuración del Procfile
El archivo `Procfile` ya está configurado con:
```
web: gunicorn main:app -w 4 -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:$PORT
```

Esto usa:
- **Gunicorn** como servidor WSGI para producción
- **4 workers** para manejar múltiples peticiones concurrentes
- **UvicornWorker** para soportar aplicaciones FastAPI/ASGI
- **$PORT** variable de entorno proporcionada por Heroku

## Verificar el despliegue
Visita: `https://tu-app.herokuapp.com/`

Endpoint de health check: `https://tu-app.herokuapp.com/health`

## Troubleshooting

### Ver logs en tiempo real
```bash
heroku logs --tail
```

### Reiniciar la aplicación
```bash
heroku restart
```

### Ver las variables de entorno configuradas
```bash
heroku config
```

### Escalar dynos (si necesitas más recursos)
```bash
heroku ps:scale web=1
```

### Verificar el estado de los dynos
```bash
heroku ps
```

## Consideraciones importantes

### Tamaño del slug
Si el tamaño del slug es demasiado grande, puedes:
1. Agregar archivos innecesarios al `.gitignore`
2. Eliminar archivos de debug (`debug_raw_response_*.txt`)
3. Usar `.slugignore` para excluir archivos del slug

### Optimización de recursos
El plan gratuito de Heroku tiene limitaciones:
- 512 MB de RAM
- El dyno se duerme después de 30 minutos de inactividad
- 550-1000 horas gratuitas por mes

Para mejor rendimiento, considera actualizar al plan Hobby o superior.

## Configuración avanzada

### Agregar un .slugignore (opcional)
Crea un archivo `.slugignore` para excluir archivos del despliegue:
```
*.txt
debug_*.txt
output_reports/
__pycache__/
*.pyc
.git/
.venv/
```

### Ajustar el número de workers
Modifica el Procfile según tus necesidades:
```
# Para más workers (requiere más RAM)
web: gunicorn main:app -w 8 -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:$PORT

# Para menos workers (usa menos RAM)
web: gunicorn main:app -w 2 -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:$PORT
```

## Notas importantes
- El puerto lo asigna Heroku automáticamente a través de la variable `$PORT`
- Asegúrate de que todas las API keys estén configuradas antes de desplegar
- Los archivos en `.gitignore` no se desplegarán
- El directorio `.venv/` no debe incluirse en el repositorio
