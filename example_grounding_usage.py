#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Ejemplos simples de uso de las herramientas de grounding en Horizon Chat Agent

Este script demuestra cómo usar las tres herramientas principales:
1. Google Search Grounding
2. URL Context
3. Function Calling (datetime)
"""

import asyncio
from agent_service import chat_service


async def example_1_datetime():
    """
    Ejemplo 1: Obtener fecha y hora actual
    
    El agente automáticamente llamará a la función get_current_datetime()
    cuando detecte que necesita información temporal.
    """
    print("\n" + "="*60)
    print("EJEMPLO 1: Fecha y Hora Actual")
    print("="*60 + "\n")
    
    result = await chat_service.process_message(
        message="¿Qué día y hora es ahora?",
        user_id="demo_user",
        auth_token=None,
    )
    
    print(f"🤖 Respuesta: {result['response']}\n")
    print(f"🔧 Herramientas usadas: {result['tools_used']}")
    
    if result['metadata'].get('function_calls_made'):
        print(f"\n📞 Función ejecutada:")
        print(f"   {result['metadata']['function_calls_made'][0]['name']}")
        print(f"   Resultado: {result['metadata']['function_calls_made'][0]['result']['datetime']}")


async def example_2_stock_price():
    """
    Ejemplo 2: Precio actual de acciones con Google Search
    
    El agente detectará keywords como "precio actual" y automáticamente
    ejecutará una búsqueda en Google para obtener información actualizada.
    """
    print("\n" + "="*60)
    print("EJEMPLO 2: Precio Actual de Acciones (Google Search)")
    print("="*60 + "\n")
    
    result = await chat_service.process_message(
        message="¿Cuál es el precio actual de las acciones de Microsoft?",
        user_id="demo_user",
        auth_token=None,
    )
    
    print(f"🤖 Respuesta: {result['response']}\n")
    print(f"🔧 Herramientas usadas: {result['tools_used']}")
    
    if result['metadata'].get('grounding_used'):
        print(f"\n🔍 Búsqueda ejecutada: {result['metadata'].get('search_queries')}")
        if result['metadata'].get('sources'):
            print(f"\n📚 Fuentes consultadas:")
            for i, source in enumerate(result['metadata']['sources'][:3], 1):
                print(f"   {i}. {source['title']}")
                print(f"      {source['uri']}")


async def example_3_url_analysis():
    """
    Ejemplo 3: Análisis de contenido de URL
    
    El agente detectará la URL en el mensaje y automáticamente
    recuperará y analizará su contenido.
    """
    print("\n" + "="*60)
    print("EJEMPLO 3: Análisis de URL")
    print("="*60 + "\n")
    
    # URL de ejemplo - Wikipedia sobre Portfolio Management
    url = "https://en.wikipedia.org/wiki/Portfolio_(finance)"
    
    result = await chat_service.process_message(
        message=f"Resume los conceptos clave de este artículo: {url}",
        user_id="demo_user",
        auth_token=None,
    )
    
    print(f"🤖 Respuesta: {result['response']}\n")
    print(f"🔧 Herramientas usadas: {result['tools_used']}")
    
    if result['metadata'].get('url_analyzed'):
        print(f"\n🌐 URL analizada: {result['metadata'].get('detected_urls')}")


async def example_4_temporal_with_search():
    """
    Ejemplo 4: Búsqueda con contexto temporal
    
    Google Search puede inferir "hoy" por contexto sin necesidad
    de usar Function Calling (que no se puede mezclar con grounding).
    """
    print("\n" + "="*60)
    print("EJEMPLO 4: Búsqueda con Contexto Temporal")
    print("="*60 + "\n")
    print("ℹ️  Nota: Google Search infiere 'hoy' automáticamente\n")
    
    result = await chat_service.process_message(
        message="¿Qué noticias financieras importantes han sucedido hoy?",
        user_id="demo_user",
        auth_token=None,
    )
    
    print(f"🤖 Respuesta: {result['response']}\n")
    print(f"🔧 Herramientas usadas: {result['tools_used']}")
    
    print(f"\n📊 Metadata completa:")
    print(f"   - Grounding usado: {result['metadata'].get('grounding_used', False)}")
    print(f"   - Fuentes consultadas: {len(result['metadata'].get('sources', []))}")


async def example_5_financial_context():
    """
    Ejemplo 5: Consulta financiera compleja
    
    Demuestra cómo el agente combina inteligentemente todas las herramientas
    para responder consultas financieras sofisticadas.
    """
    print("\n" + "="*60)
    print("EJEMPLO 5: Consulta Financiera Compleja")
    print("="*60 + "\n")
    
    result = await chat_service.process_message(
        message="¿Cuál es la cotización actual del S&P 500 y qué factores están influyendo en su movimiento hoy?",
        user_id="demo_user",
        auth_token=None,
    )
    
    print(f"🤖 Respuesta: {result['response']}\n")
    print(f"🔧 Herramientas usadas: {result['tools_used']}")
    print(f"📈 Modelo usado: {result['model_used']}")


async def show_capabilities():
    """Muestra las capacidades actuales del servicio"""
    print("\n" + "🌟"*30)
    print("CAPACIDADES DEL SERVICIO HORIZON CHAT AGENT")
    print("🌟"*30 + "\n")
    
    health = chat_service.get_health_status()
    
    print("📋 Herramientas disponibles:")
    for tool in health['tools']:
        status = "✅" if tool['enabled'] else "❌"
        print(f"   {status} {tool['name']}: {tool['description']}")
    
    print("\n🎯 Capacidades:")
    for cap in health['capabilities']:
        print(f"   ✅ {cap}")
    
    print(f"\n🤖 Modelos disponibles:")
    for model in health['models_available']:
        print(f"   • {model}")
    
    print(f"\n💚 Estado: {health['status']}")
    print(f"📊 Sesiones activas: {health['active_sessions']}")


async def main():
    """Ejecutar todos los ejemplos"""
    print("\n" + "🚀"*30)
    print("EJEMPLOS DE USO - HERRAMIENTAS DE GROUNDING")
    print("🚀"*30)
    
    # Mostrar capacidades primero
    await show_capabilities()
    
    # Ejecutar ejemplos
    examples = [
        ("Fecha y Hora", example_1_datetime),
        ("Precio de Acciones", example_2_stock_price),
        ("Análisis de URL", example_3_url_analysis),
        ("Búsqueda Temporal", example_4_temporal_with_search),
        ("Consulta Financiera Compleja", example_5_financial_context),
    ]
    
    for name, func in examples:
        try:
            print(f"\n{'─'*60}")
            await func()
            print(f"{'─'*60}")
            
            # Pequeña pausa entre ejemplos
            await asyncio.sleep(1)
            
        except Exception as e:
            print(f"\n❌ Error en ejemplo '{name}': {e}")
    
    print("\n" + "="*60)
    print("✅ Ejemplos completados")
    print("="*60)
    print("\n💡 TIP: Las herramientas se seleccionan automáticamente")
    print("   según el contenido de tu consulta. ¡Simplemente pregunta!")
    print("\n")


if __name__ == "__main__":
    asyncio.run(main())

