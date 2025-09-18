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

## Nueva funcionalidad: Informe de Análisis de Portafolio (JSON estructurado)

Este servicio ahora expone un flujo completo para generar un informe de análisis de portafolio en un único paso, usando salida JSON estrictamente estructurada y lista para ser consumida por un generador de PDF.

- Botón en Frontend → Backend envía orden → FastAPI → Agente → Gemini → JSON estructurado.

### Flujo end-to-end
1. El Frontend dispara la acción (botón) para "generar_informe_portafolio".
2. El Backend llama el endpoint del servicio: `POST /acciones/generar_informe_portafolio`.
3. El agente construye un prompt predefinido de analista financiero senior y llama a Gemini usando `response_mime_type=application/json` y `response_schema=Report` (Pydantic).
4. El servicio devuelve un objeto `PortfolioReportResponse` con el informe en `report` (ya validado) y metadatos.

### Endpoint
- `POST /acciones/generar_informe_portafolio`

Request (JSON):
```json
{
  "model_preference": "pro",
  "context": {
    "images": [
      {"bucket": "portfolio-files", "path": "portfolio_growth.png"},
      {"bucket": "portfolio-files", "path": "drawdown_underwater.png"},
      {"bucket": "portfolio-files", "path": "efficient_frontier.png"},
      {"bucket": "portfolio-files", "path": "matriz_correlacion.png"}
    ],
    "metrics": {
      "retorno_anualizado": "29.45%",
      "volatilidad": "21.47%",
      "sharpe": "1.371",
      "max_drawdown": "-39.90%"
    }
  }
}
```

Response (JSON, resumido):
```json
{
  "report": {
    "fileName": "Informe_Estrategico_Portafolio_2025-09-15.pdf",
    "document": {
      "title": "Informe Estratégico de Portafolio",
      "author": "Autor",
      "subject": "Análisis y Perspectivas"
    },
    "content": [
      {"type": "header1", "text": "Informe Estratégico de Portafolio"},
      {"type": "paragraph", "text": "..."},
      {"type": "image", "path": "portfolio_growth.png", "caption": "Figura 1 ..."}
    ]
  },
  "session_id": "...",
  "model_used": "gemini-2.5-pro",
  "metadata": {"context_keys": ["images", "metrics"]}
}
```

### Esquema de salida (Pydantic)
La respuesta del modelo sigue el esquema `Report` definido en `models.py`:
- `Report.fileName`: nombre sugerido del PDF.
- `Report.document`: metadatos (`title`, `author`, `subject`).
- `Report.content[]`: lista de bloques de contenido heterogéneos (`paragraph`, `header1/2/3`, `table`, `image`, `list`, `key_value_list`, `spacer`, `page_break`, etc.).
  - Para imágenes se puede usar `path` y/o el objeto `supabase` con `bucket`, `path` y `transform` (width/height/quality/resize/format). Esto permite referenciar directamente las imágenes de Supabase mediante su nombre y ruta.

### Referencias a imágenes en Supabase
Pase en `context.images` los pares `{bucket, path}` que el agente puede usar al redactar el informe. El consumidor del JSON (tu generador de PDF) deberá resolver esas rutas a URLs (p. ej., usando Signed URLs) o montar accesos internos. El esquema también soporta `transform` por si decides aplicar transformaciones (calidad, tamaño, formato) aguas abajo.

### Modelos y código relevante
- `models.py`: contiene `Report`, `ContentItem`, `SupabaseImage`, `DocumentMetadata`, y `PortfolioReportRequest/Response`.
- `agent_service.py`: método `ejecutar_generacion_informe_portafolio` que construye el prompt, invoca Gemini con `response_schema=Report`, valida la salida y devuelve `PortfolioReportResponse`.
- `main.py`: endpoint `POST /acciones/generar_informe_portafolio`.

### Variables de entorno adicionales
- `GOOGLE_API_KEY` (alternativa a `GEMINI_API_KEY`).
- `SUPABASE_URL` y `SUPABASE_SERVICE_ROLE_KEY` (opcionales; útiles si deseas resolver/firmar URLs de imágenes desde el backend).

### Dependencias
Ejecuta:
```bash
pip install -r requirements.txt
```
Incluye, entre otras:
- `google-genai` (Structured Output con `response_schema`)
- `supabase` (si luego deseas integrar Signed URLs o lecturas desde Storage)

### Ejemplo con curl
```bash
curl -X POST "http://localhost:8001/acciones/generar_informe_portafolio" \
  -H "Content-Type: application/json" \
  -d '{
    "model_preference": "pro",
    "context": {
      "images": [
        {"bucket": "portfolio-files", "path": "portfolio_growth.png"},
        {"bucket": "portfolio-files", "path": "drawdown_underwater.png"}
      ],
      "metrics": {"retorno_anualizado": "29.45%", "volatilidad": "21.47%"}
    }
  }'
```

### Notas
- El informe es 100% JSON y se ajusta al esquema; no devuelve texto libre.
- Si no pasas `model_preference`, por defecto el agente usa `gemini-2.5-pro` para este flujo.
- La resolución real de imágenes (firmadas/públicas) queda a cargo del consumidor del JSON.