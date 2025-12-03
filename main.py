"""
Aplicación FastAPI para el servicio independiente del agente de chat
"""
from fastapi import FastAPI, HTTPException, Depends, BackgroundTasks, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
import uvicorn
import uuid
import json
import asyncio
import logging
from datetime import datetime
from typing import List, Dict, Any, AsyncGenerator
from contextlib import asynccontextmanager

# APScheduler imports
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
import pytz

from config import settings
from models import (
    ChatRequest, ChatResponse, HealthResponse, SessionInfo,
    ErrorResponse, MessageRole,
    PortfolioReportRequest, PortfolioReportResponse,
    AlertsAnalysisRequest, AlertsAnalysisResponse,
    FutureProjectionsRequest, FutureProjectionsResponse,
    PerformanceAnalysisRequest, PerformanceAnalysisResponse,
    DailyWeeklySummaryRequest, DailyWeeklySummaryResponse
)
from agent_service import chat_service

# Configurar logger
logger = logging.getLogger(__name__)

# Almacenamiento en memoria para estados de tareas
# Con 1 worker de Gunicorn, todos los requests comparten la misma memoria
task_statuses: Dict[str, Dict[str, Any]] = {}

# Scheduler global
scheduler: AsyncIOScheduler = None


# ============================================
# SCHEDULER: Tarea programada de resumen diario
# ============================================

async def scheduled_daily_summary_for_all_users():
    """
    Tarea programada que se ejecuta de lunes a viernes a las 9:00 AM hora Nueva York.
    Genera el resumen diario/semanal para todos los usuarios registrados.
    
    NOTA: Esta es una implementación básica. En producción, deberías:
    1. Obtener la lista de usuarios activos desde la base de datos
    2. Obtener tokens de servicio para cada usuario (o usar service role)
    3. Implementar manejo de errores y reintentos por usuario
    """
    logger.info("🕘 [SCHEDULER] Iniciando tarea programada de resumen diario/semanal")
    
    # En este punto, deberías obtener la lista de usuarios desde el backend
    # Por ahora, esta tarea se activará pero requerirá que los usuarios
    # tengan sus datos configurados para funcionar
    
    # Para implementación completa, podrías:
    # 1. Llamar a un endpoint del backend que devuelva usuarios activos
    # 2. Iterar sobre cada usuario y ejecutar el resumen
    
    logger.info("🕘 [SCHEDULER] Tarea de resumen programado completada")
    
    # Ejemplo de cómo se invocaría para un usuario específico:
    # request = DailyWeeklySummaryRequest(
    #     user_id="user_123",
    #     session_id=None,
    #     model_preference="flash",
    #     auth_token="SERVICE_TOKEN"  # Token de servicio
    # )
    # result = await chat_service.ejecutar_resumen_diario_semanal(request)


