"""
Script para ejecutar REALMENTE el agente y generar un informe de portafolio.

Este script:
1. Se conecta al Supabase real
2. Lee todos los archivos de la carpeta "Graficos" 
3. Ejecuta el agente REAL con llamada a Gemini
4. Captura el JSON del informe generado
5. Lo guarda localmente para inspección

REQUIERE:
- Variables de entorno configuradas en .env
- API key válida de Gemini (GOOGLE_API_KEY)
- Conexión a internet para Gemini API

USO:
python test_03_real_agent_execution.py
"""
import os
import asyncio
import json
from datetime import datetime
from typing import Dict, Any


async def execute_real_portfolio_report():
    """Ejecuta el agente REAL para generar un informe de portafolio"""
    
    print("🚀 INICIANDO EJECUCIÓN REAL DEL AGENTE")
    print("=" * 60)
    
    # Verificar configuración
    print("🔧 Verificando configuración...")
    from config import settings
    
    # Verificar Gemini
    if not settings.get_api_key():
        print("❌ ERROR: No se encontró API key de Gemini")
        print("   Configura GOOGLE_API_KEY o GEMINI_API_KEY en .env")
        return
    
    print(f"✅ API Key de Gemini: {'*' * 20}...{settings.get_api_key()[-4:]}")
    
    # Verificar Supabase
    if not all([settings.supabase_url, settings.supabase_service_role_key]):
        print("❌ ERROR: Configuración de Supabase incompleta")
        return
    
    print(f"✅ Supabase URL: {settings.supabase_url}")
    print(f"✅ Bucket: {settings.supabase_bucket_name}")
    print(f"✅ Prefix: {settings.supabase_base_prefix}")
    
    # Importar el agente
    try:
        from agent_service import chat_service
        print("✅ Agente importado correctamente")
    except Exception as e:
        print(f"❌ ERROR importando agente: {e}")
        return
    
    # Diagnosticar conexión a Supabase
    print(f"\n🔍 DIAGNOSTICANDO CONEXIÓN A SUPABASE...")
    print("-" * 40)
    
    print(f"   Cliente Supabase: {type(chat_service.supabase)}")
    print(f"   URL configurada: {settings.supabase_url}")
    print(f"   Service key configurada: {'Sí' if settings.supabase_service_role_key else 'No'}")
    
    if not chat_service.supabase:
        print("❌ ERROR: El agente no pudo conectar a Supabase")
        print("🔧 Intentando reconectar manualmente...")
        
        try:
            from supabase import create_client
            manual_client = create_client(settings.supabase_url, settings.supabase_service_role_key)
            print("✅ Conexión manual exitosa - reemplazando cliente del agente")
            chat_service.supabase = manual_client
        except Exception as e:
            print(f"❌ ERROR en conexión manual: {e}")
            return
    
    print("✅ Conexión a Supabase establecida")
    
    # Mostrar contexto disponible
    print(f"\n📊 VERIFICANDO CONTEXTO DISPONIBLE...")
    print("-" * 40)
    
    try:
        storage_ctx = chat_service._gather_storage_context()
        if "storage" in storage_ctx:
            storage = storage_ctx["storage"]
            print(f"📄 Archivos JSON: {len(storage.get('json_docs', {}))}")
            print(f"📝 Archivos MD: {len(storage.get('markdown_docs', {}))}")
            print(f"🖼️ Imágenes PNG: {len(storage.get('images', []))}")
            
            # Mostrar archivos disponibles
            json_files = list(storage.get('json_docs', {}).keys())
            md_files = list(storage.get('markdown_docs', {}).keys())
            png_files = [img['path'].split('/')[-1] for img in storage.get('images', [])]
            
            print(f"\n📋 ARCHIVOS DISPONIBLES:")
            print(f"   JSON: {json_files}")
            print(f"   MD: {md_files}")  
            print(f"   PNG: {png_files}")
            
            context_size = len(json.dumps(storage_ctx, ensure_ascii=False))
            print(f"\n📏 Tamaño del contexto: {context_size:,} caracteres")
            
        else:
            print("⚠️ No se encontró contexto de Storage")
            
    except Exception as e:
        print(f"❌ ERROR verificando contexto: {e}")
        return
    
    # Confirmar ejecución
    print(f"\n⚠️ CONFIRMACIÓN REQUERIDA")
    print("-" * 40)
    print("Este script va a:")
    print("1. Hacer una llamada REAL a la API de Gemini")
    print("2. Consumir tokens de tu quota")
    print("3. Generar un informe usando todos los archivos disponibles")
    print(f"4. El contexto tiene {context_size:,} caracteres")
    
    response = input("\n¿Continuar con la ejecución? (s/N): ").strip().lower()
    if response not in ['s', 'si', 'y', 'yes']:
        print("❌ Ejecución cancelada por el usuario")
        return
    
    # Crear request
    print(f"\n🤖 PREPARANDO REQUEST PARA EL AGENTE...")
    print("-" * 40)
    
    from models import PortfolioReportRequest
    
    timestamp = datetime.now().isoformat()
    request = PortfolioReportRequest(
        session_id=None,  # Se creará automáticamente
        model_preference="pro",  # Usar modelo Pro para análisis profundo
        context={
            "execution_type": "real_test",
            "timestamp": timestamp,
            "source": "test_script",
            "note": "Ejecución real del agente para testing"
        }
    )
    
    print(f"✅ Request preparado")
    print(f"   📅 Timestamp: {timestamp}")
    print(f"   🧠 Modelo: {settings.model_pro}")
    print(f"   🎯 Tipo: Ejecución real")
    
    # Ejecutar el agente
    max_retries = 3
    retry_count = 0
    
    while retry_count < max_retries:
        try:
            print(f"\n🚀 EJECUTANDO AGENTE (Intento {retry_count + 1}/{max_retries})...")
            print("-" * 40)
            print("⏳ Enviando request a Gemini... (esto puede tomar varios minutos)")
            
            # EJECUCIÓN REAL DEL AGENTE
            result = await chat_service.ejecutar_generacion_informe_portafolio(request)
            
            print("✅ ¡Agente ejecutado exitosamente!")
            
            # Verificar resultado
            if "error" in result:
                print(f"❌ ERROR en la respuesta del agente:")
                print(f"   {result.get('error', 'Error desconocido')}")
                if "detail" in result:
                    print(f"   Detalle: {result['detail']}")
                
                # Preguntar si reintentar
                if retry_count < max_retries - 1:
                    retry_response = input(f"\n¿Reintentar? (Quedan {max_retries - retry_count - 1} intentos) (s/N): ").strip().lower()
                    if retry_response in ['s', 'si', 'y', 'yes']:
                        retry_count += 1
                        continue
                
                return
            
            # Procesar resultado exitoso
            print(f"\n📊 RESULTADO DEL AGENTE:")
            print("-" * 40)
            print(f"✅ Session ID: {result.get('session_id', 'N/A')}")
            print(f"✅ Modelo usado: {result.get('model_used', 'N/A')}")
            
            if "report" in result:
                report = result["report"]
                print(f"✅ Informe generado correctamente")
                print(f"   📄 Tipo: {type(report)}")
                
                if isinstance(report, dict):
                    print(f"   🔑 Claves principales: {list(report.keys())[:10]}")
                elif hasattr(report, 'model_dump'):
                    report_dict = report.model_dump()
                    print(f"   🔑 Claves principales: {list(report_dict.keys())[:10]}")
                    report = report_dict
                
                # Guardar el informe
                await save_report_locally(report, result, timestamp)
                
            else:
                print("⚠️ No se encontró 'report' en el resultado")
                print(f"   Claves disponibles: {list(result.keys())}")
            
            break  # Salir del loop si fue exitoso
            
        except Exception as e:
            error_message = str(e)
            print(f"❌ ERROR durante la ejecución:")
            print(f"   {error_message}")
            
            # Analizar tipo de error
            if "API key" in error_message or "INVALID_ARGUMENT" in error_message:
                print("   🔑 Error relacionado con API key")
            elif "quota" in error_message.lower() or "limit" in error_message.lower():
                print("   💰 Error relacionado con cuota/límites")
            elif "timeout" in error_message.lower():
                print("   ⏰ Error de timeout")
            else:
                print("   🔧 Error técnico general")
            
            retry_count += 1
            
            if retry_count < max_retries:
                print(f"\n⚠️ INTENTO {retry_count}/{max_retries} FALLÓ")
                retry_response = input(f"¿Reintentar? (Quedan {max_retries - retry_count} intentos) (s/N): ").strip().lower()
                if retry_response not in ['s', 'si', 'y', 'yes']:
                    print("❌ Ejecución cancelada por el usuario")
                    return
                    
                print("⏳ Esperando 5 segundos antes del reintento...")
                await asyncio.sleep(5)
            else:
                print(f"❌ Se agotaron todos los intentos ({max_retries})")
                return


