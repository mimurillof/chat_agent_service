#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Prueba rápida para verificar que el fix de herramientas funciona
"""

import asyncio
from agent_service import chat_service


async def test_google_search():
    """Probar Google Search sin function calling"""
    print("\n🧪 Test 1: Google Search (sin function calling)")
    print("-" * 50)
    
    result = await chat_service.process_message(
        message="¿Cuál es el precio actual de Bitcoin?",
        user_id="test_quick"
    )
    
    print(f"✅ Respuesta: {result['response'][:200]}...")
    print(f"🔧 Herramientas: {result['tools_used']}")
    print(f"📊 Metadata keys: {list(result['metadata'].keys())}")
    
    if 'google_search' in result['tools_used']:
        print("✅ Google Search funcionando correctamente")
    else:
        print("⚠️ Google Search no se usó")


async def test_url_context():
    """Probar URL Context sin function calling"""
    print("\n🧪 Test 2: URL Context (sin function calling)")
    print("-" * 50)
    
    result = await chat_service.process_message(
        message="Resume https://en.wikipedia.org/wiki/Finance",
        user_id="test_quick"
    )
    
    print(f"✅ Respuesta: {result['response'][:200]}...")
    print(f"🔧 Herramientas: {result['tools_used']}")
    print(f"📊 URLs detectadas: {result['metadata'].get('detected_urls')}")
    
    if 'url_context' in result['tools_used']:
        print("✅ URL Context funcionando correctamente")
    else:
        print("⚠️ URL Context no se usó")


async def test_datetime():
    """Probar Function Calling solo"""
    print("\n🧪 Test 3: Function Calling (sin grounding)")
    print("-" * 50)
    
    result = await chat_service.process_message(
        message="¿Qué día de la semana es?",
        user_id="test_quick"
    )
    
    print(f"✅ Respuesta: {result['response']}")
    print(f"🔧 Herramientas: {result['tools_used']}")
    
    if result['metadata'].get('function_calls_made'):
        print(f"📅 Función ejecutada: {result['metadata']['function_calls_made'][0]['name']}")
        print("✅ Function Calling funcionando correctamente")
    else:
        print("ℹ️ El modelo respondió sin usar la función")


async def main():
    print("\n" + "="*60)
    print("PRUEBA RÁPIDA - FIX DE HERRAMIENTAS")
    print("="*60)
    print("\nVerificando que no se mezclan Function Calling con Grounding...")
    
    try:
        await test_google_search()
        await asyncio.sleep(1)
        
        await test_url_context()
        await asyncio.sleep(1)
        
        await test_datetime()
        
        print("\n" + "="*60)
        print("✅ PRUEBA RÁPIDA COMPLETADA")
        print("="*60)
        print("\n💡 Si no hubo errores 400, el fix está funcionando!")
        
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())