def setup_scheduler():
    """Configura el scheduler APScheduler con la zona horaria de Nueva York."""
    global scheduler
    
    # Zona horaria de Nueva York
    ny_timezone = pytz.timezone('America/New_York')
    
    # Crear scheduler
    scheduler = AsyncIOScheduler(timezone=ny_timezone)
    
    # Programar tarea: Lunes a Viernes a las 9:00 AM hora NY
    scheduler.add_job(
        scheduled_daily_summary_for_all_users,
        trigger=CronTrigger(
            day_of_week='mon-fri',  # Lunes a Viernes
            hour=9,                  # 9:00 AM
            minute=0,
            timezone=ny_timezone
        ),
        id='daily_summary_job',
        name='Resumen Diario/Semanal Programado',
        replace_existing=True
    )
    
    logger.info("📅 [SCHEDULER] Configurado para ejecutar L-V a las 9:00 AM hora Nueva York")
    return scheduler


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Maneja el ciclo de vida de la aplicación (startup/shutdown)."""
    # Startup
    logger.info("🚀 Iniciando aplicación y scheduler...")
    scheduler = setup_scheduler()
    scheduler.start()
    logger.info("✅ Scheduler iniciado correctamente")
    
    yield
    
    # Shutdown
    logger.info("🛑 Deteniendo scheduler...")
    if scheduler and scheduler.running:
        scheduler.shutdown(wait=False)
    logger.info("✅ Scheduler detenido")


# Crear aplicación FastAPI con lifespan
app = FastAPI(
    title=settings.service_name,
    version=settings.service_version,
    description="Servicio independiente del agente de chat financiero Horizon",
    lifespan=lifespan
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


async def process_alerts_analysis_task(task_id: str, request: AlertsAnalysisRequest):
    """
    Función auxiliar que procesa el análisis de alertas en background.
    Actualiza el estado en task_statuses.
    """
    try:
        # Actualizar estado a "processing"
        task_statuses[task_id]["status"] = "processing"
        task_statuses[task_id]["updated_at"] = datetime.now().isoformat()
        
        # Generar análisis de alertas
        result = await chat_service.ejecutar_analisis_alertas(request)
        
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


async def process_future_projections_task(task_id: str, request: FutureProjectionsRequest):
    """
    Función auxiliar que procesa las proyecciones futuras en background.
    Actualiza el estado en task_statuses.
    """
    try:
        # Actualizar estado a "processing"
        task_statuses[task_id]["status"] = "processing"
        task_statuses[task_id]["updated_at"] = datetime.now().isoformat()
        
        # Generar proyecciones
        result = await chat_service.ejecutar_proyecciones_futuras(request)
        
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

@app.post("/chat")
async def chat(
    request: ChatRequest,
    authorization: str | None = Header(default=None, alias="Authorization"),
):
    """Endpoint principal para el chat con streaming - requiere user_id"""
    try:
        bearer_token = None
        if authorization and authorization.lower().startswith("bearer "):
            bearer_token = authorization.split(" ", 1)[1]
        elif request.auth_token:
            bearer_token = request.auth_token

        async def event_generator() -> AsyncGenerator[str, None]:
            """Genera eventos SSE para streaming"""
            try:
                # Procesar mensaje con streaming
                async for chunk in chat_service.process_message_stream(
                    message=request.message,
                    user_id=request.user_id,
                    session_id=request.session_id,
                    model_preference=request.model_preference,
                    file_path=request.file_path,
                    url=request.url,
                    context=request.context,
                    auth_token=bearer_token,
                ):
                    # Formato SSE: data: {json}\n\n
                    yield f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n"
                
                # Señal de finalización
                yield f"data: {json.dumps({'done': True})}\n\n"
            
            except Exception as e:
                error_data = {
                    "error": str(e),
                    "done": True
                }
                yield f"data: {json.dumps(error_data)}\n\n"
        
        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",  # Nginx: disable buffering
            }
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error procesando chat: {str(e)}"
        )

@app.post("/acciones/analisis_alertas/start")
async def analisis_alertas_start(
    request: AlertsAnalysisRequest,
    background_tasks: BackgroundTasks,
    authorization: str | None = Header(default=None, alias="Authorization"),
):
    """
    Inicia el análisis asíncrono de alertas y oportunidades.
    Retorna inmediatamente con un task_id para hacer polling.
    """
    # Extraer token de autorización si está presente
    bearer_token = None
    if authorization and authorization.lower().startswith("bearer "):
        bearer_token = authorization.split(" ", 1)[1]
    elif request.auth_token:
        bearer_token = request.auth_token
    
    # Actualizar el token en el request
    request.auth_token = bearer_token
    
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
        process_alerts_analysis_task,
        task_id,
        request
    )
    
    return {
        "task_id": task_id,
        "status": "pending",
        "message": "Análisis de alertas iniciado. Use el endpoint /acciones/analisis_alertas/status/{task_id} para verificar el progreso.",
        "poll_url": f"/acciones/analisis_alertas/status/{task_id}",
        "created_at": task_statuses[task_id]["created_at"]
    }


@app.get("/acciones/analisis_alertas/status/{task_id}")
async def analisis_alertas_status(task_id: str):
    """
    Obtiene el estado actual de una tarea de análisis de alertas.
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
        response["message"] = "Análisis en proceso. Vuelva a consultar en unos segundos."
    
    return response


@app.post("/acciones/proyecciones_futuras/start")
async def proyecciones_futuras_start(
    request: FutureProjectionsRequest,
    background_tasks: BackgroundTasks,
    authorization: str | None = Header(default=None, alias="Authorization"),
):
    """
    Inicia el análisis asíncrono de proyecciones futuras.
    Retorna inmediatamente con un task_id para hacer polling.
    """
    # Extraer token de autorización si está presente
    bearer_token = None
    if authorization and authorization.lower().startswith("bearer "):
        bearer_token = authorization.split(" ", 1)[1]
    elif request.auth_token:
        bearer_token = request.auth_token
    
    # Actualizar el token en el request
    request.auth_token = bearer_token
    
    # Generar task_id único
    task_id = f"proj_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{id(request)}"
    
    # Inicializar estado de la tarea
    task_statuses[task_id] = {
        "task_id": task_id,
        "status": "pending",
        "created_at": datetime.now().isoformat(),
        "updated_at": datetime.now().isoformat(),
    }
    
    # Agregar tarea en background
    background_tasks.add_task(process_future_projections_task, task_id, request)
    
    return {
        "task_id": task_id,
        "status": "pending",
        "message": "Análisis de proyecciones futuras iniciado",
        "poll_url": f"/acciones/proyecciones_futuras/status/{task_id}",
        "created_at": task_statuses[task_id]["created_at"]
    }


