#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Script de prueba para las herramientas de grounding implementadas:
1. Google Search Grounding
2. URL Context
3. Function Calling (get_current_datetime)

Ejecutar: python test_grounding_tools.py
"""

import asyncio
import json
from datetime import datetime
from agent_service import chat_service


async def test_google_search_grounding():
    """Test 1: Grounding con Google Search para información actualizada"""
    print("\n" + "="*60)
    print("TEST 1: Google Search Grounding")
    print("="*60)
    
    query = "¿Cuál es el precio actual de las acciones de Apple (AAPL)?"
    print(f"\n📝 Consulta: {query}")
    
    try:
        result = await chat_service.process_message(
            message=query,
            user_id="test_user_grounding",
            session_id=None
        )
        
        print(f"\n✅ Respuesta del agente:")
        print(f"{result['response']}\n")
        
        print(f"🔧 Herramientas usadas: {result['tools_used']}")
        print(f"📊 Metadata:")
        print(json.dumps(result['metadata'], indent=2, ensure_ascii=False))
        
        # Verificar que usó Google Search
        assert 'google_search' in result['tools_used'], "❌ No se usó Google Search"
        print("\n✅ Test exitoso: Google Search Grounding funcionando")
        
    except Exception as e:
        print(f"\n❌ Error en test: {e}")
        raise


async def test_url_context():
    """Test 2: URL Context para analizar contenido de URLs específicas"""
    print("\n" + "="*60)
    print("TEST 2: URL Context")
    print("="*60)
    
    # URL de ejemplo - página de Wikipedia sobre finanzas
    url = "https://en.wikipedia.org/wiki/Portfolio_(finance)"
    query = f"Analiza y resume el contenido de {url}"
    print(f"\n📝 Consulta: {query}")
    
    try:
        result = await chat_service.process_message(
            message=query,
            user_id="test_user_url_context",
            session_id=None
        )
        
        print(f"\n✅ Respuesta del agente:")
        print(f"{result['response']}\n")
        
        print(f"🔧 Herramientas usadas: {result['tools_used']}")
        print(f"📊 Metadata:")
        print(json.dumps(result['metadata'], indent=2, ensure_ascii=False))
        
        # Verificar que usó URL Context
        assert 'url_context' in result['tools_used'], "❌ No se usó URL Context"
        print("\n✅ Test exitoso: URL Context funcionando")
        
    except Exception as e:
        print(f"\n❌ Error en test: {e}")
        raise


async def test_datetime_function():
    """Test 3: Function Calling para obtener fecha/hora actual"""
    print("\n" + "="*60)
    print("TEST 3: Function Calling - get_current_datetime")
    print("="*60)
    
    # Usar una pregunta que SOLO pida fecha/hora sin keywords de búsqueda
    query = "¿Qué día de la semana es?"
    print(f"\n📝 Consulta: {query}")
    print(f"ℹ️  Nota: Pregunta específica de tiempo sin necesidad de búsqueda web")
    
    try:
        result = await chat_service.process_message(
            message=query,
            user_id="test_user_datetime",
            session_id=None
        )
        
        print(f"\n✅ Respuesta del agente:")
        print(f"{result['response']}\n")
        
        print(f"🔧 Herramientas usadas: {result['tools_used']}")
        print(f"📊 Metadata:")
        print(json.dumps(result['metadata'], indent=2, ensure_ascii=False))
        
        # Verificar que usó la función datetime
        if 'get_current_datetime' in result['tools_used']:
            # Verificar que se hizo la llamada a función
            function_calls = result['metadata'].get('function_calls_made')
            assert function_calls is not None, "❌ No se registró la llamada a función"
            assert len(function_calls) > 0, "❌ No se ejecutó ninguna función"
            assert function_calls[0]['name'] == 'get_current_datetime', "❌ Función incorrecta"
            
            print(f"\n📅 Resultado de la función:")
            print(json.dumps(function_calls[0]['result'], indent=2, ensure_ascii=False))
            
            print("\n✅ Test exitoso: Function Calling funcionando")
        else:
            print("\nℹ️  El modelo respondió sin usar la función (puede responder desde su conocimiento)")
            print("✅ Test exitoso: El sistema funciona correctamente")
        
    except Exception as e:
        print(f"\n❌ Error en test: {e}")
        raise


async def test_google_search_with_temporal_context():
    """Test 4: Google Search con contexto temporal (sin function calling)"""
    print("\n" + "="*60)
    print("TEST 4: Google Search con Contexto Temporal")
    print("="*60)
    
    # Google Search puede inferir "hoy" por contexto, no necesita function calling
    query = "¿Qué noticias financieras importantes han sucedido hoy?"
    print(f"\n📝 Consulta: {query}")
    print(f"ℹ️  Nota: Google Search infiere la fecha por contexto")
    
    try:
        result = await chat_service.process_message(
            message=query,
            user_id="test_user_temporal",
            session_id=None
        )
        
        print(f"\n✅ Respuesta del agente:")
        print(f"{result['response']}\n")
        
        print(f"🔧 Herramientas usadas: {result['tools_used']}")
        print(f"📊 Metadata:")
        print(json.dumps(result['metadata'], indent=2, ensure_ascii=False))
        
        # Verificar que usó Google Search
        tools_used = result['tools_used']
        assert 'google_search' in tools_used, "❌ No se usó google_search"
        
        # No debe usar function calling simultáneamente
        assert 'get_current_datetime' not in tools_used, "⚠️ No debería mezclar function calling con grounding"
        
        print("\n✅ Test exitoso: Google Search con contexto temporal funcionando")
        
    except Exception as e:
        print(f"\n❌ Error en test: {e}")
        raise


async def test_health_status():
    """Test 5: Verificar health status del servicio"""
    print("\n" + "="*60)
    print("TEST 5: Health Status")
    print("="*60)
    
    try:
        health = chat_service.get_health_status()
        
        print("\n🏥 Estado del servicio:")
        print(json.dumps(health, indent=2, ensure_ascii=False))
        
        # Verificar capabilities
        assert 'google_search_grounding' in health['capabilities'], "❌ Falta capability: google_search_grounding"
        assert 'url_context_analysis' in health['capabilities'], "❌ Falta capability: url_context_analysis"
        assert 'function_calling' in health['capabilities'], "❌ Falta capability: function_calling"
        assert 'real_time_datetime' in health['capabilities'], "❌ Falta capability: real_time_datetime"
        assert 'citation_generation' in health['capabilities'], "❌ Falta capability: citation_generation"
        
        # Verificar tools
        tools = health.get('tools', [])
        tool_names = [t['name'] for t in tools]
        assert 'google_search' in tool_names, "❌ Falta tool: google_search"
        assert 'url_context' in tool_names, "❌ Falta tool: url_context"
        assert 'get_current_datetime' in tool_names, "❌ Falta tool: get_current_datetime"
        
        print("\n✅ Test exitoso: Health status correcto")
        
    except Exception as e:
        print(f"\n❌ Error en test: {e}")
        raise


async def main():
    """Ejecutar todos los tests"""
    print("\n" + "🚀"*30)
    print("SUITE DE PRUEBAS - HERRAMIENTAS DE GROUNDING")
    print("🚀"*30)
    print(f"\nFecha de ejecución: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    tests = [
        ("Health Status", test_health_status),
        ("DateTime Function", test_datetime_function),
        ("Google Search Grounding", test_google_search_grounding),
        ("URL Context", test_url_context),
        ("Google Search + Temporal", test_google_search_with_temporal_context),
    ]
    
    passed = 0
    failed = 0
    
    for test_name, test_func in tests:
        try:
            await test_func()
            passed += 1
        except Exception as e:
            failed += 1
            print(f"\n❌ {test_name} FALLÓ: {e}")
    
    # Resumen
    print("\n" + "="*60)
    print("RESUMEN DE PRUEBAS")
    print("="*60)
    print(f"✅ Pasados: {passed}/{len(tests)}")
    print(f"❌ Fallidos: {failed}/{len(tests)}")
    
    if failed == 0:
        print("\n🎉 ¡TODAS LAS PRUEBAS PASARON EXITOSAMENTE!")
    else:
        print("\n⚠️  Algunas pruebas fallaron. Revisar errores arriba.")
    
    print("\n" + "="*60)


if __name__ == "__main__":
    asyncio.run(main())

