from typing import Optional, Dict, Any, List
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