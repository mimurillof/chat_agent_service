"""
Aplicación FastAPI para el servicio independiente del agente de chat
"""
from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import uvicorn
from typing import List

from config import settings
from models import (
    ChatRequest, ChatResponse, HealthResponse, SessionInfo, 
    ErrorResponse, MessageRole
)
from agent_service import chat_service

# Crear aplicación FastAPI
app = FastAPI(
    title=settings.service_name,
    version=settings.service_version,
    description="Servicio independiente del agente de chat financiero Horizon"
)

# Configurar CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/", response_model=dict)
async def root():
    """Endpoint raíz"""
    return {
        "service": settings.service_name,
        "version": settings.service_version,
        "status": "running",
        "endpoints": {
            "health": "/health",
            "chat": "/chat",
            "sessions": "/sessions",
            "docs": "/docs"
        }
    }

@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check del servicio"""
    try:
        status = chat_service.get_health_status()
        return HealthResponse(**status)
    except Exception as e:
        raise HTTPException(
            status_code=503, 
            detail=f"Servicio no disponible: {str(e)}"
        )

@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """Endpoint principal para el chat"""
    try:
        result = await chat_service.process_message(
            message=request.message,
            session_id=request.session_id,
            model_preference=request.model_preference,
            file_path=request.file_path,
            url=request.url,
            context=request.context
        )
        
        return ChatResponse(**result)
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error procesando chat: {str(e)}"
        )

@app.post("/sessions/create", response_model=dict)
async def create_session():
    """Crear nueva sesión de chat"""
    try:
        session_id = chat_service.create_session()
        return {"session_id": session_id, "status": "created"}
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error creando sesión: {str(e)}"
        )

@app.get("/sessions", response_model=List[SessionInfo])
async def list_sessions():
    """Listar sesiones activas"""
    try:
        sessions = chat_service.list_sessions()
        return [SessionInfo(**session) for session in sessions]
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error listando sesiones: {str(e)}"
        )

@app.get("/sessions/{session_id}", response_model=SessionInfo)
async def get_session(session_id: str):
    """Obtener información de una sesión específica"""
    try:
        session_info = chat_service.get_session_info(session_id)
        if not session_info:
            raise HTTPException(
                status_code=404,
                detail="Sesión no encontrada"
            )
        return SessionInfo(**session_info)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error obteniendo sesión: {str(e)}"
        )

@app.delete("/sessions/{session_id}", response_model=dict)
async def close_session(session_id: str):
    """Cerrar una sesión específica"""
    try:
        success = chat_service.close_session(session_id)
        if not success:
            raise HTTPException(
                status_code=404,
                detail="Sesión no encontrada"
            )
        return {"session_id": session_id, "status": "closed"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error cerrando sesión: {str(e)}"
        )

@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    """Manejador global de excepciones"""
    return JSONResponse(
        status_code=500,
        content=ErrorResponse(
            error="Error interno del servidor",
            detail=str(exc)
        ).model_dump()
    )

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host=settings.service_host,
        port=settings.service_port,
        reload=True,
        log_level=settings.log_level.lower()
    )