"""
Script de prueba para verificar la salida estructurada de Gemini
siguiendo exactamente el tutorial oficial.

Este script prueba la configuración JSON estructurada paso a paso:
1. Configuración básica del cliente
2. Definición del esquema con Pydantic BaseModel
3. Configuración correcta del response_schema
4. Manejo apropiado de la respuesta .parsed

REQUIERE:
- Variables de entorno configuradas en .env
- API key válida de Gemini (GOOGLE_API_KEY)
"""
import os
import json
from datetime import datetime
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any


# Esquema simplificado para testing siguiendo el tutorial
class AnalysisSection(BaseModel):
    title: str = Field(description="Título de la sección")
    content: str = Field(description="Contenido de la sección")
    key_points: List[str] = Field(description="Puntos clave de la sección")


class SimplePortfolioReport(BaseModel):
    report_title: str = Field(description="Título del informe")
    timestamp: str = Field(description="Timestamp de generación")
    summary: str = Field(description="Resumen ejecutivo")
    sections: List[AnalysisSection] = Field(description="Secciones del análisis")
    recommendations: List[str] = Field(description="Recomendaciones principales")
    risk_assessment: str = Field(description="Evaluación de riesgos")


async def test_structured_output():
    """Test de salida estructurada siguiendo el tutorial oficial"""
    
    print("🧪 TESTING SALIDA ESTRUCTURADA DE GEMINI")
    print("=" * 50)
    
    # 1. Verificar configuración
    print("🔧 Verificando configuración...")
    from config import settings
    
    if not settings.get_api_key():
        print("❌ ERROR: No se encontró API key de Gemini")
        return False
    
    print(f"✅ API Key configurada: {'*' * 20}...{settings.get_api_key()[-4:]}")
    
    # 2. Configurar cliente Gemini según tutorial
    print("🔌 Configurando cliente Gemini...")
    try:
        from google import genai
        from google.genai import types
        
        # Configurar cliente como en el tutorial - con API key explícita
        client = genai.Client(api_key=settings.get_api_key())
        print("✅ Cliente Gemini configurado")
        
    except Exception as e:
        print(f"❌ ERROR configurando cliente: {e}")
        return False
    
    # 3. Test básico de salida estructurada
    print("\\n📊 EJECUTANDO TEST BÁSICO...")
    print("-" * 40)
    
    try:
        # Prompt simple para testing
        prompt = """
        Genera un informe de portafolio de inversiones con las siguientes características:
        - Título: "Análisis de Portafolio de Prueba"
        - Resumen de 2-3 líneas sobre diversificación
        - 2 secciones: "Análisis de Riesgo" y "Rendimiento"
        - 3 recomendaciones concretas
        - Evaluación de riesgo general
        """
        
        # Configuración según tutorial - EXACTA
        config = types.GenerateContentConfig(
            temperature=0.1,  # Temperatura baja para determinismo
            response_mime_type="application/json",
            response_schema=SimplePortfolioReport,  # Esquema Pydantic
        )
        
        print("⏳ Enviando request a Gemini...")
        
        # Intentar con diferentes modelos si hay sobrecarga
        models_to_try = ["gemini-2.5-flash", "gemini-1.5-flash", "gemini-1.5-pro"]
        
        for model_name in models_to_try:
            try:
                print(f"   Probando modelo: {model_name}")
                
                # Generar contenido según tutorial
                response = client.models.generate_content(
                    model=model_name,
                    contents=prompt,
                    config=config,
                )
                
                print(f"✅ Respuesta recibida de Gemini usando {model_name}")
                break
                
            except Exception as model_error:
                print(f"   ❌ Error con {model_name}: {str(model_error)[:100]}...")
                if "overloaded" in str(model_error) or "503" in str(model_error):
                    print(f"   ⏳ Modelo {model_name} sobrecargado, probando siguiente...")
                    continue
                else:
                    # Error no relacionado con sobrecarga, propagar
                    raise model_error
        else:
            # Si llegamos aquí, todos los modelos fallaron
            print("❌ Todos los modelos están sobrecargados, reintentar más tarde")
            return False
        
        # 4. Procesar respuesta según tutorial
        print("\\n🔍 PROCESANDO RESPUESTA...")
        print("-" * 40)
        
        # Verificar atributo .parsed según tutorial
        if hasattr(response, 'parsed') and response.parsed:
            print("✅ response.parsed disponible")
            parsed_report = response.parsed
            print(f"✅ Tipo de .parsed: {type(parsed_report)}")
            
            # Verificar que es instancia de nuestro modelo
            if isinstance(parsed_report, SimplePortfolioReport):
                print("✅ .parsed es instancia de SimplePortfolioReport")
                
                # Mostrar estructura
                print(f"\\n📋 ESTRUCTURA DEL INFORME:")
                print(f"   Título: {parsed_report.report_title}")
                print(f"   Timestamp: {parsed_report.timestamp}")
                print(f"   Secciones: {len(parsed_report.sections)}")
                print(f"   Recomendaciones: {len(parsed_report.recommendations)}")
                
                # Guardar para inspección
                output_file = f"test_structured_output_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
                
                with open(output_file, 'w', encoding='utf-8') as f:
                    json.dump(parsed_report.model_dump(), f, ensure_ascii=False, indent=2)
                
                print(f"✅ Informe guardado: {output_file}")
                
                return True
                
            else:
                print(f"❌ .parsed no es instancia correcta: {type(parsed_report)}")
                
        else:
            print("❌ response.parsed no disponible o vacío")
            
            # Fallback: intentar parsear .text según tutorial
            if hasattr(response, 'text') and response.text:
                print("🔄 Intentando fallback con .text...")
                try:
                    json_data = json.loads(response.text)
                    manual_parsed = SimplePortfolioReport.model_validate(json_data)
                    print("✅ Parsing manual exitoso")
                    
                    output_file = f"test_structured_output_manual_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
                    with open(output_file, 'w', encoding='utf-8') as f:
                        json.dump(manual_parsed.model_dump(), f, ensure_ascii=False, indent=2)
                    
                    print(f"✅ Informe manual guardado: {output_file}")
                    return True
                    
                except Exception as e:
                    print(f"❌ Error en parsing manual: {e}")
                    print(f"Raw text: {response.text[:500]}...")
            else:
                print("❌ response.text tampoco disponible")
        
        return False
        
    except Exception as e:
        print(f"❌ ERROR durante el test: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_with_real_context():
    """Test con contexto real de Supabase"""
    
    print("\\n🌐 TESTING CON CONTEXTO REAL DE SUPABASE...")
    print("=" * 50)
    
    try:
        # Importar agente para obtener contexto
        from agent_service import chat_service
        
        # Obtener contexto real
        storage_ctx = chat_service._gather_storage_context()
        
        if "storage" not in storage_ctx:
            print("❌ No hay contexto de Storage disponible")
            return False
        
        storage = storage_ctx["storage"]
        print(f"✅ Contexto obtenido:")
        print(f"   JSON docs: {len(storage.get('json_docs', {}))}")
        print(f"   MD docs: {len(storage.get('markdown_docs', {}))}")
        print(f"   Imágenes: {len(storage.get('images', []))}")
        
        # Preparar prompt con contexto real
        context_summary = {
            "json_files": list(storage.get('json_docs', {}).keys()),
            "md_files": list(storage.get('markdown_docs', {}).keys()),
            "png_files": [img['path'].split('/')[-1] for img in storage.get('images', [])],
            "total_files": len(storage.get('json_docs', {})) + len(storage.get('markdown_docs', {})) + len(storage.get('images', []))
        }
        
        prompt = f"""
        Analiza el siguiente contexto de portafolio y genera un informe estructurado:
        
        CONTEXTO DISPONIBLE:
        {json.dumps(context_summary, ensure_ascii=False, indent=2)}
        
        Genera un informe que incluya:
        - Título descriptivo
        - Resumen de los datos disponibles
        - Análisis de las secciones principales
        - Recomendaciones basadas en los archivos disponibles
        - Evaluación de riesgo preliminar
        """
        
        # Configurar cliente
        from google import genai
        from google.genai import types
        from config import settings
        
        client = genai.Client(api_key=settings.get_api_key())
        
        config = types.GenerateContentConfig(
            temperature=0.2,
            response_mime_type="application/json",
            response_schema=SimplePortfolioReport,
        )
        
        print("⏳ Generando informe con contexto real...")
        
        response = client.models.generate_content(
            model="gemini-2.5-pro",  # Usar Pro para análisis más profundo
            contents=prompt,
            config=config,
        )
        
        # Procesar respuesta
        if hasattr(response, 'parsed') and response.parsed:
            parsed_report = response.parsed
            
            output_file = f"test_real_context_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(parsed_report.model_dump(), f, ensure_ascii=False, indent=2)
            
            print(f"✅ Informe con contexto real guardado: {output_file}")
            
            # Mostrar resumen
            print(f"\\n📊 RESUMEN DEL INFORME:")
            print(f"   Título: {parsed_report.report_title}")
            print(f"   Secciones: {len(parsed_report.sections)}")
            for i, section in enumerate(parsed_report.sections):
                print(f"   {i+1}. {section.title}")
            
            return True
        
        else:
            print("❌ No se pudo parsear la respuesta con contexto real")
            return False
        
    except Exception as e:
        print(f"❌ ERROR en test con contexto real: {e}")
        import traceback
        traceback.print_exc()
        return False


async def main():
    """Función principal de testing"""
    
    print("🧪 INICIANDO TESTS DE SALIDA ESTRUCTURADA")
    print("=" * 60)
    
    try:
        # Test 1: Básico
        print("\\n[ TEST 1: BÁSICO ]")
        test1_success = await test_structured_output()
        
        if test1_success:
            print("\\n✅ TEST 1 EXITOSO - Procediendo con test avanzado...")
            
            # Test 2: Con contexto real
            print("\\n[ TEST 2: CON CONTEXTO REAL ]")
            test2_success = await test_with_real_context()
            
            if test2_success:
                print("\\n🎉 TODOS LOS TESTS EXITOSOS")
                print("✅ La salida estructurada funciona correctamente")
                print("✅ Se puede proceder con el agente real")
                return True
            else:
                print("\\n⚠️ TEST 2 FALLÓ - revisar configuración con contexto")
                return False
        else:
            print("\\n❌ TEST 1 FALLÓ - problema fundamental con salida estructurada")
            return False
            
    except Exception as e:
        print(f"❌ ERROR inesperado: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    finally:
        print("\\n🏁 TESTS FINALIZADOS")


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())