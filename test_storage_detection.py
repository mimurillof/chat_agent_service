#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test para verificar la detección de consultas sobre archivos del usuario.
Este script prueba el método _is_user_storage_query sin necesitar API keys.
"""
import sys
import os
import re

# No importamos el servicio directamente para evitar la inicialización

def _is_user_storage_query(query: str) -> bool:
    """
    Detecta si el usuario está preguntando sobre SUS archivos en Supabase Storage.
    Reconoce patrones posesivos y referencias a archivos del usuario.
    
    Ejemplos que debería detectar:
    - "¿Qué significa mi gráfico de Monte Carlo?"
    - "Analiza mis gráficos"
    - "Explícame mi reporte"
    - "¿Cómo interpreto mi análisis de riesgo?"
    - "Dame un resumen de mi portafolio basado en mis archivos"
    - "¿Qué dicen mis datos?"
    - "Muéstrame mi historial de inversiones"
    """
    query_lower = query.lower()
    
    # Patrones posesivos en español
    possessive_patterns = [
        "mi ", "mis ", "mío", "mía", "míos", "mías",
        "el mio", "la mia", "los mios", "las mias",
        "mi archivo", "mis archivos", "mi documento", "mis documentos",
        "mi gráfico", "mis gráficos", "mi grafico", "mis graficos",
        "mi imagen", "mis imágenes", "mi imagen", "mis imagenes",
        "mi reporte", "mis reportes", "mi informe", "mis informes",
        "mi análisis", "mis análisis", "mi analisis", "mis analisis",
        "mi portafolio", "mi portfolio", "mi cartera",
        "mi json", "mis json", "mi pdf", "mis pdf",
        "mi chart", "mis charts", "mi data", "mis datos",
    ]
    
    # Palabras clave de tipos de archivos/visualizaciones
    file_type_keywords = [
        # Gráficos y visualizaciones
        "gráfico", "grafico", "gráficos", "graficos",
        "chart", "charts", "plot", "plots",
        "visualización", "visualizacion", "visualizaciones",
        "diagrama", "diagramas",
        
        # Tipos de análisis comunes en finanzas
        "monte carlo", "montecarlo", "simulación", "simulacion",
        "correlación", "correlacion", "heatmap",
        "drawdown", "volatilidad", "riesgo",
        "pie chart", "bar chart", "line chart",
        "candlestick", "velas",
        "scatter", "distribución", "distribucion",
        "histograma", "histogram",
        
        # Tipos de archivos
        "json", "pdf", "imagen", "imágenes", "imagenes",
        "png", "jpg", "jpeg",
        
        # Documentos de análisis
        "reporte", "informe", "análisis", "analisis",
        "resumen", "summary", "documento",
    ]
    
    # Verbos de acción sobre archivos personales
    action_verbs = [
        "analiza", "analizar", "analízame", "analizame",
        "explica", "explicar", "explícame", "explicame",
        "interpreta", "interpretar", "interprétame", "interpretame",
        "muestra", "mostrar", "muéstrame", "muestrame",
        "describe", "describir", "descríbeme", "describeme",
        "resume", "resumir", "resúmeme", "resumeme",
        "lee", "leer", "léeme", "leeme",
        "revisa", "revisar", "revísame", "revisame",
        "extrae", "extraer", "extráeme", "extraeme",
        "qué significa", "que significa",
        "qué dice", "que dice",
        "qué muestra", "que muestra",
        "cómo interpreto", "como interpreto",
        "cómo leo", "como leo",
    ]
    
    # Detectar patrón posesivo + tipo de archivo
    has_possessive = any(pattern in query_lower for pattern in possessive_patterns)
    has_file_type = any(keyword in query_lower for keyword in file_type_keywords)
    has_action = any(verb in query_lower for verb in action_verbs)
    
    # Si tiene posesivo y tipo de archivo → es consulta de storage
    if has_possessive and has_file_type:
        return True
    
    # Si tiene posesivo y verbo de acción → probable consulta de storage
    if has_possessive and has_action:
        return True
    
    # Patrones específicos adicionales
    specific_patterns = [
        "basado en mis",
        "según mis",
        "con base en mis",
        "de acuerdo a mis",
        "usando mis",
        "a partir de mis",
        "desde mis archivos",
        "en mi storage",
        "en mi bucket",
        "de mi carpeta",
        "mi último", "mi ultima",
        "mi reciente", "mi más reciente",
        "que tengo guardado", "que tengo almacenado",
        "que he subido", "que subí",
    ]
    
    if any(pattern in query_lower for pattern in specific_patterns):
        return True
    
    return False

def test_storage_detection():
    """Prueba la detección de consultas sobre archivos del usuario."""
    
    # Casos que DEBEN ser detectados como consultas de storage
    should_detect = [
        # Patrones posesivos + gráficos
        "¿Qué significa mi gráfico de Monte Carlo?",
        "Analiza mis gráficos de riesgo",
        "Explícame mi reporte de correlación",
        "¿Cómo interpreto mi análisis de volatilidad?",
        "Dame un resumen de mi portafolio basado en mis archivos",
        "¿Qué dicen mis datos de rendimiento?",
        "Muéstrame mi historial de inversiones",
        
        # Gráficos específicos
        "mi gráfico de distribución",
        "mi chart de correlaciones",
        "mi imagen del heatmap",
        "mis visualizaciones del portafolio",
        
        # Tipos de archivos
        "analiza mi json de análisis",
        "qué contiene mi pdf del reporte",
        "lee mi markdown de resumen",
        
        # Patrones específicos
        "basado en mis archivos dime...",
        "según mis datos de análisis",
        "usando mis gráficos explica",
        "a partir de mis reportes",
        
        # Monte Carlo específico
        "mi simulación de Monte Carlo",
        "mi gráfico montecarlo",
        "mi análisis de simulación",
        
        # Acciones sobre archivos
        "analiza mi último reporte",
        "resume mis archivos",
        "interpreta mi gráfico",
        "explica mi visualización",
    ]
    
    # Casos que NO deben ser detectados (consultas generales)
    should_not_detect = [
        # Consultas generales sin posesivo
        "¿Qué es Monte Carlo?",
        "Explica qué es un gráfico de correlación",
        "¿Cómo funciona el análisis de riesgo?",
        "Dame información sobre diversificación",
        
        # Noticias y mercado
        "Noticias de NVIDIA hoy",
        "¿Cómo va el S&P 500?",
        "Precio de Bitcoin",
        
        # Conceptos generales
        "¿Qué es el Sharpe Ratio?",
        "Explica el drawdown máximo",
        "¿Qué significa VaR?",
    ]
    
    print("=" * 60)
    print("TEST DE DETECCIÓN DE CONSULTAS DE STORAGE DE USUARIO")
    print("=" * 60)
    
    # Probar casos positivos
    print("\n📗 CASOS QUE DEBEN DETECTARSE (storage_query=True):")
    print("-" * 50)
    
    passed = 0
    failed = 0
    
    for query in should_detect:
        result = _is_user_storage_query(query)
        status = "✅" if result else "❌"
        if result:
            passed += 1
        else:
            failed += 1
        print(f"{status} '{query[:60]}...' → {result}")
    
    print(f"\n   Pasaron: {passed}/{len(should_detect)}")
    
    # Probar casos negativos
    print("\n📕 CASOS QUE NO DEBEN DETECTARSE (storage_query=False):")
    print("-" * 50)
    
    neg_passed = 0
    neg_failed = 0
    
    for query in should_not_detect:
        result = _is_user_storage_query(query)
        status = "✅" if not result else "❌"
        if not result:
            neg_passed += 1
        else:
            neg_failed += 1
        print(f"{status} '{query[:60]}...' → {result}")
    
    print(f"\n   Pasaron: {neg_passed}/{len(should_not_detect)}")
    
    # Resumen final
    print("\n" + "=" * 60)
    print("RESUMEN FINAL:")
    total_tests = len(should_detect) + len(should_not_detect)
    total_passed = passed + neg_passed
    print(f"   Total tests: {total_tests}")
    print(f"   Pasaron: {total_passed}")
    print(f"   Fallaron: {total_tests - total_passed}")
    
    if total_passed == total_tests:
        print("\n🎉 TODOS LOS TESTS PASARON!")
    else:
        print(f"\n⚠️ Hay {total_tests - total_passed} tests que fallaron")
    
    print("=" * 60)
    
    return total_passed == total_tests


if __name__ == "__main__":
    success = test_storage_detection()
    sys.exit(0 if success else 1)
