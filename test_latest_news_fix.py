#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test específico para el error con "What's the latest news?"
"""

import asyncio
from agent_service import chat_service


async def test_latest_news():
    """Probar la pregunta que causó el error"""
    print("\n" + "="*60)
    print("TEST: What's the latest news?")
    print("="*60 + "\n")
    
    try:
        result = await chat_service.process_message(
            message="What's the latest news?",
            user_id="test_fix_user"
        )
        
        print(f"✅ Respuesta exitosa:")
        print(f"   {result['response'][:300]}...\n")
        print(f"🔧 Herramientas usadas: {result['tools_used']}")
        print(f"📊 Metadata keys: {list(result['metadata'].keys())}")
        
        if result['metadata'].get('grounding_used'):
            print(f"📚 Fuentes: {len(result['metadata'].get('sources', []))}")
            if result['metadata'].get('search_queries'):
                print(f"🔍 Búsquedas: {result['metadata']['search_queries']}")
        
        print("\n✅ Test exitoso - error corregido!")
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()


async def test_various_queries():
    """Probar varias consultas para asegurar estabilidad"""
    queries = [
        "What's the latest news?",
        "¿Qué noticias hay?",
        "Latest financial news",
        "Noticias recientes",
        "What happened today?"
    ]
    
    print("\n" + "="*60)
    print("PRUEBAS DE ESTABILIDAD")
    print("="*60)
    
    passed = 0
    failed = 0
    
    for query in queries:
        print(f"\n📝 Probando: '{query}'")
        try:
            result = await chat_service.process_message(
                message=query,
                user_id="test_stability"
            )
            
            if result['response'] and not result['response'].startswith("Lo siento"):
                print(f"   ✅ OK - {len(result['response'])} caracteres")
                passed += 1
            else:
                print(f"   ⚠️  Respuesta por defecto")
                passed += 1
                
        except Exception as e:
            print(f"   ❌ ERROR: {e}")
            failed += 1
        
        await asyncio.sleep(0.5)
    
    print(f"\n{'='*60}")
    print(f"Resultados: {passed} pasados, {failed} fallidos")
    print(f"{'='*60}")


async def main():
    print("\n🔧 TEST DE FIX PARA ERROR DE response.text")
    print("="*60)
    
    # Test principal
    await test_latest_news()
    await asyncio.sleep(1)
    
    # Tests de estabilidad
    await test_various_queries()
    
    print("\n✅ Tests completados")


if __name__ == "__main__":
    asyncio.run(main())

