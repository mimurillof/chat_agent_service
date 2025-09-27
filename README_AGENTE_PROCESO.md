# Proceso del Agente: Generación de Informes de Portafolio

## Descripción General

Este documento detalla el proceso interno del agente `ChatAgentService` para generar informes de análisis de portafolio en formato JSON estructurado, desde la recepción de la solicitud hasta la entrega de la respuesta final.

## Arquitectura del Proceso

### 1. Punto de Entrada: `ejecutar_generacion_informe_portafolio()`

**Ubicación**: `agent_service.py`, línea 232

**Firma del método**:

```python
async def ejecutar_generacion_informe_portafolio(self, req: PortfolioReportRequest) -> Dict[str, Any]
```

**Parámetros de entrada**:

- `req: PortfolioReportRequest`: Objeto Pydantic con:
  - `model_preference`: Preferencia de modelo ("pro" o "flash")
  - `context`: Diccionario con métricas, imágenes y datos adicionales
  - `session_id`: ID de sesión opcional

### 2. Inicialización y Configuración

#### 2.1 Creación/Gestión de Sesión

```python
session_id = req.session_id or self.create_session()
```

- Si no se proporciona `session_id`, crea una nueva sesión
- Registra la actividad en el estado interno del agente

#### 2.2 Selección de Modelo

```python
if req.model_preference:
    model = settings.model_pro if req.model_preference.lower() == "pro" else settings.model_flash
else:
    model = settings.model_pro
```

- **Por defecto**: `gemini-2.5-pro` (modelo más avanzado para análisis financiero)
- **Alternativa**: `gemini-2.5-flash` si se especifica "flash"
- **Configuración**: Modelos definidos en `config.py`

### 3. Construcción del Prompt de Sistema

#### 3.1 Instrucciones Base

El prompt incluye instrucciones críticas para:

- **Formato de salida**: JSON válido únicamente
- **Esquema**: Seguir estrictamente el esquema `Report` de Pydantic
- **Estructura**: Contenido profesional y PDF-ready

#### 3.2 Tipos de Contenido Soportados

```python
• 'header1': Títulos principales
• 'header2': Secciones principales (I., II., III.)
• 'header3': Subsecciones (5.1, 5.2)
• 'paragraph': Texto con estilos (italic, bold, centered, disclaimer)
• 'spacer': Espacios en blanco (height en pixeles)
• 'page_break': Saltos de página
• 'table': Tablas con headers y rows
• 'list': Listas con items formateados
• 'key_value_list': Métricas financieras
• 'image': Gráficos con path, caption, width, height
```

#### 3.3 Requisitos de Análisis

- Resumen ejecutivo con contexto macro
- Métricas de rendimiento detalladas
- Análisis de riesgo y drawdowns
- Comparativas con portafolios optimizados
- Análisis de correlación
- Proyecciones y recomendaciones

### 4. Recopilación de Contexto desde Supabase Storage

#### 4.1 Método: `_gather_storage_context()`

```python
def _gather_storage_context(self) -> Dict[str, Any]
```

**Pasos**:

1. **Listado de archivos**: `_list_supabase_files()`
   - Filtra por extensiones: `.json`, `.md`, `.png`
   - Lista archivos en bucket/prefijo configurado

2. **Lectura de archivos de texto**: `_read_supabase_text_files()`
   - Descarga y parsea archivos JSON
   - Lee archivos Markdown como texto plano
   - Maneja errores de descarga individualmente

3. **Compilación de contexto**:

   ```python
   return {
       "storage": {
           "bucket": self.supabase_bucket,
           "prefix": self.supabase_prefix,
           "images": [...],  # Lista de imágenes PNG
           "json_docs": {...},  # Contenido de archivos JSON
           "markdown_docs": {...}  # Contenido de archivos MD
       }
   }
   ```

#### 4.2 Fusión de Contextos

```python
# Contexto del request + contexto de Storage
merged_ctx = {**req.context, **storage_ctx}
contents.append(types.Content(
    role="user",
    parts=[types.Part.from_text(text=f"CONTEXT_JSON=\n{json.dumps(merged_ctx, ensure_ascii=False)}")]
))
```

### 5. Configuración de la Llamada a Gemini

#### 5.1 Configuración de Generación

```python
config = types.GenerateContentConfig(
    temperature=0.1,  # Baja temperatura para consistencia JSON
    top_p=0.8,
    max_output_tokens=16384,  # Alto límite para informes extensos
    response_mime_type="application/json",
    response_schema=Report,  # Esquema Pydantic para validación
)
```

#### 5.2 Sistema de Fallback de Modelos

```python
models_to_try = [model]
if model == "gemini-2.5-pro":
    models_to_try.extend(["gemini-2.5-flash", "gemini-2.5-flash-lite"])
elif model == "gemini-2.5-flash":
    models_to_try.extend(["gemini-2.5-flash-lite", "gemini-2.0-flash"])
```

**Estrategia de fallback**:

- Intenta modelo preferido primero
- Si hay sobrecarga (503) o error, prueba modelos alternativos
- Garantiza disponibilidad del servicio

### 6. Ejecución de la Llamada a Gemini

#### 6.1 Llamada Asíncrona

```python
resp = await self.client.aio.models.generate_content(
    model=try_model,
    contents=contents,
    config=config,
)
```

#### 6.2 Procesamiento de Respuesta

**Método preferido**: Salida estructurada nativa

```python
if hasattr(resp, "parsed") and resp.parsed:
    parsed_report = resp.parsed
```

**Fallback**: Parseo manual de JSON

```python
elif hasattr(resp, "text") and resp.text:
    # Limpieza y completado automático de JSON
    # Validación con Pydantic Report.model_validate()
    parsed_report = Report.model_validate(parsed_json)
```

