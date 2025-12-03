# -*- coding: utf-8 -*-
"""
Servicio independiente del agente de chat Horizon
Adaptado para funcionar como microservicio separado
"""
import os
import re
import uuid
import traceback
import mimetypes
import base64
import logging
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List, Tuple
import json
from json import JSONDecodeError

from pydantic import BaseModel, ValidationError, Field
import httpx
from config import settings
from models import ChatMessage, MessageRole, PortfolioReportRequest, PortfolioReportResponse, Report, AlertsAnalysisRequest, FutureProjectionsRequest, PerformanceAnalysisRequest, DailyWeeklySummaryRequest

# Configurar logger
logger = logging.getLogger(__name__)

try:
    from google import genai
    from google.genai import types
    
    # Configurar API key
    api_key = settings.get_api_key()
    if not api_key:
        raise ValueError("GEMINI_API_KEY o GOOGLE_API_KEY no configurada")
    
    if not os.getenv("GEMINI_API_KEY"):
        os.environ["GEMINI_API_KEY"] = api_key
    
    # Crear cliente con API key explícita (según tutorial)
    client = genai.Client(api_key=api_key)
    
except Exception as e:
    print(f"❌ Error configurando Gemini: {e}")
    client = None

try:
    from json_repair import repair_json
    _has_json_repair = True
except Exception:
    _has_json_repair = False

# ==========================================
# HERRAMIENTAS DEL AGENTE
# ==========================================

def get_current_datetime() -> Dict[str, str]:
    """
    Función que devuelve la fecha y hora actuales del sistema.
    Esta función es usada por el modelo a través de Function Calling.
    
    Returns:
        Dict con fecha, hora, timezone y formato ISO
    """
    now = datetime.now()
    now_utc = datetime.now(timezone.utc)
    
    return {
        "date": now.strftime("%Y-%m-%d"),
        "time": now.strftime("%H:%M:%S"),
        "datetime": now.strftime("%Y-%m-%d %H:%M:%S"),
        "timezone": "local",
        "iso_format": now.isoformat(),
        "utc_datetime": now_utc.strftime("%Y-%m-%d %H:%M:%S UTC"),
        "utc_iso": now_utc.isoformat(),
        "weekday": now.strftime("%A"),
        "month": now.strftime("%B"),
        "year": now.strftime("%Y"),
    }


# Declaración de la función para Function Calling
GET_DATETIME_DECLARATION = types.FunctionDeclaration(
    name="get_current_datetime",
    description="Obtiene la fecha y hora actuales del sistema. Usa esta función cuando necesites saber qué día es hoy, qué hora es ahora, o cualquier información temporal actual.",
    parameters={
        "type": "object",
        "properties": {},  # No requiere parámetros
        "required": []
    }
)

# Herramienta de selección de archivos (basada en gemini_supabase/main.py)
FILE_SELECTION_TOOL = types.Tool(
    function_declarations=[
        types.FunctionDeclaration(
            name="SelectorDeArchivos",
            description="Herramienta para seleccionar la lista de archivos más relevantes de Supabase.",
            parameters={
                "type": "object",
                "properties": {
                    "archivos_a_analizar": {
                        "type": "array",
                        "description": "Lista de los IDs y nombres de los archivos que el modelo ha determinado que son cruciales para responder la pregunta.",
                        "items": {
                            "type": "object",
                            "properties": {
                                "id_archivo": {
                                    "type": "string",
                                    "description": "El ID único del archivo (ej. 'rep_Q4') que debe ser analizado."
                                },
                                "nombre_archivo": {
                                    "type": "string",
                                    "description": "El nombre completo del archivo (ej. 'reporte_ventas_Q4.pdf')."
                                }
                            },
                            "required": ["id_archivo", "nombre_archivo"]
                        }
                    }
                },
                "required": ["archivos_a_analizar"]
            }
        )
    ]
)

# Prompts del sistema
FLASH_SYSTEM_PROMPT = """
Eres un asistente financiero rápido y eficiente especializado en:
- Consultas generales del mercado y definiciones financieras
- Búsquedas web de información actualizada mediante Google Search
- Análisis de contenido de URLs específicas
- Obtener información temporal actual (fecha y hora)
- Resúmenes concisos y respuestas directas

HERRAMIENTAS DISPONIBLES:
1. **Google Search**: Úsala cuando necesites información actual sobre precios, noticias, eventos recientes o datos que puedan haber cambiado recientemente.
2. **URL Context**: Úsala cuando el usuario proporcione URLs específicas para analizar.
3. **get_current_datetime**: Úsala cuando necesites saber la fecha u hora actual.

Utiliza las herramientas de manera inteligente y solo cuando sea necesario. Proporciona respuestas precisas y útiles.
"""

PRO_SYSTEM_PROMPT = """
Eres un analista financiero experto especializado en análisis profundo de documentos.
- Analiza documentos financieros con detalle crítico
- Identifica riesgos, oportunidades y patrones
- Proporciona insights accionables y fundamentados
- Mantén una perspectiva crítica y objetiva

HERRAMIENTAS DISPONIBLES:
1. **URL Context**: Para analizar URLs específicas proporcionadas por el usuario.
2. **get_current_datetime**: Para obtener información temporal actual.

Enfócate en la calidad del análisis sobre la velocidad.
"""

class ArchivoSeleccionado(BaseModel):
    """Representa un archivo seleccionado para análisis."""

    id_archivo: str = Field(..., description="Identificador único dentro del bucket")
    nombre_archivo: str = Field(..., description="Nombre del archivo")


class SelectorDeArchivos(BaseModel):
    """Esquema de tool calling para seleccionar archivos relevantes."""

    archivos_a_analizar: List[ArchivoSeleccionado] = Field(
        ..., description="Listado de archivos que el modelo necesita para responder"
    )


def _build_tool_from_schema(schema: BaseModel) -> types.Tool:
    parameters_schema = {
        "type": "object",
        "properties": {
            "archivos_a_analizar": {
                "type": "array",
                "description": schema.model_fields["archivos_a_analizar"].description,
                "items": {
                    "type": "object",
                    "properties": {
                        "id_archivo": {
                            "type": "string",
                            "description": ArchivoSeleccionado.model_fields["id_archivo"].description,
                        },
                        "nombre_archivo": {
                            "type": "string",
                            "description": ArchivoSeleccionado.model_fields["nombre_archivo"].description,
                        },
                    },
                    "required": ["id_archivo", "nombre_archivo"],
                },
            }
        },
        "required": ["archivos_a_analizar"],
    }

    return types.Tool(
        function_declarations=[
            types.FunctionDeclaration(
                name=schema.__name__,
                description=schema.__doc__,
                parameters=parameters_schema,
            )
        ]
    )


FILE_SELECTION_TOOL = _build_tool_from_schema(SelectorDeArchivos)


