from typing import Optional, Dict, Any, List, Literal, Union
from pydantic import BaseModel, Field
from enum import Enum

class MessageRole(str, Enum):
    """Roles de mensajes en el chat"""
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"

class ChatMessage(BaseModel):
    """Modelo para un mensaje de chat"""
    role: MessageRole
    content: str
    timestamp: Optional[str] = None

class ChatRequest(BaseModel):
    """Modelo para solicitud de chat"""
    message: str = Field(..., description="Mensaje del usuario")
    user_id: str = Field(..., description="ID del usuario autenticado (requerido)")
    auth_token: Optional[str] = Field(
        None,
        description=(
            "Token JWT del usuario (Bearer). Si se suministra, el servicio lo reenviará al backend."
        ),
    )
    session_id: Optional[str] = Field(None, description="ID de sesión para mantener contexto")
    model_preference: Optional[str] = Field(None, description="Preferencia de modelo (flash/pro)")
    file_path: Optional[str] = Field(None, description="Ruta a archivo para análisis")
    url: Optional[str] = Field(None, description="URL para análisis")
    context: Optional[Dict[str, Any]] = Field(None, description="Contexto adicional")

class ChatResponse(BaseModel):
    """Modelo para respuesta de chat"""
    response: str = Field(..., description="Respuesta del agente")
    session_id: str = Field(..., description="ID de sesión")
    model_used: str = Field(..., description="Modelo utilizado")
    tools_used: List[str] = Field(default_factory=list, description="Herramientas utilizadas")
    metadata: Optional[Dict[str, Any]] = Field(None, description="Metadatos adicionales")

class HealthResponse(BaseModel):
    """Modelo para respuesta de health check"""
    status: str
    service: str
    version: str
    models_available: List[str]
    active_sessions: int

class SessionInfo(BaseModel):
    """Información de sesión"""
    session_id: str
    created_at: str
    message_count: int
    model_used: str
    last_activity: str

class ErrorResponse(BaseModel):
    """Modelo para respuestas de error"""
    error: str
    detail: Optional[str] = None
    error_code: Optional[str] = None

# ====== Esquema de informe de análisis de portafolio (salida JSON estructurada) ======

class ImageTransform(BaseModel):
    width: Optional[int] = None
    height: Optional[int] = None
    quality: Optional[int] = Field(None, ge=20, le=100)
    resize: Optional[Literal["cover", "contain", "fill"]] = None
    format: Optional[Literal["origin", "avif"]] = None


class SupabaseImage(BaseModel):
    bucket: str
    path: str
    public: Optional[bool] = None
    expires_in: Optional[int] = None
    use_url: Optional[bool] = None
    transform: Optional[ImageTransform] = None


class KeyValueItem(BaseModel):
    """Item para listas key-value"""
    key: str
    value: str


class ContentItem(BaseModel):
    """Elemento de contenido del informe - soporta múltiples tipos"""
    type: str  # header1, header2, header3, paragraph, spacer, page_break, table, list, key_value_list, image
    text: Optional[str] = None  # Para headers y paragraphs
    style: Optional[str] = None  # italic, bold, centered, disclaimer, etc.
    height: Optional[Union[float, int]] = None  # Para spacers y images
    path: Optional[str] = None  # Para images (solo nombre del archivo)
    caption: Optional[str] = None  # Para images
    width: Optional[Union[float, int]] = None  # Para images
    headers: Optional[List[str]] = None  # Para tables
    rows: Optional[List[List[Any]]] = None  # Para tables
    items: Optional[List[Union[str, KeyValueItem]]] = None  # Para lists y key_value_lists
    supabase: Optional[SupabaseImage] = None  # Deprecated - mantenido por compatibilidad


class DocumentMetadata(BaseModel):
    """Metadatos del documento del informe"""
    title: Optional[str] = None
    author: Optional[str] = None  # Debe ser "Horizon Agent"
    subject: Optional[str] = None


class Report(BaseModel):
    fileName: str
    document: Optional[DocumentMetadata] = None
    content: List[ContentItem]


class PortfolioReportRequest(BaseModel):
    """Solicitud para generar informe de análisis de portafolio mediante botón"""
    user_id: str = Field(..., description="ID del usuario autenticado (requerido)")
    session_id: Optional[str] = Field(None, description="ID de sesión para el agente")
    model_preference: Optional[str] = Field(None, description="flash | pro")
    context: Optional[Dict[str, Any]] = Field(None, description="Datos/indicadores/imagenes relevantes para el informe")


class PortfolioReportResponse(BaseModel):
    report: Report
    session_id: str
    model_used: str
    metadata: Optional[Dict[str, Any]] = None


# ====== Modelos para Alertas y Oportunidades ======

class AlertsAnalysisRequest(BaseModel):
    """Solicitud para generar análisis de alertas y oportunidades"""
    user_id: str = Field(..., description="ID del usuario autenticado (requerido)")
    session_id: Optional[str] = Field(None, description="ID de sesión para el agente")
    model_preference: Optional[str] = Field(None, description="flash | pro")
    auth_token: Optional[str] = Field(None, description="Token JWT para autenticación")


class AlertsAnalysisResponse(BaseModel):
    """Respuesta del análisis de alertas y oportunidades"""
    analysis: str = Field(..., description="Análisis generado en formato Markdown")
    session_id: str = Field(..., description="ID de sesión")
    model_used: str = Field(..., description="Modelo utilizado")
    metadata: Optional[Dict[str, Any]] = None


# ====== Modelos para Proyecciones Futuras ======

class FutureProjectionsRequest(BaseModel):
    """Solicitud para generar proyecciones futuras del portafolio"""
    user_id: str = Field(..., description="ID del usuario autenticado (requerido)")
    session_id: Optional[str] = Field(None, description="ID de sesión para el agente")
    model_preference: Optional[str] = Field(None, description="flash | pro")
    auth_token: Optional[str] = Field(None, description="Token JWT para autenticación")


class FutureProjectionsResponse(BaseModel):
    """Respuesta del análisis de proyecciones futuras"""
    projections: str = Field(..., description="Proyecciones generadas en formato Markdown")
    session_id: str = Field(..., description="ID de sesión")
    model_used: str = Field(..., description="Modelo utilizado")
    metadata: Optional[Dict[str, Any]] = None


# ====== Modelos para Análisis de Rendimiento ======

class PerformanceAnalysisRequest(BaseModel):
    """Solicitud para generar análisis de rendimiento del portafolio"""
    user_id: str = Field(..., description="ID del usuario autenticado (requerido)")
    session_id: Optional[str] = Field(None, description="ID de sesión para el agente")
    model_preference: Optional[str] = Field(None, description="flash | pro")
    auth_token: Optional[str] = Field(None, description="Token JWT para autenticación")


class PerformanceAnalysisResponse(BaseModel):
    """Respuesta del análisis de rendimiento"""
    analysis: str = Field(..., description="Análisis de rendimiento generado en formato Markdown")
    session_id: str = Field(..., description="ID de sesión")
    model_used: str = Field(..., description="Modelo utilizado")
    metadata: Optional[Dict[str, Any]] = None