### 7. Limpieza y Validación de JSON

#### 7.1 Detección de JSON Truncado

```python
if len(cleaned_text) > 3000 and not cleaned_text.endswith('}'):
    # Contar llaves abiertas vs cerradas
    open_braces = cleaned_text.count('{')
    close_braces = cleaned_text.count('}')
    missing_braces = open_braces - close_braces
```

#### 7.2 Completado Automático

- Remueve líneas incompletas
- Balancea llaves faltantes
- Corrige comas finales problemáticas
- Valida sintaxis JSON

#### 7.3 Validación con Pydantic

```python
parsed_report = Report.model_validate(parsed_json)
```

- Valida estructura contra esquema `Report`
- Asegura tipos de datos correctos
- Valida campos requeridos

### 8. Construcción de la Respuesta Final

#### 8.1 Objeto de Respuesta

```python
response_payload = PortfolioReportResponse(
    report=parsed_report,
    session_id=session_id,
    model_used=successful_model,
    metadata={
        "context_keys": list(req.context.keys()),
        "fallback_model": successful_model if successful_model != model else None,
    },
).model_dump()
```

#### 8.2 Registro en Sesión

```python
summary_added = ChatMessage(
    role=MessageRole.ASSISTANT,
    content="[INFORME_PORTAFOLIO_GENERADO]",
    timestamp=datetime.now().isoformat()
)
self.sessions[session_id]["messages"].append(summary_added.model_dump())
```

### 9. Manejo de Errores y Debugging

#### 9.1 Tipos de Error

- **Sobrecarga de modelo**: Fallback automático
- **JSON malformado**: Limpieza y completado
- **Validación fallida**: Reintento o error descriptivo
- **Conexión Supabase**: Continúa sin contexto adicional

#### 9.2 Debugging Avanzado

```python
# Guardado de respuesta raw para diagnóstico
timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
debug_file = f"debug_raw_response_{timestamp}.txt"
with open(debug_file, 'w', encoding='utf-8') as f:
    f.write(f"MODELO: {successful_model}\n")
    f.write(f"TIMESTAMP: {timestamp}\n")
    f.write(raw_text)
```

### 10. Flujo de Datos Completo

```
1. PortfolioReportRequest
   ↓
2. Selección de modelo + creación de sesión
   ↓
3. Construcción de prompt de sistema
   ↓
4. Recopilación de contexto Supabase
   ↓
5. Fusión de contextos (request + storage)
   ↓
6. Configuración GenerateContentConfig
   ↓
7. Llamada a Gemini con fallback
   ↓
8. Procesamiento de respuesta (parsed/text)
   ↓
9. Limpieza y validación JSON
   ↓
10. Validación Pydantic Report
    ↓
11. Construcción PortfolioReportResponse
    ↓
12. Registro en sesión
    ↓
13. Retorno de respuesta final
```

### 11. Dependencias y Configuración

#### 11.1 Variables de Entorno Requeridas

- `GEMINI_API_KEY` o `GOOGLE_API_KEY`
- `SUPABASE_URL` (opcional)
- `SUPABASE_SERVICE_ROLE_KEY` (opcional)

#### 11.2 Configuración en `config.py`

```python
model_pro = "gemini-2.5-pro"
model_flash = "gemini-2.5-flash"
supabase_bucket = "portfolio-files"
supabase_prefix = ""
```

#### 11.3 Modelos Pydantic

- `PortfolioReportRequest`: Entrada del endpoint
- `Report`: Esquema de salida estructurada
- `ContentItem`: Tipos de contenido del informe
- `PortfolioReportResponse`: Respuesta del servicio

### 12. Métricas de Rendimiento

#### 12.1 Tokens y Límite

- **Máximo output tokens**: 16,384
- **Temperatura**: 0.1 (consistencia JSON)
- **Top-p**: 0.8

#### 12.2 Elementos Típicos del Informe

- **Contenido mínimo**: 50+ elementos
- **Imágenes**: Todas las PNG disponibles
- **Secciones**: 8-12 secciones principales
- **Longitud**: 20,000+ caracteres

### 13. Casos de Uso y Ejemplos

#### 13.1 Caso Básico

```python
request = PortfolioReportRequest(
    model_preference="pro",
    context={
        "metrics": {"retorno": "25%", "riesgo": "15%"},
        "images": [{"bucket": "portfolio-files", "path": "chart.png"}]
    }
)
result = await agent.ejecutar_generacion_informe_portafolio(request)
```

#### 13.2 Contexto Completo de Supabase

- Archivos JSON: Datos de portafolio
- Archivos MD: Análisis adicionales
- Imágenes PNG: Gráficos y visualizaciones

### 14. Puntos de Extensión

#### 14.1 Nuevos Tipos de Contenido

- Extender `ContentItem` en `models.py`
- Actualizar prompt de sistema
- Validar compatibilidad con generador PDF

#### 14.2 Nuevos Modelos Gemini

- Agregar a lista de fallback
- Probar compatibilidad con `response_schema`

#### 14.3 Fuentes de Contexto Adicionales

- APIs financieras externas
- Bases de datos adicionales
- Archivos locales

### 15. Troubleshooting

#### 15.1 Problemas Comunes

- **JSON truncado**: Sistema de completado automático
- **Modelo sobrecargado**: Fallback automático
- **Contexto faltante**: Continúa sin datos Supabase
- **Validación fallida**: Mensajes de error detallados

#### 15.2 Logs de Debug

- Respuestas raw guardadas en archivos
- Información detallada de parsing
- Métricas de rendimiento por modelo

**Nota**: Este proceso garantiza informes de portafolio profesionales, estructurados y listos para conversión PDF, con alta disponibilidad gracias al sistema de fallback de modelos y robustez en el manejo de respuestas JSON.
 
 