# -*- coding: utf-8 -*-
"""
Servicio independiente del agente de chat Horizon
Adaptado para funcionar como microservicio separado
"""
import os
import re
import uuid
import traceback
from datetime import datetime
from typing import Optional, Dict, Any, List
import json
from json import JSONDecodeError

from pydantic import ValidationError
from config import settings
from models import ChatMessage, MessageRole, PortfolioReportRequest, PortfolioReportResponse, Report

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
    from supabase import create_client
    _has_supabase = True
except Exception:
    _has_supabase = False

try:
    from json_repair import repair_json
    _has_json_repair = True
except Exception:
    _has_json_repair = False

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
        self.supabase = None
        
        if not self.client:
            raise Exception("Cliente Gemini no disponible")
        
        # Inicializar Supabase si hay credenciales
        if _has_supabase and settings.supabase_url and settings.supabase_service_role_key:
            try:
                self.supabase = create_client(settings.supabase_url, settings.supabase_service_role_key)
            except Exception as e:
                print(f"⚠️ No se pudo inicializar Supabase: {e}")
        
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
    
    # =====================
    # Informe de análisis de portafolio
    # =====================
    def _list_supabase_files(self, user_id: str) -> List[Dict[str, Any]]:
        """Lista archivos en el bucket del usuario. Filtra por extensiones permitidas."""
        if not self.supabase:
            return []
        allowed = {".json", ".md", ".png"}
        files: List[Dict[str, Any]] = []
        
        # Listar archivos en la carpeta del usuario: {user_id}/
        try:
            items = self.supabase.storage.from_(self.supabase_bucket).list(user_id or "")
        except Exception as e:
            print(f"⚠️ Error listando Storage para user_id '{user_id}': {e}")
            return []

        for it in (items or []):
            name = str(it.get("name") or "")
            lower = name.lower()
            if not any(lower.endswith(ext) for ext in allowed):
                continue
            full_path = f"{user_id}/{name}"
            files.append({
                "name": name,
                "path": full_path,
                "user_id": user_id,
                "ext": lower[lower.rfind("."):],
            })
        return files

    def _read_supabase_text_files(self, files: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Descarga y devuelve contenidos de .json y .md en dicts separados."""
        if not self.supabase:
            return {"json_docs": {}, "markdown_docs": {}}
        json_docs: Dict[str, Any] = {}
        markdown_docs: Dict[str, str] = {}
        for f in files:
            ext = f.get("ext")
            path = f.get("path")
            name = f.get("name")
            if ext not in (".json", ".md"):
                continue
            try:
                data = self.supabase.storage.from_(self.supabase_bucket).download(path)
                text = data.decode("utf-8", errors="replace") if isinstance(data, (bytes, bytearray)) else str(data)
                if ext == ".json":
                    try:
                        json_docs[name] = json.loads(text)
                    except Exception:
                        json_docs[name] = {"_raw": text}
                else:
                    markdown_docs[name] = text
            except Exception as e:
                print(f"⚠️ No se pudo descargar {path}: {e}")
        return {"json_docs": json_docs, "markdown_docs": markdown_docs}

    def _gather_storage_context(self, user_id: str) -> Dict[str, Any]:
        """Compila contexto desde Storage: JSON/MD contenidos y lista de imágenes PNG del usuario específico."""
        if not self.supabase:
            return {}
        files = self._list_supabase_files(user_id)
        text_ctx = self._read_supabase_text_files(files)
        images = [
            {"bucket": self.supabase_bucket, "path": f["path"]}
            for f in files if f.get("ext") == ".png"
        ]
        return {
            "storage": {
                "bucket": self.supabase_bucket,
                "user_id": user_id,
                "images": images,
                **text_ctx,
            }
        }

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
        storage_ctx = self._gather_storage_context(user_id)
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

    async def process_message(
        self, 
        message: str,
        user_id: str,  # ✅ NUEVO: Requerido para multiusuario
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