@app.get("/acciones/proyecciones_futuras/status/{task_id}")
async def proyecciones_futuras_status(task_id: str):
    """
    Obtiene el estado actual de una tarea de proyecciones futuras.
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
        response["message"] = "Proyecciones futuras en proceso. Vuelva a consultar en unos segundos."
    
    return response


async def process_performance_analysis_task(task_id: str, request: PerformanceAnalysisRequest):
    """
    Función auxiliar que procesa el análisis de rendimiento en background.
    Actualiza el estado en task_statuses.
    """
    try:
        # Actualizar estado a "processing"
        task_statuses[task_id]["status"] = "processing"
        task_statuses[task_id]["updated_at"] = datetime.now().isoformat()
        
        # Generar análisis de rendimiento
        result = await chat_service.ejecutar_analisis_rendimiento(request)
        
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


@app.post("/acciones/analisis_rendimiento/start")
async def analisis_rendimiento_start(
    request: PerformanceAnalysisRequest,
    background_tasks: BackgroundTasks,
    authorization: str | None = Header(default=None, alias="Authorization"),
):
    """
    Inicia el análisis asíncrono de rendimiento del portafolio.
    Retorna inmediatamente con un task_id para hacer polling.
    """
    # Extraer token de autorización si está presente
    bearer_token = None
    if authorization and authorization.lower().startswith("bearer "):
        bearer_token = authorization.split(" ", 1)[1]
    elif request.auth_token:
        bearer_token = request.auth_token
    
    # Actualizar el token en el request
    request.auth_token = bearer_token
    
    # Generar task_id único
    task_id = f"perf_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{id(request)}"
    
    # Inicializar estado de la tarea
    task_statuses[task_id] = {
        "task_id": task_id,
        "status": "pending",
        "created_at": datetime.now().isoformat(),
        "updated_at": datetime.now().isoformat(),
    }
    
    # Agregar tarea en background
    background_tasks.add_task(process_performance_analysis_task, task_id, request)
    
    return {
        "task_id": task_id,
        "status": "pending",
        "message": "Análisis de rendimiento iniciado",
        "poll_url": f"/acciones/analisis_rendimiento/status/{task_id}",
        "created_at": task_statuses[task_id]["created_at"]
    }


@app.get("/acciones/analisis_rendimiento/status/{task_id}")
async def analisis_rendimiento_status(task_id: str):
    """
    Obtiene el estado actual de una tarea de análisis de rendimiento.
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
        response["message"] = "Análisis de rendimiento en proceso. Vuelva a consultar en unos segundos."
    
    return response


async def process_daily_weekly_summary_task(task_id: str, request: DailyWeeklySummaryRequest):
    """
    Función auxiliar que procesa el resumen diario/semanal en background.
    Actualiza el estado en task_statuses.
    """
    try:
        # Actualizar estado a "processing"
        task_statuses[task_id]["status"] = "processing"
        task_statuses[task_id]["updated_at"] = datetime.now().isoformat()
        
        # Generar resumen diario/semanal
        result = await chat_service.ejecutar_resumen_diario_semanal(request)
        
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


@app.post("/acciones/resumen_diario_semanal/start")
async def resumen_diario_semanal_start(
    request: DailyWeeklySummaryRequest,
    background_tasks: BackgroundTasks,
    authorization: str | None = Header(default=None, alias="Authorization"),
):
    """
    Inicia el análisis asíncrono de resumen diario/semanal del portafolio.
    Retorna inmediatamente con un task_id para hacer polling.
    """
    # Extraer token de autorización si está presente
    bearer_token = None
    if authorization and authorization.lower().startswith("bearer "):
        bearer_token = authorization.split(" ", 1)[1]
    elif request.auth_token:
        bearer_token = request.auth_token
    
    # Actualizar el token en el request
    request.auth_token = bearer_token
    
    # Generar task_id único
    task_id = f"summ_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{id(request)}"
    
    # Inicializar estado de la tarea
    task_statuses[task_id] = {
        "task_id": task_id,
        "status": "pending",
        "created_at": datetime.now().isoformat(),
        "updated_at": datetime.now().isoformat(),
    }
    
    # Agregar tarea en background
    background_tasks.add_task(process_daily_weekly_summary_task, task_id, request)
    
    return {
        "task_id": task_id,
        "status": "pending",
        "message": "Resumen diario/semanal iniciado",
        "poll_url": f"/acciones/resumen_diario_semanal/status/{task_id}",
        "created_at": task_statuses[task_id]["created_at"]
    }


@app.get("/acciones/resumen_diario_semanal/status/{task_id}")
async def resumen_diario_semanal_status(task_id: str):
    """
    Obtiene el estado actual de una tarea de resumen diario/semanal.
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
        response["message"] = "Resumen diario/semanal en proceso. Vuelva a consultar en unos segundos."
    
    return response


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