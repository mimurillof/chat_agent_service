"""
Aplicación FastAPI para el servicio independiente del agente de chat
"""
from fastapi import FastAPI, HTTPException, Depends, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import uvicorn
import uuid
from datetime import datetime
from typing import List, Dict, Any

from config import settings
from models import (
    ChatRequest, ChatResponse, HealthResponse, SessionInfo, 
    ErrorResponse, MessageRole,
    PortfolioReportRequest, PortfolioReportResponse
)
from agent_service import chat_service

# Almacenamiento en memoria para estados de tareas
# Con 1 worker de Gunicorn, todos los requests comparten la misma memoria
task_statuses: Dict[str, Dict[str, Any]] = {}

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
            "generar_informe_portafolio": "/acciones/generar_informe_portafolio",
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

async def process_report_generation_task(task_id: str, request: PortfolioReportRequest):
    """
    Función auxiliar que procesa la generación del reporte en background.
    Actualiza el estado en task_statuses.
    """
    try:
        # Actualizar estado a "processing"
        task_statuses[task_id]["status"] = "processing"
        task_statuses[task_id]["updated_at"] = datetime.now().isoformat()
        
        # Generar reporte
        result = await chat_service.ejecutar_generacion_informe_portafolio(request)
        
        if isinstance(result, dict) and result.get("error"):
            # Error en la generación
            task_statuses[task_id]["status"] = "error"
            task_statuses[task_id]["error"] = result.get("detail") or result.get("error")
            task_statuses[task_id]["updated_at"] = datetime.now().isoformat()
        else:
            # Éxito
            task_statuses[task_id]["status"] = "completed"
            task_statuses[task_id]["result"] = result
            task_statuses[task_id]["updated_at"] = datetime.now().isoformat()
            task_statuses[task_id]["completed_at"] = datetime.now().isoformat()
    
    except Exception as e:
        # Error inesperado
        task_statuses[task_id]["status"] = "error"
        task_statuses[task_id]["error"] = str(e)
        task_statuses[task_id]["updated_at"] = datetime.now().isoformat()


@app.post("/acciones/generar_informe_portafolio/start")
async def generar_informe_portafolio_start(
    request: PortfolioReportRequest,
    background_tasks: BackgroundTasks
):
    """
    Inicia la generación asíncrona de un informe de portafolio.
    Retorna inmediatamente con un task_id para hacer polling.
    """
    # Generar ID único para la tarea
    task_id = str(uuid.uuid4())
    
    # Crear estado inicial
    task_statuses[task_id] = {
        "task_id": task_id,
        "status": "pending",
        "created_at": datetime.now().isoformat(),
        "updated_at": datetime.now().isoformat(),
        "model_preference": request.model_preference,
    }
    
    # Iniciar procesamiento en background
    background_tasks.add_task(
        process_report_generation_task,
        task_id,
        request
    )
    
    return {
        "task_id": task_id,
        "status": "pending",
        "message": "Generación de informe iniciada. Use el endpoint /acciones/generar_informe_portafolio/status/{task_id} para verificar el progreso.",
        "poll_url": f"/acciones/generar_informe_portafolio/status/{task_id}",
        "created_at": task_statuses[task_id]["created_at"]
    }


@app.get("/acciones/generar_informe_portafolio/status/{task_id}")
async def generar_informe_portafolio_status(task_id: str):
    """
    Obtiene el estado actual de una tarea de generación de informe.
    Estados posibles: pending, processing, completed, error
    """
    if task_id not in task_statuses:
        raise HTTPException(
            status_code=404,
            detail=f"Tarea con ID {task_id} no encontrada"
        )
    
    status_info = task_statuses[task_id]
    
    # Respuesta básica para todos los estados
    response = {
        "task_id": status_info["task_id"],
        "status": status_info["status"],
        "created_at": status_info["created_at"],
        "updated_at": status_info["updated_at"],
    }
    
    # Agregar información específica según el estado
    if status_info["status"] == "completed":
        response["result"] = status_info.get("result")
        response["completed_at"] = status_info.get("completed_at")
    elif status_info["status"] == "error":
        response["error"] = status_info.get("error")
    elif status_info["status"] in ["pending", "processing"]:
        response["message"] = "Informe en proceso de generación. Vuelva a consultar en unos segundos."
    
    return response


@app.post("/acciones/generar_informe_portafolio", response_model=PortfolioReportResponse)
async def generar_informe_portafolio(request: PortfolioReportRequest):
    """
    Endpoint: genera informe de análisis de portafolio con salida JSON estructurada.
    NOTA: Este endpoint es síncrono y puede dar timeout. Se recomienda usar /start y /status
    Requiere user_id para acceder a los archivos del usuario en Supabase.
    """
    try:
        result = await chat_service.ejecutar_generacion_informe_portafolio(request)
        if isinstance(result, dict) and result.get("error"):
            raise HTTPException(status_code=500, detail=result.get("detail") or result.get("error"))
        return PortfolioReportResponse(**result)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error generando informe de portafolio: {str(e)}")

@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """Endpoint principal para el chat - requiere user_id"""
    try:
        result = await chat_service.process_message(
            message=request.message,
            user_id=request.user_id,  # ✅ Pasar user_id al servicio
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