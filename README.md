# Chat Agent Service

Este es un servicio independiente para el agente de chat que puede ser desplegado separadamente del backend principal.

## Estructura

- `main.py`: Aplicación FastAPI principal
- `agent_service.py`: Lógica del agente de chat
- `models.py`: Modelos Pydantic para la API
- `config.py`: Configuración del servicio
- `requirements.txt`: Dependencias específicas del servicio

## Instalación

```bash
pip install -r requirements.txt
```

## Ejecución

```bash
uvicorn main:app --host 0.0.0.0 --port 8001
```

## Variables de Entorno

- `GEMINI_API_KEY`: Clave API de Google Gemini
- `SERVICE_HOST`: Host del servicio (default: 0.0.0.0)
- `SERVICE_PORT`: Puerto del servicio (default: 8001)