async def save_report_locally(report: Dict[str, Any], full_result: Dict[str, Any], timestamp: str):
    """Guarda el informe y resultado completo localmente"""
    
    print(f"\n💾 GUARDANDO RESULTADO LOCALMENTE...")
    print("-" * 40)
    
    try:
        # Crear directorio si no existe
        output_dir = "output_reports"
        os.makedirs(output_dir, exist_ok=True)
        
        # Nombres de archivos con timestamp
        clean_timestamp = timestamp.replace(":", "-").replace(".", "-")
        report_file = f"{output_dir}/portfolio_report_{clean_timestamp}.json"
        full_result_file = f"{output_dir}/full_result_{clean_timestamp}.json"
        summary_file = f"{output_dir}/execution_summary_{clean_timestamp}.txt"
        
        # Guardar solo el informe
        with open(report_file, 'w', encoding='utf-8') as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        
        print(f"✅ Informe guardado: {report_file}")
        
        # Guardar resultado completo
        with open(full_result_file, 'w', encoding='utf-8') as f:
            json.dump(full_result, f, ensure_ascii=False, indent=2)
        
        print(f"✅ Resultado completo guardado: {full_result_file}")
        
        # Crear resumen de ejecución
        summary = f"""RESUMEN DE EJECUCIÓN DEL AGENTE
{'='*50}

Timestamp: {timestamp}
Session ID: {full_result.get('session_id', 'N/A')}
Modelo usado: {full_result.get('model_used', 'N/A')}

ARCHIVOS GENERADOS:
- Informe JSON: {report_file}
- Resultado completo: {full_result_file}
- Este resumen: {summary_file}

ESTADÍSTICAS:
- Tamaño del informe: {len(json.dumps(report, ensure_ascii=False)):,} caracteres
- Tamaño del resultado completo: {len(json.dumps(full_result, ensure_ascii=False)):,} caracteres

ESTRUCTURA DEL INFORME:
"""
        
        if isinstance(report, dict):
            for key in report.keys():
                summary += f"- {key}\n"
        
        summary += f"\nEJECUCIÓN COMPLETADA EXITOSAMENTE ✅"
        
        with open(summary_file, 'w', encoding='utf-8') as f:
            f.write(summary)
        
        print(f"✅ Resumen guardado: {summary_file}")
        
        # Mostrar estadísticas finales
        report_size = len(json.dumps(report, ensure_ascii=False))
        print(f"\n📊 ESTADÍSTICAS FINALES:")
        print(f"   📄 Tamaño del informe: {report_size:,} caracteres")
        print(f"   📁 Archivos creados: 3")
        print(f"   📂 Directorio: {output_dir}/")
        
        if isinstance(report, dict):
            print(f"   🔑 Secciones del informe: {len(report)}")
        
    except Exception as e:
        print(f"❌ ERROR guardando archivos: {e}")


async def main():
    """Función principal"""
    try:
        await execute_real_portfolio_report()
    except KeyboardInterrupt:
        print(f"\n❌ Ejecución interrumpida por el usuario")
    except Exception as e:
        print(f"❌ ERROR inesperado: {e}")
        import traceback
        traceback.print_exc()
    
    print(f"\n🏁 SCRIPT FINALIZADO")


if __name__ == "__main__":
    asyncio.run(main())