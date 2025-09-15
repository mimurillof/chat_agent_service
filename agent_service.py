# -*- coding: utf-8 -*-
"""
Servicio independiente del agente de chat Horizon
Adaptado para funcionar como microservicio separado
"""
import os
import uuid
import traceback
from datetime import datetime
from typing import Optional, Dict, Any, List
from config import settings
from models import ChatMessage, MessageRole

try:
    from google import genai
    from google.genai import types
    
    # Configurar API key
    api_key = settings.get_api_key()
    if not api_key:
        raise ValueError("GEMINI_API_KEY o GOOGLE_API_KEY no configurada")
    
    if not os.getenv("GEMINI_API_KEY"):
        os.environ["GEMINI_API_KEY"] = api_key
    
    client = genai.Client()
    
except Exception as e:
    print(f"❌ Error configurando Gemini: {e}")
    client = None

# Prompts del sistema
FLASH_SYSTEM_PROMPT = """
Eres un asistente financiero rápido y eficiente especializado en:
- Consultas generales del mercado y definiciones financieras
- Búsquedas web de información actualizada 
- Análisis de contenido de URLs
- Resúmenes concisos y respuestas directas

Utiliza las herramientas disponibles cuando sea necesario y proporciona respuestas precisas y útiles.
"""

PRO_SYSTEM_PROMPT = """
Eres un analista financiero experto especializado en análisis profundo de documentos.
- Analiza documentos financieros con detalle crítico
- Identifica riesgos, oportunidades y patrones
- Proporciona insights accionables y fundamentados
- Mantén una perspectiva crítica y objetiva

Enfócate en la calidad del análisis sobre la velocidad.
"""

class ChatAgentService:
    """Servicio independiente del agente de chat"""
    
    def __init__(self):
        self.client = client
        self.sessions: Dict[str, Dict] = {}
        self.active_sessions = 0
        
        if not self.client:
            raise Exception("Cliente Gemini no disponible")
    
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
                "web_search", 
                "url_analysis",
                "document_analysis",
                "real_time_data"
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
        """Elegir modelo y herramientas basado en el tipo de consulta"""
        
        # Si hay archivo local, usar Pro para análisis profundo
        if file_path:
            return settings.model_pro, []
        
        # Si hay URL o necesita búsqueda web, usar Flash con herramientas
        if url or self._needs_web_search(query):
            tools = []
            if self._has_google_search():
                tools.append("Google Search")
            return settings.model_flash, tools
        
        # Para consultas generales, usar Flash
        return settings.model_flash, []
    
    def _needs_web_search(self, query: str) -> bool:
        """Determinar si la consulta necesita búsqueda web"""
        web_keywords = [
            "precio actual", "cotización", "últimas noticias", "hoy", "ahora",
            "precio de", "valor actual", "mercado actual", "tendencia actual",
            "noticias de", "actualización", "estado actual"
        ]
        query_lower = query.lower()
        return any(keyword in query_lower for keyword in web_keywords)
    
    def _has_google_search(self) -> bool:
        """Verificar si Google Search está disponible"""
        # Por ahora retornamos False, se puede implementar más tarde
        return False
    
    async def process_message(
        self, 
        message: str, 
        session_id: Optional[str] = None,
        model_preference: Optional[str] = None,
        file_path: Optional[str] = None,
        url: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Procesar mensaje del usuario"""
        
        try:
            # Crear sesión si no existe
            if not session_id:
                session_id = self.create_session()
            elif session_id not in self.sessions:
                session_id = self.create_session()
            
            session = self.sessions[session_id]
            
            # Elegir modelo y herramientas
            if model_preference:
                model = settings.model_pro if model_preference.lower() == "pro" else settings.model_flash
                tools = []
            else:
                model, tools = self._choose_model_and_tools(message, file_path, url)
            
            session["model_used"] = model
            
            # Agregar mensaje del usuario al historial
            user_message = ChatMessage(
                role=MessageRole.USER,
                content=message,
                timestamp=datetime.now().isoformat()
            )
            session["messages"].append(user_message.model_dump())
            
            # Preparar configuración para Gemini
            config = types.GenerateContentConfig(
                temperature=0.7,
                top_p=0.9,
                max_output_tokens=2048,
            )
            
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
            
            # Agregar mensaje actual
            conversation_history.append(types.Content(
                role="user",
                parts=[types.Part.from_text(text=message)]
            ))
            
            # Generar respuesta
            response = await self._generate_response(model, conversation_history, config)
            
            # Agregar respuesta al historial
            assistant_message = ChatMessage(
                role=MessageRole.ASSISTANT,
                content=response,
                timestamp=datetime.now().isoformat()
            )
            session["messages"].append(assistant_message.model_dump())
            session["last_activity"] = datetime.now().isoformat()
            
            return {
                "response": response,
                "session_id": session_id,
                "model_used": model,
                "tools_used": tools,
                "metadata": {
                    "message_count": len(session["messages"]),
                    "context_provided": context is not None,
                    "file_analyzed": file_path is not None,
                    "url_analyzed": url is not None
                }
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
    
    async def _generate_response(self, model: str, conversation_history: List, config) -> str:
        """Generar respuesta usando el modelo especificado"""
        try:
            response = await self.client.aio.models.generate_content(
                model=model,
                contents=conversation_history,
                config=config
            )
            
            if response and response.text:
                return response.text.strip()
            else:
                return "No pude generar una respuesta. Por favor intenta reformular tu pregunta."
                
        except Exception as e:
            print(f"❌ Error generando respuesta: {e}")
            return f"Error generando respuesta: {str(e)}"
    
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