class ChatAgentService:
    """Servicio independiente del agente de chat"""
    
    def __init__(self):
        self.client = client
        self.sessions: Dict[str, Dict] = {}
        self.active_sessions = 0
        self.http_client = httpx.AsyncClient(timeout=30.0)
        self._backend_base_url = settings.get_backend_url().rstrip("/")
        self.supabase = None
        
        if not self.client:
            raise Exception("Cliente Gemini no disponible")
        
        self.supabase_bucket = settings.supabase_bucket_name or "portfolio-files"
        
        # ✅ Ya no usamos prefijos hardcodeados, ahora usamos user_id dinámicamente
    
    def get_health_status(self) -> Dict[str, Any]:
        """Obtener estado del servicio"""
        return {
            "status": "healthy" if self.client else "unhealthy",
            "service": settings.service_name,
            "version": settings.service_version,
            "models_available": [settings.model_flash, settings.model_pro],
            "active_sessions": self.active_sessions,
            "capabilities": [
                "financial_analysis",
                "google_search_grounding",  # ✅ Nuevo
                "url_context_analysis",     # ✅ Nuevo
                "function_calling",          # ✅ Nuevo
                "real_time_datetime",        # ✅ Nuevo
                "web_search", 
                "url_analysis",
                "document_analysis",
                "citation_generation"        # ✅ Nuevo
            ],
            "tools": [
                {
                    "name": "google_search",
                    "description": "Búsqueda en Google para información actualizada",
                    "enabled": True
                },
                {
                    "name": "url_context",
                    "description": "Análisis de contenido de URLs específicas",
                    "enabled": True
                },
                {
                    "name": "get_current_datetime",
                    "description": "Obtener fecha y hora actuales del sistema",
                    "enabled": True
                }
            ]
        }
    
    def create_session(self) -> str:
        """Crear nueva sesión de chat"""
        session_id = str(uuid.uuid4())
        self.sessions[session_id] = {
            "id": session_id,
            "created_at": datetime.now().isoformat(),
            "messages": [],
            "model_used": settings.model_flash,
            "last_activity": datetime.now().isoformat()
        }
        self.active_sessions += 1
        return session_id
    
    def get_session_info(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Obtener información de sesión"""
        session = self.sessions.get(session_id)
        if not session:
            return None
        
        return {
            "session_id": session_id,
            "created_at": session["created_at"],
            "message_count": len(session["messages"]),
            "model_used": session["model_used"],
            "last_activity": session["last_activity"]
        }
    
    def _choose_model_and_tools(self, query: str, file_path: Optional[str] = None, url: Optional[str] = None) -> tuple:
        """
        Elegir modelo y herramientas basado en el tipo de consulta.
        
        IMPORTANTE: NO se pueden mezclar Function Calling con Grounding Tools (Google Search, URL Context)
        en la misma llamada según la API de Gemini.
        
        Returns:
            tuple: (model_name, list_of_tool_objects, list_of_tool_names)
        """
        tools = []
        tool_names = []
        
        # Si hay archivo local, usar Pro para análisis profundo
        if file_path:
            # Pro con URL Context (sin function calling)
            url_context_tool = types.Tool(url_context=types.UrlContext())
            tools.append(url_context_tool)
            tool_names.append("url_context")
            return settings.model_pro, tools, tool_names
        
        # Si hay URL explícita, agregar URL Context (sin function calling)
        if url:
            url_context_tool = types.Tool(url_context=types.UrlContext())
            tools.append(url_context_tool)
            tool_names.append("url_context")
            return settings.model_flash, tools, tool_names
        
        # Si necesita búsqueda web, agregar Google Search (sin function calling)
        if self._needs_web_search(query):
            google_search_tool = types.Tool(google_search=types.GoogleSearch())
            tools.append(google_search_tool)
            tool_names.append("google_search")
            return settings.model_flash, tools, tool_names
        
        # Si necesita información temporal, usar SOLO function calling
        if self._needs_datetime(query):
            datetime_tool = types.Tool(function_declarations=[GET_DATETIME_DECLARATION])
            tools.append(datetime_tool)
            tool_names.append("get_current_datetime")
            return settings.model_flash, tools, tool_names
        
        # Para consultas generales, NO usar herramientas
        return settings.model_flash, tools, tool_names
    
    def _needs_web_search(self, query: str) -> bool:
        """
        Determinar si la consulta necesita búsqueda web.
        Detecta keywords que indican necesidad de información actualizada.
        """
        web_keywords = [
            # Español
            "precio actual", "cotización", "últimas noticias",
            "precio de", "valor actual", "mercado actual", "tendencia actual",
            "noticias de", "actualización", "estado actual", "reciente",
            "últimas", "actual", "en este momento",
            "cotiza", "vale", "cuesta", "subió", "bajó", "cayó",
            "noticias", "hoy", "eventos", "sucedido", "acontecido",
            # Inglés
            "latest news", "current price", "stock price", "today",
            "what happened", "recent", "latest", "news about",
            "current", "now", "breaking news", "update on",
            "price of", "market", "trending", "happened today"
        ]
        query_lower = query.lower()
        return any(keyword in query_lower for keyword in web_keywords)
    
    def _needs_datetime(self, query: str) -> bool:
        """
        Determinar si la consulta necesita información de fecha/hora.
        Solo retorna True si NO necesita búsqueda web (para evitar conflictos).
        """
        # No usar datetime si ya necesita web search
        if self._needs_web_search(query):
            return False
        
        # Keywords que indican solo fecha/hora sin búsqueda
        datetime_keywords = [
            "qué hora es", "qué día es", "fecha actual", "hora actual",
            "qué fecha es", "hora es ahora", "día de la semana",
            "cuándo es", "mes actual", "año actual"
        ]
        query_lower = query.lower()
        return any(keyword in query_lower for keyword in datetime_keywords)
    
    def _extract_urls_from_query(self, query: str) -> List[str]:
        """Extraer URLs del mensaje del usuario"""
        # Patrón para detectar URLs
        url_pattern = r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+'
        urls = re.findall(url_pattern, query)
        return urls
    
    def _add_citations_to_text(self, text: str, grounding_metadata) -> str:
        """
        Agregar citaciones en línea al texto basado en groundingMetadata.
        Implementación basada en el tutorial.md
        """
        if not grounding_metadata:
            return text
        
        try:
            supports = grounding_metadata.grounding_supports
            chunks = grounding_metadata.grounding_chunks
            
            if not supports or not chunks:
                return text
            
            # Ordenar supports por end_index en orden descendente para evitar problemas de desplazamiento
            sorted_supports = sorted(supports, key=lambda s: s.segment.end_index, reverse=True)
            
            for support in sorted_supports:
                end_index = support.segment.end_index
                if support.grounding_chunk_indices:
                    # Crear string de citación como [1](link1), [2](link2)
                    citation_links = []
                    for i in support.grounding_chunk_indices:
                        if i < len(chunks):
                            uri = chunks[i].web.uri
                            citation_links.append(f"[{i + 1}]({uri})")
                    citation_string = " " + ", ".join(citation_links)
                    text = text[:end_index] + citation_string + text[end_index:]
            
            return text
        except Exception as e:
            print(f"⚠️ Error agregando citaciones: {e}")
            return text
    
    # =====================
    # Informe de análisis de portafolio
    # =====================
    async def _close(self) -> None:
        try:
            await self.http_client.aclose()
        except Exception:
            pass

    async def _backend_list_files(
        self,
        user_id: str,
        auth_token: Optional[str],
        extensions: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        if not auth_token:
            return []

        ext_param = ",".join(extensions) if extensions else None
        headers = {"Authorization": f"Bearer {auth_token}"}
        url = f"{self._backend_base_url}/api/storage/files"

        try:
            response = await self.http_client.get(
                url,
                params={"extensions": ext_param, "limit": 100},
                headers=headers,
            )
            response.raise_for_status()
            payload = response.json()
            files = payload.get("files")
            if not isinstance(files, list):
                return []
            normalized: List[Dict[str, Any]] = []
            for item in files:
                name = item.get("name")
                if not name:
                    continue
                normalized.append({
                    "name": name,
                    "user_id": user_id,
                    "ext": f".{item.get('ext', '').lower()}" if item.get("ext") else None,
                    "path": item.get("full_path"),
                    "size": item.get("size"),
                    "updated_at": item.get("updated_at"),
                })
            return normalized
        except httpx.HTTPStatusError as exc:
            status_code = exc.response.status_code
            if status_code == 401:
                raise HTTPException(status_code=401, detail="Token inválido para acceso a storage") from exc
            print(f"⚠️ Error HTTP listando archivos de backend: {exc}")
            return []
        except Exception as exc:
            print(f"⚠️ Error listando archivos vía backend: {exc}")
            return []

    async def _backend_download_file(
        self,
        user_id: str,
        filename: str,
        auth_token: Optional[str],
    ) -> Tuple[bytes, str]:
        if not auth_token:
            raise PermissionError("Se requiere token de autenticación para descargar archivos")

        headers = {"Authorization": f"Bearer {auth_token}"}
        url = f"{self._backend_base_url}/api/storage/download"

        try:
            response = await self.http_client.get(
                url,
                params={"filename": filename},
                headers=headers,
            )
            response.raise_for_status()
            content_type = response.headers.get("content-type", "application/octet-stream")
            return response.content, content_type
        except httpx.HTTPStatusError as exc:
            status_code = exc.response.status_code
            if status_code == 404:
                raise FileNotFoundError(f"Archivo {filename} no encontrado para el usuario") from exc
            if status_code == 401:
                raise PermissionError("Token inválido o expirado") from exc
            raise

    async def _backend_upload_json(
        self,
        user_id: str,
        filename: str,
        data: Dict[str, Any],
        auth_token: Optional[str],
    ) -> Dict[str, Any]:
        """
        Sube un archivo JSON al bucket del usuario vía el backend.
        
        Args:
            user_id: ID del usuario
            filename: Nombre del archivo (debe terminar en .json)
            data: Diccionario con los datos a guardar
            auth_token: Token de autenticación
            
        Returns:
            Dict con el resultado de la operación
        """
        if not auth_token:
            raise PermissionError("Se requiere token de autenticación para subir archivos")

        headers = {
            "Authorization": f"Bearer {auth_token}",
            "Content-Type": "application/json"
        }
        url = f"{self._backend_base_url}/api/storage/save-json"

        try:
            response = await self.http_client.post(
                url,
                json={"filename": filename, "data": data},
                headers=headers,
                timeout=30.0,
            )
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as exc:
            status_code = exc.response.status_code
            error_detail = exc.response.text
            logger.error(f"Error HTTP {status_code} al subir {filename}: {error_detail}")
            if status_code == 401:
                raise PermissionError("Token inválido o expirado") from exc
            raise Exception(f"Error al subir archivo: {status_code} - {error_detail}") from exc
        except Exception as exc:
            logger.error(f"Error al subir archivo {filename}: {exc}")
            raise

    async def _gather_storage_context(self, user_id: str, auth_token: Optional[str]) -> Dict[str, Any]:
        """Compila contexto desde el backend: JSON/MD/PDF + imágenes."""
        files = await self._backend_list_files(
            user_id=user_id,
            auth_token=auth_token,
            extensions=["json", "md", "png", "jpg", "jpeg", "pdf"],
        )

        json_docs: Dict[str, Any] = {}
        markdown_docs: Dict[str, str] = {}
        images: List[Dict[str, Any]] = []
        pdfs: List[Dict[str, Any]] = []

        for file_info in files:
            name = file_info.get("name")
            ext = (file_info.get("ext") or "").lower()
            if not name or not ext:
                continue

            # Manejar imágenes
            if ext in {".png", ".jpg", ".jpeg", ".gif", ".webp"}:
                images.append({
                    "bucket": self.supabase_bucket,
                    "path": file_info.get("path") or f"{user_id}/{name}",
                })
                continue

            # Manejar PDFs como referencias
            if ext == ".pdf":
                pdfs.append({
                    "bucket": self.supabase_bucket,
                    "path": file_info.get("path") or f"{user_id}/{name}",
                    "name": name,
                })
                continue

            if ext not in {".json", ".md"}:
                continue

            try:
                file_bytes, content_type = await self._backend_download_file(
                    user_id=user_id,
                    filename=name,
                    auth_token=auth_token,
                )
            except Exception as exc:
                print(f"⚠️ No se pudo descargar {name}: {exc}")
                continue

            text = file_bytes.decode("utf-8", errors="replace") if isinstance(file_bytes, (bytes, bytearray)) else str(file_bytes)

            if ext == ".json":
                try:
                    json_docs[name] = json.loads(text)
                except Exception:
                    json_docs[name] = {"_raw": text}
            else:
                markdown_docs[name] = text

        if not json_docs and not markdown_docs and not images and not pdfs:
            return {}

        return {
            "storage": {
                "bucket": self.supabase_bucket,
                "user_id": user_id,
                "images": images,
                "pdfs": pdfs,
                "json_docs": json_docs,
                "markdown_docs": markdown_docs,
            }
        }

    async def _process_portfolio_query(
        self,
        message: str,
        user_id: str,
        model: str,
        conversation_history: List,
        tools: List,
        auth_token: Optional[str],
        session: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        """
        Procesa consultas de portafolio usando el flujo de selección de archivos + análisis inline.
        Basado en el ejemplo gemini_supabase/main.py
        """
        try:
            print(f"\n🔍 Detectada consulta de portafolio para usuario {user_id}")
            
            # Paso 1: Listar archivos disponibles del usuario (incluyendo imágenes y PDFs)
            files = await self._backend_list_files(
                user_id=user_id,
                auth_token=auth_token,
                extensions=["json", "md", "png", "jpg", "jpeg", "gif", "webp", "pdf"],
            )
            
            if not files:
                print("⚠️ No se encontraron archivos para el usuario")
                return None
            
            # Filtrar archivos no deseados (similar al ejemplo)
            excluded_extensions = ('.html', '-.emptyFolder', '.gitkeep')
            filtered_files = [
                f for f in files 
                if not any(f.get("name", "").endswith(ext) for ext in excluded_extensions)
            ]
            
            if not filtered_files:
                print("⚠️ No hay archivos relevantes después del filtrado")
                return None
            
            print(f"📁 Encontrados {len(filtered_files)} archivos relevantes")
            
            # Paso 2: Gemini selecciona los archivos necesarios (Function Calling)
            selected_files = await self._select_files_via_gemini(message, filtered_files, model)
            
            if not selected_files:
                print("⚠️ Gemini no seleccionó archivos para el análisis")
                return None
            
            print(f"✅ Gemini seleccionó {len(selected_files)} archivo(s)")
            
            # Paso 3: Descargar y analizar archivos inline
            response_text = await self._analyze_files_inline(
                message=message,
                selected_files=selected_files,
                user_id=user_id,
                auth_token=auth_token,
                model=model,
            )
            
            if not response_text:
                print("⚠️ No se pudo generar respuesta del análisis")
                return None
            
            return {
                "text": response_text,
                "grounding_metadata": None,
                "function_calls": [{"name": "portfolio_file_analysis", "files": len(selected_files)}],
            }
            
        except Exception as exc:
            print(f"❌ Error en _process_portfolio_query: {exc}")
            traceback.print_exc()
            return None
    
    async def _select_files_via_gemini(
        self,
        prompt: str,
        files_metadata: List[Dict[str, Any]],
        model: str,
    ) -> List[Dict[str, Any]]:
        """
        Usa Gemini Function Calling para seleccionar archivos relevantes.
        Basado en paso_1_decision del ejemplo.
        LÍMITE: Máximo 10 archivos para evitar timeouts.
        """
        try:
            # Preparar metadatos en formato legible
            formatted_metadata = []
            for f in files_metadata:
                formatted_metadata.append({
                    "nombre": f.get("name"),
                    "id_archivo": f.get("name"),  # Usar nombre como ID
                    "tipo": f.get("ext", "").lstrip(".").upper(),
                    "tamaño_MB": round(f.get("size", 0) / (1024 * 1024), 2) if f.get("size") else 0,
                })
            
            metadatos_str = json.dumps(formatted_metadata, indent=2, ensure_ascii=False)
            
            decision_prompt = f"""
El usuario ha proporcionado el siguiente prompt: '{prompt}'.

A continuación, se presenta una lista de archivos disponibles en Supabase con sus metadatos:
--- ARCHIVOS DISPONIBLES ---
{metadatos_str}
--- FIN DE ARCHIVOS DISPONIBLES ---

IMPORTANTE: Selecciona MÁXIMO 10 archivos relevantes para responder la consulta:
1. Archivos JSON: Contienen datos estructurados de análisis
2. Archivos MD (Markdown): Contienen resúmenes y narrativas
3. Imágenes (PNG/JPG/JPEG/GIF/WEBP): Gráficos, visualizaciones y diagramas
4. Archivos PDF: Documentos completos, reportes generados

REGLAS ESPECIALES:
- Si el usuario menciona "reporte", "informe" o "documento": PRIORIZA archivos PDF e json y md e imágenes.

DEBES utilizar la función 'SelectorDeArchivos' para devolver la lista de archivos ESENCIALES (máximo 10).
"""
            
            # Usar el tool de selección de archivos
            response = await self.client.aio.models.generate_content(
                model=model,
                contents=[decision_prompt],
                config=types.GenerateContentConfig(
                    tools=[FILE_SELECTION_TOOL],
                    tool_config=types.ToolConfig(
                        function_calling_config=types.FunctionCallingConfig(mode="ANY")
                    )
                )
            )
            
            if response.function_calls:
                call = response.function_calls[0]
                call_args = call.args or {}
                archivos_seleccionados = call_args.get('archivos_a_analizar', [])
                
                # Forzar límite de archivos para evitar timeout
                MAX_FILES = 10
                
                # Detectar si el usuario menciona "reporte" para priorizar PDFs e imágenes
                is_report_query = any(word in prompt.lower() for word in ['reporte', 'informe', 'report', 'documento'])
                
                if is_report_query:
                    # Para reportes: más PDFs e imágenes
                    MAX_JSON = 3
                    MAX_MD = 3
                    MAX_IMAGES = 2
                    MAX_PDF = 2
                else:
                    # Para análisis general: más datos estructurados
                    MAX_JSON = 4
                    MAX_MD = 3
                    MAX_IMAGES = 2
                    MAX_PDF = 1
                
                if len(archivos_seleccionados) > MAX_FILES:
                    print(f"⚠️ Gemini seleccionó {len(archivos_seleccionados)} archivos, limitando a {MAX_FILES}")
                    
                    # Clasificar archivos por tipo
                    json_files = [f for f in archivos_seleccionados if f.get('nombre_archivo', '').lower().endswith('.json')]
                    md_files = [f for f in archivos_seleccionados if f.get('nombre_archivo', '').lower().endswith('.md')]
                    image_files = [f for f in archivos_seleccionados if f.get('nombre_archivo', '').lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.webp'))]
                    pdf_files = [f for f in archivos_seleccionados if f.get('nombre_archivo', '').lower().endswith('.pdf')]
                    
                    # Combinar con prioridad según el tipo de consulta
                    if is_report_query:
                        # Para reportes: priorizar PDFs e imágenes
                        archivos_seleccionados = (
                            pdf_files[:MAX_PDF] + 
                            image_files[:MAX_IMAGES] + 
                            json_files[:MAX_JSON] + 
                            md_files[:MAX_MD]
                        )
                    else:
                        # Para análisis: priorizar datos
                        archivos_seleccionados = (
                            json_files[:MAX_JSON] + 
                            md_files[:MAX_MD] + 
                            image_files[:MAX_IMAGES] + 
                            pdf_files[:MAX_PDF]
                        )
                    archivos_seleccionados = archivos_seleccionados[:MAX_FILES]
                
                print(f"📋 Gemini seleccionó {len(archivos_seleccionados)} archivo(s) para análisis:")
                for arch in archivos_seleccionados:
                    print(f"  - {arch.get('nombre_archivo')}")
                
                return archivos_seleccionados
            else:
                print("⚠️ Gemini no devolvió llamada a función")
                return []
                
        except Exception as exc:
            print(f"❌ Error en _select_files_via_gemini: {exc}")
            return []
    
    async def _analyze_files_inline(
        self,
        message: str,
        selected_files: List[Dict[str, Any]],
        user_id: str,
        auth_token: Optional[str],
        model: str,
    ) -> Optional[str]:
        """
        Descarga archivos seleccionados y los envía inline a Gemini para análisis.
        Basado en paso_2_analisis_inline del ejemplo.
        """
        try:
            inline_parts = []
            total_size_bytes = 0
            
            for item in selected_files:
                file_name = item.get('nombre_archivo')
                if not file_name:
                    continue
                
                try:
                    # Descargar archivo vía backend
                    file_bytes, content_type = await self._backend_download_file(
                        user_id=user_id,
                        filename=file_name,
                        auth_token=auth_token,
                    )
                    
                    # Determinar mime type
                    mime_type, _ = mimetypes.guess_type(file_name)
                    if mime_type is None:
                        mime_type = content_type or 'application/octet-stream'
                    
                    # Rastrear tamaño
                    file_size = len(file_bytes)
                    total_size_bytes += file_size
                    size_mb = file_size / (1024 * 1024)
                    
                    # Agregar como parte inline
                    if file_name.lower().endswith('.json'):
                        json_content = file_bytes.decode('utf-8')
                        inline_parts.append(json_content)
                        print(f"   ✅ Añadido JSON: {file_name} ({size_mb:.2f} MB)")
                    elif file_name.lower().endswith('.md'):
                        md_content = file_bytes.decode('utf-8')
                        inline_parts.append(md_content)
                        print(f"   ✅ Añadido MD: {file_name} ({size_mb:.2f} MB)")
                    else:
                        inline_parts.append(
                            types.Part.from_bytes(
                                data=file_bytes,
                                mime_type=mime_type,
                            )
                        )
                        print(f"   ✅ Añadido imagen: {file_name} ({size_mb:.2f} MB, {mime_type})")
                        
                except Exception as exc:
                    print(f"⚠️ Error procesando {file_name}: {exc}")
                    continue
            
            if not inline_parts:
                print("❌ No se pudo procesar ningún archivo")
                return None
            
            # Agregar el prompt del usuario
            final_contents = inline_parts + [message]
            
            total_size_mb = total_size_bytes / (1024 * 1024)
            print(f"\n📤 Enviando {len(final_contents)} elementos a Gemini ({total_size_mb:.2f} MB total)...")
            
            # Generar respuesta usando STREAMING para evitar timeout
            try:
                # Usar generate_content_stream para recibir respuesta de forma incremental
                response_stream = await self.client.aio.models.generate_content_stream(
                    model=model,
                    contents=final_contents
                )
                
                # Recolectar todos los chunks de la respuesta
                full_text = ""
                chunk_count = 0
                
                async for chunk in response_stream:
                    chunk_count += 1
                    if hasattr(chunk, 'text') and chunk.text:
                        full_text += chunk.text
                        # Log cada 5 chunks para no saturar logs
                        if chunk_count % 5 == 0:
                            print(f"   📝 Recibidos {chunk_count} chunks de Gemini...")
                
                if full_text:
                    print(f"✅ Análisis completado exitosamente ({chunk_count} chunks, {len(full_text)} caracteres)")
                    return full_text
                else:
                    print("⚠️ Respuesta sin texto después del streaming")
                    return None
                    
            except Exception as exc:
                error_msg = str(exc)
                if "503" in error_msg or "UNAVAILABLE" in error_msg:
                    print(f"⚠️ Modelo Gemini no disponible (503). Intenta de nuevo en unos momentos.")
                elif "timeout" in error_msg.lower():
                    print(f"⚠️ Timeout procesando archivos. Considera reducir el número de imágenes.")
                else:
                    print(f"❌ Error llamando a Gemini: {error_msg}")
                return None
            
        except Exception as exc:
            print(f"❌ Error en _analyze_files_inline: {exc}")
            traceback.print_exc()
            return None

    def _persist_raw_response(self, model_name: str, raw_text: str) -> Optional[str]:
        """Guarda la respuesta raw en disco para depuración y retorna la ruta."""
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        debug_file = f"debug_raw_response_{timestamp}.txt"
        try:
            with open(debug_file, 'w', encoding='utf-8') as f:
                f.write(f"MODELO: {model_name}\n")
                f.write(f"TIMESTAMP: {timestamp}\n")
                f.write("=" * 60 + "\n")
                f.write(raw_text)
            print(f"💾 Respuesta raw guardada en: {debug_file}")
            return debug_file
        except Exception as save_error:
            print(f"⚠️ No se pudo guardar la respuesta raw para depuración: {save_error}")
            return None

    def _extract_json_candidate(self, raw_text: str) -> Optional[str]:
        """Extrae el bloque de JSON más probable desde la respuesta raw."""
        if not raw_text:
            return None

        text = raw_text.strip()

        # Quitar bloques de código tipo ```json ... ```
        fence_match = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.DOTALL)
        if fence_match:
            return fence_match.group(1).strip()

        first_brace = text.find('{')
        if first_brace == -1:
            return None

        last_brace = text.rfind('}')
        if last_brace == -1 or last_brace < first_brace:
            return text[first_brace:].strip()

        return text[first_brace:last_brace + 1].strip()

    def _parse_report_from_text(self, raw_text: str, model_name: str) -> Optional[Report]:
        """Intenta parsear el JSON del modelo aplicando reparaciones progresivas."""
        self._persist_raw_response(model_name, raw_text)

        candidate = self._extract_json_candidate(raw_text)
        if not candidate:
            print("⚠️ No se encontró un bloque JSON claro en la respuesta del modelo.")
            return None

        attempts: List[Dict[str, str]] = []

        def enqueue(text: str, reason: str):
            normalized = text.strip()
            if not normalized:
                return
            if any(entry["text"] == normalized for entry in attempts):
                return
            attempts.append({"text": normalized, "reason": reason})

        enqueue(candidate, "respuesta original")

        # Intentar quitar bloque de cierre de code fence residual
        if candidate.endswith("```"):
            trimmed = candidate[:candidate.rfind("```")].strip()
            enqueue(trimmed, "remover cierre ```")

        # Intentar quitar coma final
        if candidate.rstrip().endswith(','):
            enqueue(candidate.rstrip(', \n\t'), "eliminar coma final")

        # Balancear llaves si faltan
        brace_diff = candidate.count('{') - candidate.count('}')
        if brace_diff > 0:
            enqueue(candidate + ('}' * brace_diff), f"balancear llaves (+{brace_diff})")
        elif brace_diff < 0:
            trimmed = candidate
            diff = brace_diff
            while diff < 0 and trimmed.endswith('}'):
                trimmed = trimmed[:-1]
                diff += 1
            enqueue(trimmed, f"remover llaves sobrantes ({abs(brace_diff)})")

        last_error: Optional[Exception] = None
        idx = 0

        while idx < len(attempts):
            attempt = attempts[idx]
            attempt_text = attempt["text"]
            reason = attempt["reason"]
            try:
                parsed_json = json.loads(attempt_text)
                report = Report.model_validate(parsed_json)
                if reason == "respuesta original":
                    print("✅ JSON parseado correctamente sin reparaciones adicionales")
                else:
                    print(f"✅ JSON parseado tras ajuste: {reason}")
                return report
            except JSONDecodeError as json_error:
                last_error = json_error
                print(f"⚠️ JSONDecodeError ({reason}): {json_error}")

                if _has_json_repair:
                    try:
                        repaired = repair_json(attempt_text)
                        enqueue(repaired, f"json_repair ({reason})")
                    except Exception as repair_error:
                        print(f"⚠️ json_repair no logró reparar el JSON ({reason}): {repair_error}")
                else:
                    print("⚠️ json_repair no está disponible para intentos de reparación automática")

                # Intentar ajustes adicionales específicos de este intento
                if attempt_text.rstrip().endswith(','):
                    enqueue(attempt_text.rstrip(', \n\t'), f"eliminar coma final ({reason})")

                brace_diff_attempt = attempt_text.count('{') - attempt_text.count('}')
                if brace_diff_attempt > 0:
                    enqueue(attempt_text + ('}' * brace_diff_attempt), f"balancear llaves (+{brace_diff_attempt}) ({reason})")

                idx += 1
            except ValidationError as validation_error:
                last_error = validation_error
                print(f"⚠️ Validación Pydantic falló ({reason}): {validation_error}")
                idx += 1
            except Exception as unexpected_error:
                last_error = unexpected_error
                print(f"⚠️ Error inesperado intentando parsear JSON ({reason}): {unexpected_error}")
                idx += 1

        if last_error:
            print(f"❌ No se pudo reparar la respuesta JSON: {last_error}")
        else:
            print("❌ No se logró parsear la respuesta JSON por motivos desconocidos")
        return None

    async def ejecutar_generacion_informe_portafolio(self, req: PortfolioReportRequest) -> Dict[str, Any]:
        """Construye prompt y genera un informe de portafolio en JSON usando el esquema Report."""
        session_id = req.session_id or self.create_session()
        user_id = req.user_id  # ✅ Obtener user_id del request
        
        # Por defecto, usar PRO para análisis profundo salvo que se indique lo contrario
        if req.model_preference:
            model = settings.model_pro if req.model_preference.lower() == "pro" else settings.model_flash
        else:
            model = settings.model_pro

        instruction = (
            "# PROMPT MAESTRO PARA AGENTE DE ANÁLISIS FINANCIERO\n\n"
            "## 1. PERSONA Y ROL\n"
            "Actúa como un Analista Financiero Cuantitativo Senior y Estratega de Carteras de Inversión con más de 20 años en Goldman Sachs. "
            "Eres meticuloso, objetivo y comunicas hallazgos con rigor institucional. Tu responsabilidad es sintetizar datos cuantitativos, narrativas cualitativas "
            "y señales visuales en un diagnóstico integral y accionable del portafolio.\n\n"

            "## 2. DIRECTIVA PRINCIPAL\n"
            "Elabora un INFORME DE ANÁLISIS DE CARTERA COMPLETO, profundo y profesional que será convertido automáticamente a PDF. "
            "Debes interpretar métricas, tablas y cada imagen disponible (graficos descargados desde Supabase) con criterios cuantitativos, "
            "contexto macroeconómico y riesgos prospectivos. Contrasta hallazgos individuales y combinados para extraer conclusiones estratégicas.\n\n"

            "## 3. PROTOCOLO DE RESPUESTA\n"
            "1. RESPONDE ÚNICAMENTE con JSON válido que siga estrictamente el esquema Report.\n"
            "2. No añadas texto fuera del JSON, ni comentarios, ni bloques markdown.\n"
            "3. Escapa apropiadamente cada cadena y garantiza que todas las llaves estén cerradas.\n"
            "4. Usa nombres de archivo de imágenes sin prefijos (ej: 'portfolio_growth.png').\n"
            "5. Conserva la relación de aspecto 16:9 en todas las imágenes fijando height = width * 9 / 16 (usa width en pulgadas, p.ej. 6.0 => height 3.375).\n"
            "6. Si algún dato no está disponible, explícitalo en el cuerpo del informe en lugar de inventarlo.\n\n"

            "## 4. ESTRUCTURA DEL INFORME\n"
            "- fileName: Nombre profesional con extensión .pdf.\n"
            "- document: { title, author='Horizon Agent', subject }.\n"
            "- content: Usa la siguiente gramática en orden lógico con secciones numeradas (I., II., III., ...).\n"
            "  • header1: título principal.\n"
            "  • header2/header3: secciones y subsecciones jerarquizadas.\n"
            "  • paragraph: narrativa (styles permitidos: body, italic, bold, centered, disclaimer).\n"
            "  • spacer: separadores (height en puntos).\n"
            "  • page_break: saltos de página.\n"
            "  • table: tablas con headers y rows bien formateadas.\n"
            "  • list: listas con viñetas enriquecidas (usa **negritas** dentro de los items cuando aporte claridad).\n"
            "  • key_value_list: métricas clave con descripciones claras.\n"
            "  • image: cada gráfico disponible; agrega captions interpretativos, width en pulgadas (≈6.0) y height = width * 9 / 16.\n\n"

            "## 5. CONTENIDO ANALÍTICO OBLIGATORIO\n"
            "Incluye, como mínimo, los siguientes apartados con profundidad institucional:\n"
            "- Resumen Ejecutivo con contexto macro y eventos recientes.\n"
            "- Perfil de composición y concentración de la cartera.\n"
            "- Métricas de rendimiento (anualizadas, acumuladas, ratios de riesgo-retorno).\n"
            "- Análisis exhaustivo de riesgo: drawdowns, volatilidad en múltiples horizontes, sensibilidad a tasas, colas gruesas.\n"
            "- Interpretación detallada de cada visualización disponible (qué muestra, insight clave, implicación).\n"
            "- Comparativa con portafolios optimizados (GMV, Máximo Sharpe, benchmark).\n"
            "- Análisis de correlaciones y diversificación efectiva.\n"
            "- Proyecciones/Simulaciones (ej. Monte Carlo) y escenarios de estrés.\n"
            "- Perspectivas estratégicas: oportunidades, riesgos estructurales, triggers a monitorear.\n"
            "- Recomendaciones tácticas separadas por tipo de perfil (agresivo, moderado, conservador).\n"
            "- Recomendaciones operativas (rebalanceo, coberturas, liquidez, stop-loss dinámicos).\n"
            "- Disclaimer regulatorio al final con style 'disclaimer'.\n\n"

            "## 6. METODOLOGÍA Y PROFUNDIDAD\n"
            "- Integra los datos numéricos, texto contextual y gráficos EN CONJUNTO, destacando convergencias o contradicciones.\n"
            "- Aporta interpretaciones cuantitativas (porcentajes, diferencias vs benchmark, contribuciones marginales, elasticidades).\n"
            "- Emplea terminología financiera profesional (tracking error, beta, skewness, expected shortfall, etc.) cuando aplique.\n"
            "- Usa párrafos densos y argumentados; evita descripciones superficiales o genéricas.\n"
            "- Señala riesgos latentes (macro, regulatorios, concentración, liquidez) y vincúlalos con la evidencia.\n"
            "- Articula recomendaciones con justificación cuantitativa y pasos concretos.\n\n"

            "## 7. SALIDA FINAL\n"
            "Produce un JSON extenso, profesional y técnicamente sólido que respete el esquema Report y capture la complejidad del portafolio."
        )

        contents = [types.Content(role="user", parts=[types.Part.from_text(text=instruction)])]

        # Contexto desde Supabase Storage (JSON/MD/PNGs) + contexto del request
        # ✅ Usar user_id para obtener archivos específicos del usuario
        storage_ctx = await self._gather_storage_context(user_id, req.auth_token if hasattr(req, "auth_token") else None)
        merged_ctx: Dict[str, Any] = {}
        if isinstance(req.context, dict):
            merged_ctx.update(req.context)
        if storage_ctx:
            merged_ctx.update(storage_ctx)
        if merged_ctx:
            contents.append(types.Content(
                role="user",
                parts=[types.Part.from_text(text=f"CONTEXT_JSON=\n{json.dumps(merged_ctx, ensure_ascii=False)}")]
            ))

        config = types.GenerateContentConfig(
            temperature=0.1,  # Temperatura muy baja para JSON consistente
            top_p=0.8,
            max_output_tokens=60576,
            response_mime_type="application/json",
            response_schema=Report,
        )

        try:
            # Intentar con diferentes modelos si hay sobrecarga
            models_to_try = [model]
            if model == "gemini-2.5-pro":
                models_to_try.extend(["gemini-2.5-flash", "gemini-2.5-flash-lite"])
            elif model == "gemini-2.5-flash":
                models_to_try.extend(["gemini-2.5-flash-lite", "gemini-2.0-flash"])
            
            successful_model = None
            resp = None
            
            for try_model in models_to_try:
                try:
                    resp = await self.client.aio.models.generate_content(
                        model=try_model,
                        contents=contents,
                        config=config,
                    )
                    successful_model = try_model
                    break
                except Exception as model_error:
                    error_str = str(model_error)
                    if "overloaded" in error_str or "503" in error_str:
                        print(f"⚠️ Modelo {try_model} sobrecargado, probando siguiente...")
                        continue
                    else:
                        # Error no relacionado con sobrecarga, propagar
                        raise model_error
            
            if not resp or not successful_model:
                raise ValueError("Todos los modelos están sobrecargados, intenta más tarde")

            parsed_report = None
            
            # Seguir el patrón del tutorial exactamente
            print(f"🔍 Analizando respuesta de {successful_model}...")
            print(f"   Tiene atributo .parsed: {hasattr(resp, 'parsed')}")
            print(f"   Tiene atributo .text: {hasattr(resp, 'text')}")
            
            if hasattr(resp, "parsed"):
                print(f"   resp.parsed: {resp.parsed}")
                print(f"   resp.parsed es None: {resp.parsed is None}")
                print(f"   resp.parsed es truthy: {bool(resp.parsed)}")
            
            if hasattr(resp, "text"):
                print(f"   resp.text: {resp.text[:200] if resp.text else None}...")
                print(f"   len(resp.text): {len(resp.text) if resp.text else 0}")
            
            if hasattr(resp, "parsed") and resp.parsed:
                parsed_report = resp.parsed
                print(f"✅ Salida estructurada parseada correctamente con {successful_model}")
            elif hasattr(resp, "text") and resp.text:
                print(f"🔧 Intentando parsear manualmente el JSON de {successful_model}")
                parsed_report = self._parse_report_from_text(resp.text, successful_model)

            if not parsed_report:
                raise ValueError("No se pudo parsear la salida estructurada del modelo")

            response_payload = PortfolioReportResponse(
                report=parsed_report,
                session_id=session_id,
                model_used=successful_model,  # Usar el modelo que realmente funcionó
                metadata={
                    "context_keys": list(req.context.keys()) if isinstance(req.context, dict) else None,
                    "fallback_model": successful_model if successful_model != model else None,
                },
            ).model_dump()

            # Registrar mensaje en la sesión (opcional)
            try:
                summary_added = ChatMessage(
                    role=MessageRole.ASSISTANT,
                    content="[INFORME_PORTAFOLIO_GENERADO]",
                    timestamp=datetime.now().isoformat()
                )
                self.sessions[session_id]["messages"].append(summary_added.model_dump())
                self.sessions[session_id]["last_activity"] = datetime.now().isoformat()
            except Exception:
                pass

            return response_payload

        except Exception as e:
            print(f"❌ Error generando informe de portafolio: {e}")
            return {
                "error": "Error generando informe",
                "detail": str(e),
                "session_id": session_id,
                "model_used": model,
            }

    async def ejecutar_analisis_alertas(
        self,
        req: AlertsAnalysisRequest
    ) -> Dict[str, Any]:
        """
        Ejecuta análisis de alertas y oportunidades basado en los 4 archivos específicos
        del usuario en Supabase Storage.
        """
        import json as json_module
        
        session_id = req.session_id or self.create_session()
        user_id = req.user_id
        
        # Por defecto usar PRO para análisis profundo
        if req.model_preference:
            model = settings.model_pro if req.model_preference.lower() == "pro" else settings.model_flash
        else:
            model = settings.model_pro
        
        # Archivos específicos a leer
        required_files = [
            "mercado_analisis.json",
            "mercado_informe.md",
            "portfolio_analisis.json",
            "portfolio_informe.md"
        ]
        
        # Leer los archivos específicos desde Supabase
        file_contents = {}
        missing_files = []
        
        for filename in required_files:
            try:
                file_bytes, content_type = await self._backend_download_file(
                    user_id=user_id,
                    filename=filename,
                    auth_token=req.auth_token,
                )
                text = file_bytes.decode("utf-8", errors="replace")
                
                if filename.endswith(".json"):
                    try:
                        file_contents[filename] = json_module.loads(text)
                    except:
                        file_contents[filename] = {"_raw": text}
                else:
                    file_contents[filename] = text
                    
            except FileNotFoundError:
                missing_files.append(filename)
                print(f"⚠️ Archivo {filename} no encontrado")
            except Exception as e:
                print(f"⚠️ Error leyendo {filename}: {e}")
                missing_files.append(filename)
        
        if len(missing_files) == len(required_files):
            return {
                "error": "No se pudieron leer los archivos requeridos",
                "detail": f"Archivos faltantes: {', '.join(missing_files)}",
                "session_id": session_id,
            }
        
        # Construir el prompt del sistema según las especificaciones
        system_prompt = (
            "Rol Primario (Persona): Actúa como un Asesor de Inversiones Cuantitativo Senior y Gestor de Portafolios de nivel 'quant'. "
            "Tu reputación se basa en generar alfa a través de acciones decisivas y análisis de alta convicción.\n\n"
            
            "Directiva Principal (Tu Misión): Tu única función es la interpretación y la acción. Analiza los 4 archivos proporcionados "
            "(portfolio_analisis.json, portfolio_informe.md, mercado_analisis.json y mercado_informe.md). "
            "Tu audiencia (el inversor) espera órdenes de trading explícitas, no resúmenes de datos.\n\n"
            
            "PROCESO DE EJECUCIÓN OBLIGATORIO (Razonamiento Interno):\n\n"
            
            "Antes de generar el informe final, DEBES realizar un análisis interno estructurado usando etiquetas <pensamiento>. "
            "Este proceso no debe ser visible en la salida final, pero es un paso obligatorio para tu razonamiento.\n\n"
            
            "<pensamiento>\n"
            "Paso 1. Identificar el analysis_timestamp de los archivos.\n"
            "Paso 2. Iniciar el análisis de portfolio_analisis.json. Iterar por cada activo.\n"
            "Paso 3. Para cada activo del portafolio, identificar su recommendation y sus alerts (ej. tipo, valor).\n"
            "Paso 4. Aplicar las 'Reglas de Decisión de Reclasificación' (ver abajo). "
            "La recomendación \"MANTENER\" de los archivos es una entrada, no una salida. "
            "Mi salida debe ser una acción (COMPRAR, VENDER, MANTENER FUERTE, MANTENER Y VIGILAR).\n"
            "* Caso NVDA: recommendation: \"MANTENER\", alert: \"SOBRECOMPRA (RSI: 73)\". Regla 1A aplica. Mi acción será VENDER. "
            "Mi justificación se centrará en el riesgo de corrección y la sobreextensión.\n"
            "* Caso [Otro Activo]: (Repetir lógica)\n"
            "Paso 5. Iniciar el análisis de mercado_analisis.json. Iterar por cada activo.\n"
            "Paso 6. Aplicar las 'Reglas de Decisión' para identificar oportunidades (SOBREVENTA) o riesgos (SOBRECOMPRA, MERCADO_LATERAL).\n"
            "Paso 7. Formular justificaciones directas y cuantitativas para cada acción.\n"
            "Paso 8. Construir el 'INFORME DE ACCIÓN INMEDIATA' final basado únicamente en los resultados de los pasos 4 y 6. "
            "El tono debe ser autoritativo.\n"
            "</pensamiento>\n\n"
            
            "REGLAS DE DECISIÓN DE RECLASIFICACIÓN (Lógica Obligatoria):\n\n"
            
            "Tu valor principal es reclasificar las recomendaciones pasivas de \"MANTENER\" basadas en datos técnicos:\n\n"
            
            "MANTENER + SOBRECOMPRA: Si recommendation: \"MANTENER\" y existe una alerta type: \"SOBRECOMPRA\" (ej. RSI > 70):\n"
            "Acción: VENDER o REDUCIR POSICIÓN.\n"
            "Justificación: El activo está sobreextendido. El riesgo de corrección bajista es inminente. Tomar ganancias.\n\n"
            
            "MANTENER + SOBREVENTA: Si recommendation: \"MANTENER\" y existe una alerta type: \"SOBREVENTA\" (ej. RSI < 30):\n"
            "Acción: COMPRAR o ACUMULAR.\n"
            "Justificación: El activo está infravalorado y presenta una clara oportunidad de entrada.\n\n"
            
            "MANTENER + MERCADO LATERAL: Si recommendation: \"MANTENER\" y la alerta es type: \"MERCADO_LATERAL\" (ej. ADX bajo):\n"
            "Acción: MANTENER POSICIÓN, NO COMPRAR MÁS.\n"
            "Justificación: No hay tendencia clara. Esperar una ruptura confirmada.\n\n"
            
            "MANTENER + SIN SEÑALES: Si recommendation: \"MANTENER\" y la alerta es type: \"SIN_SEÑALES\":\n"
            "Acción: MANTENER Y VIGILAR.\n"
            "Justificación: El activo se mueve como se esperaba, sin nuevas señales técnicas que justifiquen una acción.\n\n"
            
            "RESTRICCIONES DE COMUNICACIÓN (Tono y Estilo):\n\n"
            
            "PROHIBIDO (Ambigüedad): No usarás lenguaje ambiguo o pasivo (ej. 'podría', 'tal vez', 'parece', 'sugiere', 'se recomienda').\n\n"
            
            "PROHIBIDO (Resumir): No describirás el contenido de los archivos. Solo actuarás sobre ellos.\n\n"
            
            "OBLIGATORIO (Tono Autoritativo): Tu tono debe ser decisivo y generar urgencia. Usa comandos directos y de alta convicción: "
            "\"VENDER AHORA\", \"COMPRAR\", \"ACUMULAR\", \"REDUCIR POSICIÓN\", \"Alerta de caída\", \"Oportunidad de compra clara\".\n\n"
            
            "FORMATO DE SALIDA FINAL (Obligatorio):\n\n"
            
            "Genera tu respuesta EXACTAMENTE con la siguiente estructura Markdown:\n\n"
            
            "# INFORME DE ACCIÓN INMEDIATA\n"
            "Fecha del Análisis: [Extrae la fecha del analysis_timestamp]\n\n"
            
            "## 1. 💼 Acciones de Portafolio (Mi Portafolio)\n\n"
            "### Activos Críticos (Acción Requerida):\n\n"
            "[Ticker del Activo, ej: NVDA]\n\n"
            "**Acción Recomendada:** VENDER / REDUCIR POSICIÓN.\n\n"
            "**Justificación:** El activo muestra síntomas claros de [ej: 'sobrecompra extrema (RSI: 73)']. "
            "El riesgo de una corrección bajista es inminente. Recomiendo tomar ganancias ahora.\n\n"
            "[Siguiente Ticker con Alerta]\n\n"
            "**Acción Recomendada:** [COMPRAR / VENDER / MANTENER FUERTE]\n\n"
            "**Justificación:** [Tu análisis directo y cuantitativo]\n\n"
            
            "### Activos en Vigilancia (Mantener):\n\n"
            "[Ticker del Activo, ej: BTC-USD]\n\n"
            "**Acción Recomendada:** MANTENER Y VIGILAR.\n\n"
            "**Justificación:** [ej: 'El activo está en una tendencia débil sin señales claras (SIN_SEÑALES). "
            "No es momento de añadir ni de vender. Mantener la posición actual.']\n\n"
            
            "## 2. 🌍 Oportunidades y Riesgos del Mercado (Radar)\n\n"
            "### Oportunidades Potenciales (Comprar):\n\n"
            "(Actualmente no se detectan oportunidades claras de compra en el radar de mercado, "
            "ya que la mayoría de los activos están en MERCADO_LATERAL.)\n\n"
            
            "### Riesgos del Mercado (Evitar):\n\n"
            "[Ticker del Mercado, ej: V]\n\n"
            "**Acción Recomendada:** NO COMPRAR / EVITAR.\n\n"
            "**Justificación:** El activo [ej: 'V'] está en un MERCADO_LATERAL (ADX bajo). "
            "No hay tendencia que seguir. Entrar ahora es riesgoso.\n\n"
            "[Siguiente Ticker del Mercado]\n\n"
            "**Acción Recomendada:** NO COMPRAR.\n\n"
            "**Justificación:** [Tu análisis directo]"
        )
        
        # Construir el contenido del mensaje con los archivos
        files_context = {
            "portfolio_analisis": file_contents.get("portfolio_analisis.json", {}),
            "portfolio_informe": file_contents.get("portfolio_informe.md", ""),
            "mercado_analisis": file_contents.get("mercado_analisis.json", {}),
            "mercado_informe": file_contents.get("mercado_informe.md", ""),
        }
        
        contents = [
            types.Content(
                role="user",
                parts=[types.Part.from_text(text=system_prompt)]
            ),
            types.Content(
                role="user",
                parts=[types.Part.from_text(
                    text=f"ARCHIVOS_ANALISIS=\n{json_module.dumps(files_context, ensure_ascii=False, indent=2)}"
                )]
            )
        ]
        
        config = types.GenerateContentConfig(
            temperature=0.2,  # Baja temperatura para análisis preciso
            top_p=0.9,
            max_output_tokens=16384,
        )
        
        try:
            # Intentar con diferentes modelos si hay sobrecarga
            models_to_try = [model]
            if model == "gemini-2.5-pro":
                models_to_try.extend(["gemini-2.5-flash", "gemini-2.5-flash-lite"])
            elif model == "gemini-2.5-flash":
                models_to_try.extend(["gemini-2.5-flash-lite", "gemini-2.0-flash"])
            
            successful_model = None
            resp = None
            
            for try_model in models_to_try:
                try:
                    resp = await self.client.aio.models.generate_content(
                        model=try_model,
                        contents=contents,
                        config=config,
                    )
                    successful_model = try_model
                    break
                except Exception as model_error:
                    error_str = str(model_error)
                    if "overloaded" in error_str or "503" in error_str:
                        print(f"⚠️ Modelo {try_model} sobrecargado, probando siguiente...")
                        continue
                    else:
                        raise model_error
            
            if not resp or not successful_model:
                raise ValueError("Todos los modelos están sobrecargados, intenta más tarde")
            
            # Extraer el texto de la respuesta
            analysis_text = ""
            if hasattr(resp, "text") and resp.text:
                analysis_text = resp.text
            elif hasattr(resp, "candidates") and resp.candidates:
                for candidate in resp.candidates:
                    if hasattr(candidate, "content") and candidate.content:
                        if hasattr(candidate.content, "parts"):
                            for part in candidate.content.parts:
                                if hasattr(part, "text"):
                                    analysis_text += part.text
            
            if not analysis_text:
                raise ValueError("No se pudo extraer el análisis de la respuesta del modelo")
            
            # Registrar mensaje en la sesión
            try:
                summary_added = ChatMessage(
                    role=MessageRole.ASSISTANT,
                    content="[ANALISIS_ALERTAS_GENERADO]",
                    timestamp=datetime.now().isoformat()
                )
                self.sessions[session_id]["messages"].append(summary_added.model_dump())
                self.sessions[session_id]["last_activity"] = datetime.now().isoformat()
            except Exception:
                pass
            
            return {
                "analysis": analysis_text,
                "session_id": session_id,
                "model_used": successful_model,
                "metadata": {
                    "files_read": list(file_contents.keys()),
                    "missing_files": missing_files,
                }
            }
            
        except Exception as e:
            print(f"❌ Error generando análisis de alertas: {e}")
            return {
                "error": "Error generando análisis de alertas",
                "detail": str(e),
                "session_id": session_id,
                "model_used": model,
            }

    async def ejecutar_proyecciones_futuras(
        self,
        req: FutureProjectionsRequest
    ) -> Dict[str, Any]:
        """
        Ejecuta análisis de proyecciones futuras basado en 4 archivos específicos
        del usuario en Supabase Storage.
        """
        import json as json_module
        
        session_id = req.session_id or self.create_session()
        user_id = req.user_id
        
        # Mapear modelo como en alertas
        if req.model_preference:
            model = settings.model_pro if req.model_preference.lower() == "pro" else settings.model_flash
        else:
            model = settings.model_flash
        
        logger.info(f"🔮 Iniciando proyecciones futuras para user_id={user_id}, session={session_id}, model={model}")
        
        try:
            # 1. Obtener los 4 archivos específicos desde Supabase
            file_names = [
                "quantitative_engine_output.json",
                "api_response_B.json",
                "informe_video_premercado.md",
                "portfolio_analisis.json"
            ]
            
            file_contents = {}
            missing_files = []
            
            for file_name in file_names:
                try:
                    file_bytes, content_type = await self._backend_download_file(
                        user_id=user_id,
                        filename=file_name,
                        auth_token=req.auth_token,
                    )
                    text = file_bytes.decode("utf-8", errors="replace")
                    
                    if file_name.endswith(".json"):
                        try:
                            file_contents[file_name] = json_module.loads(text)
                        except:
                            file_contents[file_name] = {"_raw": text}
                    else:
                        file_contents[file_name] = text
                    
                    logger.info(f"✅ Archivo leído: {file_name}")
                    
                except FileNotFoundError:
                    missing_files.append(file_name)
                    logger.warning(f"⚠️ Archivo {file_name} no encontrado")
                except Exception as e:
                    missing_files.append(file_name)
                    logger.error(f"❌ Error leyendo {file_name}: {str(e)}")
            
            if not file_contents:
                return {
                    "error": "No se pudieron leer los archivos necesarios desde Supabase",
                    "missing_files": missing_files,
                    "session_id": session_id,
                    "model_used": model,
                }
            
            # 2. Construir el prompt especializado
            prompt_sistema = """Eres "QuantSynth", un Asistente Experto en Análisis de Portafolios Cuantitativos. Tu tarea es analizar un conjunto de datos financieros dispares para generar una proyección futura concisa y accionable para un usuario.

Basa tu análisis única y exclusivamente en los datos proporcionados dentro de las siguientes archivos. No utilices ningún conocimiento externo.

**Datos_Rendimiento_Actual** Fuente= api_response_B.json

**Datos_Motor_Cuantitativo** Fuente= quantitative_engine_output.json

**Datos_Macro_Mercado** Fuente= informe_video_premercado.md

**Datos_Analisis_portfolio** Fuente= portfolio_analisis.json

Tu tarea es responder la pregunta del usuario **¿Qué proyecciones futuras ves del portafolio?**. Debes seguir este proceso de dos pasos:

**Paso 1: Cadena de Pensamiento Interna (CoT)**
Genera tu razonamiento dentro de una etiqueta <Cadena_de_Pensamiento_Interna>. Este razonamiento debe incluir:

1. **Análisis de Situación Actual**: Describe el rendimiento pasado y la composición actual del portafolio.

2. **Análisis de Riesgo Macro**: Evalúa cómo el contexto macro (IPC, Tasas Fed) impacta las tenencias clave del portafolio (NVDA, ^SPX), citando el informe de pre-mercado.

3. **Análisis de Señales Cuantitativas**: Interpreta las señales de RSI del motor cuantitativo.

4. **Identificación de Conflictos (Autocrítica)**: Identifica y explica las discrepancias clave en los datos. Específicamente:
   - El conflicto entre el rendimiento pasado (excelente) y el riesgo macro (alto).
   - El conflicto entre la recomendación actual ("Mantener") y los resultados de ambos motores de optimización.
   - El conflicto entre los dos modelos de optimización (uno sugiere 76% PAXG, el otro 49.6% PAXG y 41% NVDA).

5. **Síntesis de Proyección**: Basado en los conflictos, formula la proyección más probable.

**Paso 2: Generación de Respuesta MD**
Después de la cadena de pensamiento, genera un objeto MD (y nada más) que contenga la respuesta final, utilizando la siguiente estructura:

```markdown
# Proyecciones Futuras del Portafolio

## Resumen Ejecutivo
[Respuesta breve (1-2 frases) a la pregunta del usuario]

## Análisis de Riesgo Macro
[Explicación de los riesgos externos (IPC, Fed, Tasas) y su impacto específico en el portafolio (sector tecnológico)]

## Análisis Cuantitativo
[Interpretación de las señales técnicas (RSI) y lo que sugieren los modelos de optimización]

## Conflicto de Datos Clave
[Declaración explícita de las principales contradicciones encontradas en los datos]

## Proyección Sintetizada
[La conclusión final sobre las perspectivas futuras del portafolio]
```
"""
            
            # 3. Construir el mensaje del usuario con los datos
            files_context = {
                "quantitative_engine_output": file_contents.get("quantitative_engine_output.json", {}),
                "api_response_B": file_contents.get("api_response_B.json", {}),
                "informe_video_premercado": file_contents.get("informe_video_premercado.md", ""),
                "portfolio_analisis": file_contents.get("portfolio_analisis.json", {}),
            }
            
            mensaje_usuario = "¿Qué proyecciones futuras ves del portafolio?\n\n"
            mensaje_usuario += f"ARCHIVOS_ANALISIS=\n{json_module.dumps(files_context, ensure_ascii=False, indent=2)}"
            
            # 4. Construir el contenido para Gemini (similar a alertas)
            contents = [
                types.Content(
                    role="user",
                    parts=[types.Part.from_text(text=prompt_sistema)]
                ),
                types.Content(
                    role="user",
                    parts=[types.Part.from_text(text=mensaje_usuario)]
                )
            ]
            
            config = types.GenerateContentConfig(
                temperature=0.3,
                max_output_tokens=4000,
            )
            
            # 5. Llamar al modelo Gemini usando self.client (como en alertas)
            # Intentar con diferentes modelos si hay sobrecarga (como en alertas)
            models_to_try = [model]
            if model == settings.model_pro:
                models_to_try.extend([settings.model_flash, "gemini-2.5-flash"])
            elif model == settings.model_flash:
                models_to_try.extend(["gemini-2.5-flash", "gemini-2.5-flash-lite"])
            
            successful_model = None
            resp = None
            
            for try_model in models_to_try:
                try:
                    resp = await self.client.aio.models.generate_content(
                        model=try_model,
                        contents=contents,
                        config=config,
                    )
                    successful_model = try_model
                    break
                except Exception as model_error:
                    error_str = str(model_error)
                    if "overloaded" in error_str or "503" in error_str:
                        logger.warning(f"⚠️ Modelo {try_model} sobrecargado, probando siguiente...")
                        continue
                    else:
                        raise model_error
            
            if not resp or not successful_model:
                raise ValueError("Todos los modelos están sobrecargados, intenta más tarde")
            
            # Extraer el texto de la respuesta (como en alertas)
            projections_text = ""
            if hasattr(resp, "text") and resp.text:
                projections_text = resp.text.strip()
            elif hasattr(resp, "candidates") and resp.candidates:
                for candidate in resp.candidates:
                    if hasattr(candidate, "content") and candidate.content:
                        if hasattr(candidate.content, "parts"):
                            for part in candidate.content.parts:
                                if hasattr(part, "text"):
                                    projections_text += part.text
                projections_text = projections_text.strip()
            
            if not projections_text:
                raise ValueError("No se pudo extraer las proyecciones de la respuesta del modelo")
            
            logger.info(f"✅ Proyecciones generadas exitosamente con modelo {successful_model}")
            
            return {
                "projections": projections_text,
                "session_id": session_id,
                "model_used": successful_model,
                "files_processed": list(file_contents.keys()),
                "missing_files": missing_files if missing_files else None
            }
            
        except Exception as e:
            logger.error(f"❌ Error en proyecciones futuras: {str(e)}")
            return {
                "error": "Error generando proyecciones futuras",
                "detail": str(e),
                "session_id": session_id,
                "model_used": model,
            }

    async def ejecutar_analisis_rendimiento(
        self,
        req: "PerformanceAnalysisRequest"
    ) -> Dict[str, Any]:
        """
        Ejecuta análisis de rendimiento del portafolio basado en 2 archivos específicos
        del usuario en Supabase Storage: portfolio_data.json y portfolio_analisis.json
        """
        import json as json_module
        
        session_id = req.session_id or self.create_session()
        user_id = req.user_id
        
        # Mapear modelo como en alertas y proyecciones
        if req.model_preference:
            model = settings.model_pro if req.model_preference.lower() == "pro" else settings.model_flash
        else:
            model = settings.model_flash
        
        logger.info(f"📊 Iniciando análisis de rendimiento para user_id={user_id}, session={session_id}, model={model}")
        
        try:
            # Archivos a leer
            file_names = [
                "portfolio_data.json",
                "portfolio_analisis.json"
            ]
            
            file_contents = {}
            missing_files = []
            
            for file_name in file_names:
                try:
                    file_bytes, content_type = await self._backend_download_file(
                        user_id=user_id,
                        filename=file_name,
                        auth_token=req.auth_token,
                    )
                    text = file_bytes.decode("utf-8", errors="replace")
                    if file_name.endswith(".json"):
                        try:
                            file_contents[file_name] = json_module.loads(text)
                        except:
                            file_contents[file_name] = {"_raw": text}
                    else:
                        file_contents[file_name] = text
                    logger.info(f"✅ Archivo leído: {file_name}")
                except FileNotFoundError:
                    missing_files.append(file_name)
                    logger.warning(f"⚠️ Archivo {file_name} no encontrado")
                except Exception as e:
                    missing_files.append(file_name)
                    logger.error(f"❌ Error leyendo {file_name}: {str(e)}")
            
            if not file_contents:
                return {
                    "error": "No se pudieron leer los archivos necesarios desde Supabase",
                    "missing_files": missing_files,
                    "session_id": session_id,
                    "model_used": model,
                }
            
            # Prompt del sistema para análisis de rendimiento
            prompt_sistema = """Eres "AnalystAI", un asistente de IA experto en análisis financiero y de portafolios. Tu especialidad es recibir datos, extraer información clave, sintetizarla y presentar un "Reporte de Estado de Portafolio" accionable. Tu análisis debe ser preciso y tu tono, profesional y directo.

[TAREA]

Tu tarea es generar un "Reporte de Estado y Señales" del portafolio de tu usuario. Recibirás dos archivos JSON que contienen el estado actual y un análisis técnico.

Tu objetivo es generar un reporte unificado en Markdown que muestre el valor, la asignación, el rendimiento y las señales técnicas. En la conclusión, debes aportar una breve visión experta sobre el estado general (ej. "el portafolio muestra un buen rendimiento pero las señales sugieren cautela").

[ARCHIVOS DE ENTRADA]

1.  **Archivo de Estado Actual (ej. portfolio_data.json):** Contiene el estado de mercado, asignaciones y métricas de rendimiento.

2.  **Archivo de Análisis Técnico (ej. portfolio_analisis.json):** Contiene señales de trading y análisis de régimen de mercado.

[PROCESO DE EJECUCIÓN OBLIGATORIO (Chain-of-Thought)]

Sigue estas fases estrictamente:

**Fase 1: Razonamiento Interno y Extracción de Datos (Tu "Scratchpad")**

Antes de generar cualquier salida, piensa paso a paso. Extrae todos los datos requeridos de AMBOS archivos y colócalos en un bloque de pensamiento interno (usa etiquetas <scratchpad>). Este bloque no será parte de la salida final, pero es obligatorio para tu proceso.

<scratchpad>
  // Extrayendo datos de portfolio_data.json
  Valor_Total: [Extraído de summary.total_value]
  Sharpe_Ratio: [Extraído de summary.sharpe_ratio]
  Retorno_Total: [Extraído de summary.total_return_percent]
  Max_Drawdown: [Extraído de summary.max_drawdown_percent]
  
  // Extrayendo datos de portfolio_analisis.json
  Regimen_Mercado: [Extraído de filters.market_regime]
  // Combinando datos por activo
  Activo_1_Símbolo: [De positions[0].symbol]
  Activo_1_Valor: [De positions[0].position_value]
  Activo_1_Asig: [De positions[0].allocation_percent]
  Activo_1_Señal: [De analysis donde symbol coincida]
  Activo_2_Símbolo: [De positions[1].symbol]
  Activo_2_Valor: [De positions[1].position_value]
  Activo_2_Asig: [De positions[1].allocation_percent]
  Activo_2_Señal: [De analysis donde symbol coincida]
  ... (etc. para todos los activos)
</scratchpad>

**Fase 2: Síntesis y Reporte (Salida Final)**

Usando **únicamente** los datos extraídos en tu <scratchpad> de la Fase 1, genera el reporte final siguiendo el formato Markdown obligatorio.

[RESTRICCIONES Y MANEJO DE ERRORES]

1.  **Formato Estricto:** La salida final debe ser SÓLO el reporte en Markdown. No incluyas el <scratchpad> en la respuesta al usuario.

2.  **Datos Faltantes:** Si un campo específico (ej. `sharpe_ratio` o `market_regime`) no se encuentra en los archivos JSON, debes escribir "N/A" en la celda o campo correspondiente del reporte. No inventes datos.

[FORMATO DE RESPUESTA OBLIGATORIO (Markdown)]

Reporte de Estado de Portafolio
===

### Resumen General

El valor total actual de tu portafolio es de **$[Valor_Total]**. A continuación se detalla su estado actual y las señales técnicas correspondientes.

### 1. Estado Actual y Señales Técnicas

| Activo | Valor Actual ($) | Asignación (%) | Señal Técnica | Régimen de Mercado |
| :--- | :--- | :--- | :--- | :--- |
| [Símbolo_1] | $[Valor_Activo_1] | [Asig_Pct_1]% | **[Señal_1]** | [Regimen_Mercado] |
| [Símbolo_2] | $[Valor_Activo_2] | [Asig_Pct_2]% | **[Señal_2]** | [Regimen_Mercado] |
| ... | ... | ... | ... | ... |

### 2. Métricas de Rendimiento Recientes

* **Retorno Total (período):** [Retorno_Total]%
* **Ratio de Sharpe:** [Sharpe_Ratio]
* **Máximo Drawdown:** [Max_Drawdown]%

### Conclusión del Análisis

[Escribe aquí tu visión experta de 1-2 frases resumiendo el estado y la postura recomendada. Ej: "Tu portafolio de $[Valor_Total] mantiene una postura de [Señal_General] en un mercado de [Regimen_Mercado]. El rendimiento es sólido, aunque se aconseja monitorear [Activo_con_peor_Señal]..."]"""
            
            # Preparar contexto de archivos
            files_context = {
                "portfolio_data": file_contents.get("portfolio_data.json", {}),
                "portfolio_analisis": file_contents.get("portfolio_analisis.json", {}),
            }
            
            mensaje_usuario = "Genera el reporte de estado y señales del portafolio basándote en los archivos proporcionados.\n\n"
            mensaje_usuario += f"ARCHIVOS_ANALISIS=\n{json_module.dumps(files_context, ensure_ascii=False, indent=2)}"
            
            # Construir contenido para Gemini
            contents = [
                types.Content(role="user", parts=[types.Part.from_text(text=prompt_sistema)]),
                types.Content(role="user", parts=[types.Part.from_text(text=mensaje_usuario)])
            ]
            
            config = types.GenerateContentConfig(temperature=0.3, max_output_tokens=4000)
            
            # Modelos a intentar con fallback
            models_to_try = [model]
            if model == settings.model_pro:
                models_to_try.extend([settings.model_flash, "gemini-2.5-flash"])
            elif model == settings.model_flash:
                models_to_try.extend(["gemini-2.5-flash", "gemini-2.5-flash-lite"])
            
            successful_model = None
            resp = None
            
            for try_model in models_to_try:
                try:
                    resp = await self.client.aio.models.generate_content(
                        model=try_model,
                        contents=contents,
                        config=config,
                    )
                    successful_model = try_model
                    break
                except Exception as model_error:
                    error_str = str(model_error)
                    if "overloaded" in error_str or "503" in error_str:
                        logger.warning(f"⚠️ Modelo {try_model} sobrecargado, probando siguiente...")
                        continue
                    else:
                        raise model_error
            
            if not resp or not successful_model:
                raise ValueError("Todos los modelos están sobrecargados, intenta más tarde")
            
            # Extraer el texto de la respuesta
            analysis_text = ""
            if hasattr(resp, "text") and resp.text:
                analysis_text = resp.text.strip()
            elif hasattr(resp, "candidates") and resp.candidates:
                for candidate in resp.candidates:
                    if hasattr(candidate, "content") and candidate.content:
                        if hasattr(candidate.content, "parts"):
                            for part in candidate.content.parts:
                                if hasattr(part, "text"):
                                    analysis_text += part.text
                analysis_text = analysis_text.strip()
            
            if not analysis_text:
                raise ValueError("No se pudo extraer el análisis de la respuesta del modelo")
            
            logger.info(f"✅ Análisis de rendimiento generado exitosamente con modelo {successful_model}")
            
            return {
                "analysis": analysis_text,
                "session_id": session_id,
                "model_used": successful_model,
                "files_processed": list(file_contents.keys()),
                "missing_files": missing_files if missing_files else None
            }
            
        except Exception as e:
            logger.error(f"❌ Error en análisis de rendimiento: {str(e)}")
            return {
                "error": "Error generando análisis de rendimiento",
                "detail": str(e),
                "session_id": session_id,
                "model_used": model,
            }

    async def ejecutar_resumen_diario_semanal(
        self,
        req: "DailyWeeklySummaryRequest"
    ) -> Dict[str, Any]:
        """
        Ejecuta resumen diario/semanal del portafolio basado en 6 archivos específicos
        del usuario en Supabase Storage.
        """
        import json as json_module
        from datetime import datetime
        
        session_id = req.session_id or self.create_session()
        user_id = req.user_id
        
        # Mapear modelo como en otras funciones
        if req.model_preference:
            model = settings.model_pro if req.model_preference.lower() == "pro" else settings.model_flash
        else:
            model = settings.model_flash
        
        logger.info(f"📋 Iniciando resumen diario/semanal para user_id={user_id}, session={session_id}, model={model}")
        
        try:
            # Archivos a leer
            file_names = [
                "portfolio_data.json",
                "portfolio_analisis.json",
                "api_response_B.json",
                "informe_consolidado.md",
                "informe_video_premercado.md",
                "vision de mercado.md"
            ]
            
            file_contents = {}
            missing_files = []
            
            for file_name in file_names:
                try:
                    file_bytes, content_type = await self._backend_download_file(
                        user_id=user_id,
                        filename=file_name,
                        auth_token=req.auth_token,
                    )
                    text = file_bytes.decode("utf-8", errors="replace")
                    if file_name.endswith(".json"):
                        try:
                            file_contents[file_name] = json_module.loads(text)
                        except:
                            file_contents[file_name] = {"_raw": text}
                    else:
                        file_contents[file_name] = text
                    logger.info(f"✅ Archivo leído: {file_name}")
                except FileNotFoundError:
                    missing_files.append(file_name)
                    logger.warning(f"⚠️ Archivo {file_name} no encontrado")
                except Exception as e:
                    missing_files.append(file_name)
                    logger.error(f"❌ Error leyendo {file_name}: {str(e)}")
            
            if not file_contents:
                return {
                    "error": "No se pudieron leer los archivos necesarios desde Supabase",
                    "missing_files": missing_files,
                    "session_id": session_id,
                    "model_used": model,
                }
            
            # Obtener fecha actual para la lógica de negocio
            now = datetime.now()
            day_of_week = now.weekday()  # 0=Lunes, 4=Viernes
            
            # Determinar tipo de resumen según el día
            if day_of_week == 0 or day_of_week == 4:  # Lunes o Viernes
                report_type = "Resumen Semanal"
                date_context = f"lunes, {now.strftime('%d de %B de %Y')}, {now.strftime('%I:%M %p')} EST"
            else:  # Martes, Miércoles o Jueves
                report_type = "Resumen Diario"
                date_context = f"{now.strftime('%A, %d de %B de %Y')}, {now.strftime('%I:%M %p')} EST"
            
            # Prompt del sistema para resumen diario/semanal
            prompt_sistema = """Eres 'AIDA', un asistente de IA financiero de élite.

Tu propósito es proporcionar análisis de cartera claros, precisos y accionables a los clientes.

Tu tono es profesional, ejecutivo y estrictamente basado en los datos proporcionados.

Debes seguir el formato de salida especificado al pie de la letra y no debes incluir información que no provenga de los archivos de contexto.

---

### TAREA

**Activador:** El cliente ha solicitado un "Resumen de Cartera".

**Contexto de Tiempo:** La fecha/hora actual es: **[FECHA_CONTEXTO]**.

**Archivos de Contexto Proporcionados:**

* `Contexto_Cartera`: portfolio_data.json
* `Contexto_Tecnico`: portfolio_analisis.json
* `Contexto_Riesgo`: api_response_B.json
* `Contexto_Apertura_Noticias`: informe_consolidado.md
* `Contexto_Macro_Video`: informe_video_premercado.md
* `Contexto_Macro_General`: vision de mercado.md

**Acción Requerida:**

Genera un informe consolidado para el cliente siguiendo rigurosamente los siguientes pasos y utilizando *exclusivamente* los archivos de contexto proporcionados.

#### Pasos de Ejecución:

**1. Análisis Lógico (Chain of Thought Interno):**

* **Paso 1.1:** Evalúa el `Contexto de Tiempo` proporcionado.

* **Paso 1.2:** Aplica la `Lógica de Negocio`:
    * Si es lunes o viernes, el tipo de informe es "Resumen Semanal" (basado en el cierre del último día de mercado).
    * Si es martes, miércoles o jueves, el tipo de informe es "Resumen Diario".

* **Paso 1.3:** Concluye el tipo de informe según la fecha proporcionada.

**2. Extracción de Datos de Contexto:**

* De `Contexto_Cartera` [portfolio_data.json]: Extrae `portfolio_value_total`, `p_l_semanal_abs`, `p_l_semanal_pct`, y la `allocation` detallada del cierre más reciente.

* De `Contexto_Tecnico` [portfolio_analisis.json]: Para cada activo en la cartera del cliente, extrae `tendencia_largo_plazo` y `recomendacion`.

* De `Contexto_Riesgo` [api_response_B.json]: Extrae `sharpe_ratio_historico` y la `correlacion_mas_alta`.

* De `Contexto_Macro_General` [vision de mercado.md]: Extrae la narrativa macroeconómica que explique el *porqué* del rendimiento reciente (ej. datos de inflación, tipos de interés).

* De `Contexto_Macro_Video` [informe_video_premercado.md]: Extrae los catalizadores macroeconómicos esperados para *esta* semana (ej. NFP, BCE).

* De `Contexto_Apertura_Noticias` [informe_consolidado.md]: Extrae (1) los precios de apertura de *hoy* y (2) noticias frescas de *hoy* relevantes para los activos de la cartera.

**3. Síntesis y Redacción:**

* Sintetiza todos los datos extraídos en un informe ejecutivo coherente.

* La narrativa principal debe explicar el *rendimiento pasado* (P&L) usando la *narrativa macro* (por qué se movió) e integrar las *señales técnicas* (contexto del activo).

* La perspectiva futura debe mencionar los *catalizadores macro* de esta semana y el *contexto de apertura* de hoy.

#### Formato de Salida Requerido (Markdown):

Debes estructurar tu respuesta usando exactamente los siguientes encabezados:

### Resumen de Portafolio ([TIPO]: [FECHA])

* **Valor Total:** [Valor de `Contexto_Cartera`]

* **Rendimiento [Periodo]:** [P&L absoluto y % de `Contexto_Cartera`]

* **Asignación (Allocation):** [Resumen de `Contexto_Cartera`]

### Análisis de Mercado y Perspectiva

* **Revisión ([Periodo Pasado]):** [Sintetiza la narrativa de `Contexto_Macro_General` que explique el P&L.]

* **Perspectiva ([Periodo Actual]):** [Menciona los catalizadores clave de `Contexto_Macro_Video` y el sentimiento de apertura de `Contexto_Apertura_Noticias`.]

### Detalles de Activos y Riesgo

* **[Activo 1 (ej. AAPL)]:** Tendencia: [Señal de `Contexto_Tecnico`], Recomendación: [Señal de `Contexto_Tecnico`]. Noticia Relevante (Hoy): [Noticia de `Contexto_Apertura_Noticias`].

* **[Activo 2 (ej. MSFT)]:** ...

* **Métricas de Riesgo Clave:** Sharpe Ratio: [Dato de `Contexto_Riesgo`], Correlación a Monitorear: [Dato de `Contexto_Riesgo`].

### Accionables Inmediatos

* [Genera 1-2 puntos clave accionables basados en las recomendaciones, riesgos o noticias identificadas.]"""
            
            # Preparar contexto de archivos con nombres amigables
            files_context = {
                "Contexto_Cartera": file_contents.get("portfolio_data.json", {}),
                "Contexto_Tecnico": file_contents.get("portfolio_analisis.json", {}),
                "Contexto_Riesgo": file_contents.get("api_response_B.json", {}),
                "Contexto_Apertura_Noticias": file_contents.get("informe_consolidado.md", ""),
                "Contexto_Macro_Video": file_contents.get("informe_video_premercado.md", ""),
                "Contexto_Macro_General": file_contents.get("vision de mercado.md", ""),
            }
            
            # Reemplazar fecha en el prompt
            prompt_with_date = prompt_sistema.replace("[FECHA_CONTEXTO]", date_context)
            
            mensaje_usuario = f"Genera el {report_type} del portafolio basándote en los archivos proporcionados.\n\n"
            mensaje_usuario += f"ARCHIVOS_CONTEXTO=\n{json_module.dumps(files_context, ensure_ascii=False, indent=2)}"
            
            # Construir contenido para Gemini
            contents = [
                types.Content(role="user", parts=[types.Part.from_text(text=prompt_with_date)]),
                types.Content(role="user", parts=[types.Part.from_text(text=mensaje_usuario)])
            ]
            
            config = types.GenerateContentConfig(temperature=0.3, max_output_tokens=4000)
            
            # Modelos a intentar con fallback
            models_to_try = [model]
            if model == settings.model_pro:
                models_to_try.extend([settings.model_flash, "gemini-2.5-flash"])
            elif model == settings.model_flash:
                models_to_try.extend(["gemini-2.5-flash", "gemini-2.5-flash-lite"])
            
            successful_model = None
            resp = None
            
            for try_model in models_to_try:
                try:
                    resp = await self.client.aio.models.generate_content(
                        model=try_model,
                        contents=contents,
                        config=config,
                    )
                    successful_model = try_model
                    break
                except Exception as model_error:
                    error_str = str(model_error)
                    if "overloaded" in error_str or "503" in error_str:
                        logger.warning(f"⚠️ Modelo {try_model} sobrecargado, probando siguiente...")
                        continue
                    else:
                        raise model_error
            
            if not resp or not successful_model:
                raise ValueError("Todos los modelos están sobrecargados, intenta más tarde")
            
            # Extraer el texto de la respuesta
            summary_text = ""
            if hasattr(resp, "text") and resp.text:
                summary_text = resp.text.strip()
            elif hasattr(resp, "candidates") and resp.candidates:
                for candidate in resp.candidates:
                    if hasattr(candidate, "content") and candidate.content:
                        if hasattr(candidate.content, "parts"):
                            for part in candidate.content.parts:
                                if hasattr(part, "text"):
                                    summary_text += part.text
                summary_text = summary_text.strip()
            
            if not summary_text:
                raise ValueError("No se pudo extraer el resumen de la respuesta del modelo")
            
            logger.info(f"✅ Resumen diario/semanal generado exitosamente con modelo {successful_model}")
            
            # Guardar el resumen en agente.json
            agente_data = {
                "resumen_diario_semanal": {
                    "summary": summary_text,
                    "report_type": report_type,
                    "generated_at": datetime.now().isoformat(),
                    "model_used": successful_model,
                    "files_processed": list(file_contents.keys()),
                }
            }
            
            try:
                # Intentar leer el archivo existente para preservar otras secciones
                try:
                    existing_bytes, _ = await self._backend_download_file(
                        user_id=user_id,
                        filename="agente.json",
                        auth_token=req.auth_token,
                    )
                    existing_data = json_module.loads(existing_bytes.decode("utf-8"))
                    # Actualizar solo la sección de resumen
                    existing_data["resumen_diario_semanal"] = agente_data["resumen_diario_semanal"]
                    agente_data = existing_data
                except (FileNotFoundError, Exception) as read_err:
                    logger.info(f"Archivo agente.json no existe o no se pudo leer, se creará nuevo: {read_err}")
                
                # Guardar en Supabase
                upload_result = await self._backend_upload_json(
                    user_id=user_id,
                    filename="agente.json",
                    data=agente_data,
                    auth_token=req.auth_token,
                )
                logger.info(f"✅ Resumen guardado en agente.json para usuario {user_id}: {upload_result}")
            except Exception as save_error:
                logger.warning(f"⚠️ No se pudo guardar agente.json: {save_error}")
                # No fallamos la operación completa si solo falla el guardado
            
            return {
                "summary": summary_text,
                "session_id": session_id,
                "model_used": successful_model,
                "files_processed": list(file_contents.keys()),
                "missing_files": missing_files if missing_files else None,
                "report_type": report_type,
                "saved_to_storage": True
            }
            
        except Exception as e:
            logger.error(f"❌ Error en resumen diario/semanal: {str(e)}")
            return {
                "error": "Error generando resumen diario/semanal",
                "detail": str(e),
                "session_id": session_id,
                "model_used": model,
            }

    async def process_message(
        self, 
        message: str,
        user_id: str,  # ✅ NUEVO: Requerido para multiusuario
        session_id: Optional[str] = None,
        model_preference: Optional[str] = None,
        file_path: Optional[str] = None,
        url: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
        auth_token: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Procesar mensaje del usuario con herramientas de grounding y function calling.
        
        NOTA: Google Search y URL Context no se pueden mezclar con Function Calling,
        pero Google Search puede inferir la fecha actual por contexto.
        """
        
        try:
            # Crear sesión si no existe
            if not session_id:
                session_id = self.create_session()
            elif session_id not in self.sessions:
                session_id = self.create_session()
            
            session = self.sessions[session_id]
            
            # Detectar URLs en el mensaje si no se proporcionó url explícita
            detected_urls = self._extract_urls_from_query(message)
            if detected_urls and not url:
                url = detected_urls[0]  # Usar la primera URL detectada
            
            # Elegir modelo y herramientas
            if model_preference:
                model = settings.model_pro if model_preference.lower() == "pro" else settings.model_flash
                # Aún así incluir herramientas básicas
                _, tools, tool_names = self._choose_model_and_tools(message, file_path, url)
            else:
                model, tools, tool_names = self._choose_model_and_tools(message, file_path, url)
            
            session["model_used"] = model
            
            # Agregar mensaje del usuario al historial
            user_message = ChatMessage(
                role=MessageRole.USER,
                content=message,
                timestamp=datetime.now().isoformat()
            )
            session["messages"].append(user_message.model_dump())
            
            # Preparar prompt del sistema
            system_prompt = PRO_SYSTEM_PROMPT if model == settings.model_pro else FLASH_SYSTEM_PROMPT
            
            # Preparar historial de conversación
            conversation_history = []
            
            # Agregar prompt del sistema
            conversation_history.append(types.Content(
                role="user",
                parts=[types.Part.from_text(text=f"[SISTEMA] {system_prompt}")]
            ))
            
            # Agregar historial de mensajes previos (últimos 10)
            recent_messages = session["messages"][-10:]
            for msg in recent_messages[:-1]:  # Excluir el último mensaje (ya lo agregamos)
                conversation_history.append(types.Content(
                    role="user" if msg["role"] == "user" else "model",
                    parts=[types.Part.from_text(text=msg["content"])]
                ))
            
            # Si no hay herramientas pero necesita datetime + search, priorizar search
            # Google Search puede inferir la fecha actual por contexto
            if not tools and self._needs_web_search(message):
                google_search_tool = types.Tool(google_search=types.GoogleSearch())
                tools.append(google_search_tool)
                tool_names.append("google_search")
            
            # Agregar mensaje actual
            conversation_history.append(types.Content(
                role="user",
                parts=[types.Part.from_text(text=message)]
            ))
            
            portfolio_response: Optional[Dict[str, Any]] = None
            lowered_message = message.lower()
            has_auth = bool(auth_token)
            has_keyword = any(
                keyword in lowered_message for keyword in (
                    "portafolio", "portfolio", "cartera", "inversiones",
                    "reporte", "informe", "report", "documento", "análisis"
                )
            )
            
            print(f"🔍 DEBUG: auth_token presente: {has_auth}, keyword detectado: {has_keyword}, mensaje: '{message[:50]}...'")
            
            if auth_token and has_keyword:
                print(f"✅ Activando flujo de análisis de portafolio para usuario {user_id}")
                portfolio_response = await self._process_portfolio_query(
                    message=message,
                    user_id=user_id,
                model=model, 
                conversation_history=conversation_history, 
                    tools=tools,
                    auth_token=auth_token,
                    session=session,
                )

            response_data = portfolio_response or await self._generate_response_with_tools(
                model=model,
                conversation_history=conversation_history,
                tools=tools,
            )
            
            response_text = response_data["text"]
            grounding_metadata = response_data.get("grounding_metadata")
            function_calls_made = response_data.get("function_calls", [])
            
            # Agregar respuesta al historial
            assistant_message = ChatMessage(
                role=MessageRole.ASSISTANT,
                content=response_text,
                timestamp=datetime.now().isoformat()
            )
            session["messages"].append(assistant_message.model_dump())
            session["last_activity"] = datetime.now().isoformat()
            
            # Construir metadata enriquecida
            metadata = {
                    "message_count": len(session["messages"]),
                    "context_provided": context is not None,
                    "file_analyzed": file_path is not None,
                "url_analyzed": url is not None or bool(detected_urls),
                "detected_urls": detected_urls if detected_urls else None,
                "function_calls_made": function_calls_made if function_calls_made else None,
            }
            
            # Agregar información de grounding si está disponible
            if grounding_metadata:
                metadata["grounding_used"] = True
                if hasattr(grounding_metadata, "web_search_queries"):
                    metadata["search_queries"] = grounding_metadata.web_search_queries
                if hasattr(grounding_metadata, "grounding_chunks"):
                    chunks = grounding_metadata.grounding_chunks
                    if chunks:
                        metadata["sources"] = [
                            {"title": chunk.web.title, "uri": chunk.web.uri} 
                            for chunk in chunks if hasattr(chunk, "web")
                        ]
            
            return {
                "response": response_text,
                "session_id": session_id,
                "model_used": model,
                "tools_used": tool_names,
                "metadata": metadata
            }
            
        except Exception as e:
            error_msg = f"Error procesando mensaje: {str(e)}"
            print(f"❌ {error_msg}")
            traceback.print_exc()
            
            return {
                "response": "Lo siento, hubo un error procesando tu mensaje. Por favor intenta nuevamente.",
                "session_id": session_id or "error",
                "model_used": "none",
                "tools_used": [],
                "metadata": {"error": error_msg}
            }
    
    async def process_message_stream(
        self,
        message: str,
        user_id: str,
        session_id: Optional[str] = None,
        model_preference: Optional[str] = None,
        file_path: Optional[str] = None,
        url: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
        auth_token: Optional[str] = None,
    ):
        """
        Versión de streaming de process_message que yielde chunks en tiempo real.
        Yields: dict con {"text": str} para chunks de texto o {"done": True, "metadata": dict} al finalizar
        """
        try:
            # Crear sesión si no existe
            if not session_id:
                session_id = self.create_session()
            elif session_id not in self.sessions:
                session_id = self.create_session()
            
            session = self.sessions[session_id]
            
            # Detectar URLs
            detected_urls = self._extract_urls_from_query(message)
            if detected_urls and not url:
                url = detected_urls[0]
            
            # Elegir modelo y herramientas
            if model_preference:
                model = settings.model_pro if model_preference.lower() == "pro" else settings.model_flash
                _, tools, tool_names = self._choose_model_and_tools(message, file_path, url)
            else:
                model, tools, tool_names = self._choose_model_and_tools(message, file_path, url)
            
            session["model_used"] = model
            
            # Agregar mensaje del usuario al historial
            user_message = ChatMessage(
                role=MessageRole.USER,
                content=message,
                timestamp=datetime.now().isoformat()
            )
            session["messages"].append(user_message.model_dump())
            
            # Preparar prompt del sistema
            system_prompt = PRO_SYSTEM_PROMPT if model == settings.model_pro else FLASH_SYSTEM_PROMPT
            
            # Preparar historial de conversación
            conversation_history = []
            conversation_history.append(types.Content(
                role="user",
                parts=[types.Part.from_text(text=f"[SISTEMA] {system_prompt}")]
            ))
            
            # Agregar historial de mensajes previos
            recent_messages = session["messages"][-10:]
            for msg in recent_messages[:-1]:
                conversation_history.append(types.Content(
                    role="user" if msg["role"] == "user" else "model",
                    parts=[types.Part.from_text(text=msg["content"])]
                ))
            
            # Agregar Google Search si es necesario
            if not tools and self._needs_web_search(message):
                google_search_tool = types.Tool(google_search=types.GoogleSearch())
                tools.append(google_search_tool)
                tool_names.append("google_search")
            
            # Agregar mensaje actual
            conversation_history.append(types.Content(
                role="user",
                parts=[types.Part.from_text(text=message)]
            ))
            
            # Verificar si es consulta de portafolio
            lowered_message = message.lower()
            has_auth = bool(auth_token)
            has_keyword = any(
                keyword in lowered_message for keyword in (
                    "portafolio", "portfolio", "cartera", "inversiones",
                    "reporte", "informe", "report", "documento", "análisis"
                )
            )
            
            full_response_text = ""
            grounding_metadata = None
            function_calls_made = []
            
            if auth_token and has_keyword:
                print(f"✅ Activando flujo de análisis de portafolio STREAMING para usuario {user_id}")
                # Stream portfolio analysis
                async for chunk_data in self._process_portfolio_query_stream(
                    message=message,
                    user_id=user_id,
                    model=model,
                    conversation_history=conversation_history,
                    tools=tools,
                    auth_token=auth_token,
                    session=session,
                ):
                    if "text" in chunk_data:
                        full_response_text += chunk_data["text"]
                        yield chunk_data
            else:
                # Stream normal response
                async for chunk_data in self._generate_response_with_tools_stream(
                    model=model,
                    conversation_history=conversation_history,
                    tools=tools,
                ):
                    if "text" in chunk_data:
                        full_response_text += chunk_data["text"]
                    if "grounding_metadata" in chunk_data:
                        grounding_metadata = chunk_data["grounding_metadata"]
                    if "function_calls" in chunk_data:
                        function_calls_made = chunk_data["function_calls"]
                    yield chunk_data
            
            # Agregar respuesta al historial
            assistant_message = ChatMessage(
                role=MessageRole.ASSISTANT,
                content=full_response_text,
                timestamp=datetime.now().isoformat()
            )
            session["messages"].append(assistant_message.model_dump())
            session["last_activity"] = datetime.now().isoformat()
            
            # Construir metadata
            metadata = {
                "message_count": len(session["messages"]),
                "context_provided": context is not None,
                "file_analyzed": file_path is not None,
                "url_analyzed": url is not None or bool(detected_urls),
                "detected_urls": detected_urls if detected_urls else None,
                "function_calls_made": function_calls_made if function_calls_made else None,
                "session_id": session_id,
                "model_used": model,
                "tools_used": tool_names,
            }
            
            # Agregar información de grounding
            if grounding_metadata:
                metadata["grounding_used"] = True
                if hasattr(grounding_metadata, "web_search_queries"):
                    metadata["search_queries"] = grounding_metadata.web_search_queries
                if hasattr(grounding_metadata, "grounding_chunks"):
                    chunks = grounding_metadata.grounding_chunks
                    if chunks:
                        metadata["sources"] = [
                            {"title": chunk.web.title, "uri": chunk.web.uri}
                            for chunk in chunks if hasattr(chunk, "web")
                        ]
            
            # Señal final con metadata
            yield {"done": True, "metadata": metadata}
            
        except Exception as e:
            error_msg = f"Error procesando mensaje: {str(e)}"
            print(f"❌ {error_msg}")
            traceback.print_exc()
            yield {"error": error_msg, "done": True}
    
    async def _generate_response_with_tools(
        self, 
        model: str, 
        conversation_history: List, 
        tools: List
    ) -> Dict[str, Any]:
        """
        Generar respuesta usando herramientas (grounding, function calling).
        Maneja el ciclo completo de function calling si es necesario.
        
        Returns:
            Dict con: text, grounding_metadata, function_calls
        """
        try:
            # Configuración base
            config = types.GenerateContentConfig(
                temperature=0.7,
                top_p=0.9,
                max_output_tokens=2048,
                tools=tools if tools else None
            )
            
            # Primera llamada al modelo
            response = await self.client.aio.models.generate_content(
                model=model,
                contents=conversation_history,
                config=config
            )
            
            function_calls_made = []
            max_function_call_rounds = 5  # Límite de seguridad
            current_round = 0
            
            # Ciclo de function calling
            while current_round < max_function_call_rounds:
                # Verificar si hay llamadas a funciones
                if not response.candidates:
                    break
                
                candidate = response.candidates[0]
                if not hasattr(candidate.content, 'parts'):
                    break
                
                # Buscar function calls en las partes
                has_function_call = False
                for part in candidate.content.parts:
                    if hasattr(part, 'function_call') and part.function_call:
                        has_function_call = True
                        function_call = part.function_call
                        function_name = function_call.name
                        
                        print(f"🔧 Ejecutando función: {function_name}")
                        
                        # Ejecutar la función
                        if function_name == "get_current_datetime":
                            function_result = get_current_datetime()
                            function_calls_made.append({
                                "name": function_name,
                                "result": function_result
                            })
                            
                            # Agregar resultado al historial
                            conversation_history.append(types.Content(
                                role="model",
                                parts=[part]
                            ))
                            
                            conversation_history.append(types.Content(
                                role="user",
                                parts=[types.Part.from_function_response(
                                    name=function_name,
                                    response=function_result
                                )]
                            ))
                            
                            # Continuar la conversación
                            response = await self.client.aio.models.generate_content(
                                model=model,
                                contents=conversation_history,
                                config=config
                            )
                            
                            break  # Salir del loop de parts
                        else:
                            print(f"⚠️ Función desconocida: {function_name}")
                
                if not has_function_call:
                    break  # No hay más llamadas a funciones
                
                current_round += 1
            
            # Extraer texto y metadata
            response_text = ""
            grounding_metadata = None
            
            if response and response.candidates:
                candidate = response.candidates[0]
                
                # Obtener texto - con manejo robusto de None
                if hasattr(response, 'text') and response.text is not None:
                    response_text = response.text.strip()
                elif hasattr(candidate, 'content') and hasattr(candidate.content, 'parts'):
                    # Intentar extraer texto de las partes
                    text_parts = []
                    for part in candidate.content.parts:
                        if hasattr(part, 'text') and part.text:
                            text_parts.append(part.text)
                    if text_parts:
                        response_text = " ".join(text_parts).strip()
                
                # Obtener grounding metadata
                if hasattr(candidate, 'grounding_metadata'):
                    grounding_metadata = candidate.grounding_metadata
                    
                    # Agregar citaciones al texto si hay grounding
                    if grounding_metadata and response_text:
                        print("📚 Agregando citaciones al texto...")
                        response_text = self._add_citations_to_text(response_text, grounding_metadata)
            
            if not response_text:
                response_text = "No pude generar una respuesta. Por favor intenta reformular tu pregunta."
            
            return {
                "text": response_text,
                "grounding_metadata": grounding_metadata,
                "function_calls": function_calls_made
            }
                
        except Exception as e:
            print(f"❌ Error generando respuesta con herramientas: {e}")
            traceback.print_exc()
            return {
                "text": f"Error generando respuesta: {str(e)}",
                "grounding_metadata": None,
                "function_calls": []
            }
    
    async def _generate_response_with_tools_stream(
        self,
        model: str,
        conversation_history: List,
        tools: List
    ):
        """
        Versión de streaming de _generate_response_with_tools.
        Yields: dict con {"text": str} para chunks o {"grounding_metadata": obj, "function_calls": list} al final
        """
        try:
            config = types.GenerateContentConfig(
                temperature=0.7,
                top_p=0.9,
                max_output_tokens=2048,
                tools=tools if tools else None
            )
            
            # Usar generate_content_stream para streaming
            response_stream = await self.client.aio.models.generate_content_stream(
                model=model,
                contents=conversation_history,
                config=config
            )
            
            grounding_metadata = None
            full_text = ""
            
            async for chunk in response_stream:
                if hasattr(chunk, 'text') and chunk.text:
                    full_text += chunk.text
                    yield {"text": chunk.text}
                
                # Capturar metadata del último chunk
                if chunk.candidates and hasattr(chunk.candidates[0], 'grounding_metadata'):
                    grounding_metadata = chunk.candidates[0].grounding_metadata
            
            # Agregar citaciones si hay grounding (al final)
            if grounding_metadata and full_text:
                print("📚 Agregando citaciones al texto...")
                cited_text = self._add_citations_to_text(full_text, grounding_metadata)
                # Enviar solo la diferencia (citaciones)
                if cited_text != full_text:
                    diff = cited_text[len(full_text):]
                    yield {"text": diff}
            
            # Enviar metadata al final
            yield {
                "grounding_metadata": grounding_metadata,
                "function_calls": []
            }
            
        except Exception as e:
            print(f"❌ Error en streaming: {e}")
            traceback.print_exc()
            yield {"text": f"Error generando respuesta: {str(e)}"}
    
    async def _process_portfolio_query_stream(
        self,
        message: str,
        user_id: str,
        model: str,
        conversation_history: List,
        tools: List,
        auth_token: Optional[str],
        session: Dict[str, Any],
    ):
        """
        Versión de streaming de _process_portfolio_query.
        Yields: dict con {"text": str} para chunks de texto
        """
        try:
            print(f"\n🔍 Detectada consulta de portafolio para usuario {user_id}")
            
            # Paso 1: Listar archivos (incluyendo imágenes y PDFs)
            files = await self._backend_list_files(
                user_id=user_id,
                auth_token=auth_token,
                extensions=["json", "md", "png", "jpg", "jpeg", "gif", "webp", "pdf"],
            )
            
            if not files:
                yield {"text": "No se encontraron archivos de portafolio para analizar."}
                return
            
            # Filtrar archivos
            excluded_extensions = ('.html', '-.emptyFolder', '.gitkeep')
            filtered_files = [
                f for f in files
                if not any(f.get("name", "").endswith(ext) for ext in excluded_extensions)
            ]
            
            if not filtered_files:
                yield {"text": "No hay archivos relevantes en tu portafolio."}
                return
            
            print(f"📁 Encontrados {len(filtered_files)} archivos relevantes")
            
            # Paso 2: Seleccionar archivos con Gemini
            selected_files = await self._select_files_via_gemini(message, filtered_files, model)
            
            if not selected_files:
                yield {"text": "No pude identificar archivos específicos para tu consulta. ¿Podrías ser más específico?"}
                return
            
            print(f"✅ Gemini seleccionó {len(selected_files)} archivo(s)")
            
            # Paso 3: Descargar archivos
            final_contents = []
            total_size_bytes = 0
            
            for file_info in selected_files:
                filename = file_info.get("nombre_archivo")
                if not filename:
                    continue
                
                try:
                    file_bytes, content_type = await self._backend_download_file(
                        user_id=user_id,
                        filename=filename,
                        auth_token=auth_token
                    )
                    
                    total_size_bytes += len(file_bytes)
                    filename_lower = filename.lower()
                    
                    # Procesar según tipo
                    if filename_lower.endswith('.json'):
                        json_content = file_bytes.decode('utf-8')
                        final_contents.append(json_content)
                        print(f"   ✅ Añadido JSON: {filename} ({len(file_bytes)/(1024*1024):.2f} MB)")
                    
                    elif filename_lower.endswith('.md'):
                        md_content = file_bytes.decode('utf-8')
                        final_contents.append(md_content)
                        print(f"   ✅ Añadido MD: {filename} ({len(file_bytes)/(1024*1024):.2f} MB)")
                    
                    elif filename_lower.endswith(('.png', '.jpg', '.jpeg', '.gif', '.webp')):
                        # Imágenes: usar inline data
                        mime_type = content_type or 'image/png'
                        if filename_lower.endswith('.jpg') or filename_lower.endswith('.jpeg'):
                            mime_type = 'image/jpeg'
                        elif filename_lower.endswith('.gif'):
                            mime_type = 'image/gif'
                        elif filename_lower.endswith('.webp'):
                            mime_type = 'image/webp'
                        
                        final_contents.append({
                            "inline_data": {
                                "mime_type": mime_type,
                                "data": base64.b64encode(file_bytes).decode('utf-8')
                            }
                        })
                        print(f"   ✅ Añadida imagen: {filename} ({len(file_bytes)/(1024*1024):.2f} MB)")
                    
                    elif filename_lower.endswith('.pdf'):
                        # PDF: usar inline data con base64
                        final_contents.append({
                            "inline_data": {
                                "mime_type": "application/pdf",
                                "data": base64.b64encode(file_bytes).decode('utf-8')
                            }
                        })
                        print(f"   ✅ Añadido PDF: {filename} ({len(file_bytes)/(1024*1024):.2f} MB)")
                
                except Exception as e:
                    print(f"⚠️ Error descargando {filename}: {e}")
                    continue
            
            if not final_contents:
                yield {"text": "No pude descargar los archivos necesarios para el análisis."}
                return
            
            # Agregar el prompt del usuario
            final_contents.append(message)
            
            total_size_mb = total_size_bytes / (1024 * 1024)
            print(f"\n📤 Enviando {len(final_contents)} elementos a Gemini ({total_size_mb:.2f} MB total)...")
            
            # Paso 4: Enviar a Gemini con streaming
            try:
                response_stream = await self.client.aio.models.generate_content_stream(
                    model=model,
                    contents=final_contents
                )
                
                chunk_count = 0
                async for chunk in response_stream:
                    chunk_count += 1
                    if hasattr(chunk, 'text') and chunk.text:
                        yield {"text": chunk.text}
                        
                        # Log cada 10 chunks
                        if chunk_count % 10 == 0:
                            print(f"   📝 Enviados {chunk_count} chunks al cliente...")
                
                print(f"✅ Análisis streaming completado ({chunk_count} chunks totales)")
            
            except Exception as e:
                error_msg = f"Error en el análisis: {str(e)}"
                print(f"❌ {error_msg}")
                yield {"text": f"\n\nLo siento, ocurrió un error durante el análisis: {error_msg}"}
        
        except Exception as e:
            error_msg = f"Error en consulta de portafolio: {str(e)}"
            print(f"❌ {error_msg}")
            traceback.print_exc()
            yield {"text": f"Lo siento, ocurrió un error procesando tu consulta de portafolio."}
    
    def close_session(self, session_id: str) -> bool:
        """Cerrar sesión"""
        if session_id in self.sessions:
            del self.sessions[session_id]
            self.active_sessions = max(0, self.active_sessions - 1)
            return True
        return False
    
    def list_sessions(self) -> List[Dict[str, Any]]:
        """Listar todas las sesiones activas"""
        return [
            {
                "session_id": session_id,
                "created_at": session["created_at"],
                "message_count": len(session["messages"]),
                "model_used": session["model_used"],
                "last_activity": session["last_activity"]
            }
            for session_id, session in self.sessions.items()
        ]

# Instancia global del servicio
chat_service = ChatAgentService()