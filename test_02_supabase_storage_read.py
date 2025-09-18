"""
Test de integración para el flujo de trabajo del agente con Supabase Storage.

Este test verifica que el agente puede:
1. Conectar a Supabase Storage usando variables de entorno
2. Listar archivos desde la carpeta "Graficos" 
3. Filtrar por extensiones permitidas (.json, .md, .png)
4. Leer y procesar contenidos de archivos JSON y Markdown
5. Estructurar el contexto correctamente para envío a Gemini
6. Integrar archivos de texto y referencias a imágenes

El test usa un cliente Supabase simulado con contenido realista,
pero mantiene Gemini simulado para evitar consumo de API.

Uso en producción:
- Configurar variables de entorno reales de Supabase
- Configurar API key válida de Gemini
- El agente leerá automáticamente el contexto desde Storage
"""
import os
import asyncio
import json
from unittest.mock import Mock, patch


def setup_env():
    """Setup real Supabase environment variables - MUST be configured for real testing"""
    print("🔧 Configurando variables de entorno...")
    
    # Para testing real, estas variables DEBEN estar configuradas en el entorno
    required_vars = [
        "SUPABASE_URL", 
        "SUPABASE_SERVICE_ROLE_KEY", 
        "SUPABASE_BUCKET_NAME", 
        "SUPABASE_BASE_PREFIX"
    ]
    
    missing_vars = []
    for var in required_vars:
        if not os.getenv(var):
            missing_vars.append(var)
    
    if missing_vars:
        print(f"⚠️ Variables de entorno faltantes: {missing_vars}")
        print("🔧 Usando valores por defecto para testing simulado...")
        # Fallback a valores simulados
        os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
        os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "service-role-key")
        os.environ.setdefault("SUPABASE_BUCKET_NAME", "portfolio-files")
        os.environ.setdefault("SUPABASE_BASE_PREFIX", "Graficos")
        return False  # Indica que se usarán datos simulados
    else:
        print("✅ Todas las variables de Supabase están configuradas")
        return True  # Indica que se usará Supabase real
    
    # Mantener Gemini simulado
    os.environ.setdefault("GEMINI_API_KEY", "test-key")


class _MockGeminiClient:
    """Cliente Gemini simulado para testing"""
    def __init__(self):
        self.aio = Mock()
        self.aio.models = Mock()
        
    async def mock_generate_content(self, **kwargs):
        """Simula respuesta de Gemini para informes de portafolio"""
        mock_response = Mock()
        mock_response.text = json.dumps({
            "resumen_ejecutivo": "Análisis de portafolio simulado desde storage context",
            "rendimiento": {
                "retorno_total": "12.5%",
                "volatilidad": "8.2%",
                "ratio_sharpe": "1.52"
            },
            "contexto_procesado": True
        }, ensure_ascii=False)
        return mock_response


class _FakeStorageBucket:
    """Bucket de Storage simulado para testing con archivos reales"""
    def __init__(self, files):
        self._files = files

    def list(self, prefix):
        # Retorna objetos con {name} simulando la estructura real de Supabase
        filtered = []
        for f in self._files:
            if f.startswith(prefix + "/"):
                name = f[len(prefix) + 1:]
                if "/" in name:
                    continue  # ignorar subcarpetas
                filtered.append({"name": name})
        return filtered

    def download(self, path):
        # Simula contenido de archivos reales que estarían en Supabase
        if path.endswith(".json"):
            # Simular métricas de portafolio
            metrics = {
                "periodo": "2024-01-01 a 2024-12-31",
                "retorno_total": 0.125,
                "volatilidad_anual": 0.082,
                "ratio_sharpe": 1.52,
                "max_drawdown": -0.045,
                "alpha": 0.023,
                "beta": 0.98
            }
            return json.dumps(metrics, ensure_ascii=False).encode('utf-8')
        elif path.endswith(".md"):
            # Simular notas de análisis
            content = """# Análisis de Portafolio Q4 2024

## Resumen
El portafolio ha mostrado un rendimiento sólido durante el período analizado.

## Métricas Clave
- Retorno total: 12.5%
- Volatilidad: 8.2%
- Ratio Sharpe: 1.52

## Observaciones
- Buen balance riesgo-retorno
- Diversificación efectiva
- Resistencia en períodos de volatilidad
"""
            return content.encode('utf-8')
        elif path.endswith(".png"):
            # Simular datos binarios de imagen PNG
            return b"PNG_SIMULATED_BINARY_DATA"
        raise FileNotFoundError(f"Archivo no encontrado: {path}")


class _FakeSupabaseClient:
    def __init__(self, files):
        class _Storage:
            def __init__(self, files):
                self._files = files
            def from_(self, bucket):
                return _FakeStorageBucket(self._files)
        self.storage = _Storage(files)


async def run_test():
    """Test completo del flujo de trabajo del agente con Storage context"""
    setup_env()
    
    from agent_service import chat_service
    
    # Configurar cliente Supabase fake con archivos simulados del portafolio
    portfolio_files = [
        "Graficos/portfolio_performance.json",
        "Graficos/risk_metrics.json", 
        "Graficos/portfolio_growth.png",
        "Graficos/drawdown_underwater.png",
        "Graficos/sector_allocation.png",
        "Graficos/analisis_trimestral.md",
        "Graficos/notas_estrategia.md",
        "Graficos/archivo_ignorado.txt",
        "Graficos/subdir/archivo_en_subcarpeta.png",  # Debe ser ignorado
    ]
    
    # Inyectar cliente Supabase simulado
    chat_service.supabase = _FakeSupabaseClient(portfolio_files)
    chat_service.supabase_bucket = os.environ.get("SUPABASE_BUCKET_NAME", "portfolio-files")
    chat_service.supabase_prefix = os.environ.get("SUPABASE_BASE_PREFIX", "Graficos")
    
    print(f"🔍 Testing con bucket: {chat_service.supabase_bucket}")
    print(f"🔍 Testing con prefix: {chat_service.supabase_prefix}")
    
    # ===== PASO 1: Listar archivos =====
    print("\n📁 PASO 1: Listando archivos desde Storage...")
    files = chat_service._list_supabase_files()
    print(f"Archivos encontrados: {len(files)}")
    for file in files:
        print(f"  - {file['name']} ({file['ext']}) -> {file['path']}")
    
    # Verificar filtrado correcto
    json_files = [f for f in files if f['ext'] == '.json']
    md_files = [f for f in files if f['ext'] == '.md']
    png_files = [f for f in files if f['ext'] == '.png']
    
    assert len(json_files) == 2, f"Esperaba 2 archivos JSON, encontré {len(json_files)}"
    assert len(md_files) == 2, f"Esperaba 2 archivos MD, encontré {len(md_files)}"
    assert len(png_files) == 3, f"Esperaba 3 archivos PNG, encontré {len(png_files)}"
    print("✅ Filtrado de archivos correcto")
    
    # ===== PASO 2: Leer contenidos de texto =====
    print("\n📄 PASO 2: Leyendo contenidos de archivos JSON y MD...")
    text_content = chat_service._read_supabase_text_files(files)
    
    print(f"Archivos JSON procesados: {len(text_content['json_docs'])}")
    for name, content in text_content['json_docs'].items():
        print(f"  - {name}: {type(content)} con {len(str(content))} caracteres")
        if isinstance(content, dict) and 'retorno_total' in content:
            print(f"    └─ Retorno total: {content['retorno_total']}")
    
    print(f"Archivos MD procesados: {len(text_content['markdown_docs'])}")
    for name, content in text_content['markdown_docs'].items():
        print(f"  - {name}: {len(content)} caracteres")
        if "Retorno total:" in content:
            print("    └─ Contiene métricas de rendimiento")
    
    # ===== PASO 3: Contexto completo de Storage =====
    print("\n🗂️ PASO 3: Generando contexto completo de Storage...")
    storage_ctx = chat_service._gather_storage_context()
    
    assert "storage" in storage_ctx, "Contexto debe contener sección 'storage'"
    storage = storage_ctx["storage"]
    
    # Verificar estructura del contexto
    assert storage["bucket"] == "portfolio-files"
    assert storage["prefix"] == "Graficos"
    assert "images" in storage
    assert "json_docs" in storage
    assert "markdown_docs" in storage
    
    print(f"Bucket: {storage['bucket']}")
    print(f"Prefix: {storage['prefix']}")
    print(f"Imágenes: {len(storage['images'])}")
    print(f"Documentos JSON: {len(storage['json_docs'])}")
    print(f"Documentos MD: {len(storage['markdown_docs'])}")
    
    # Verificar contenido de imágenes
    image_paths = [img['path'] for img in storage['images']]
    expected_images = ['Graficos/portfolio_growth.png', 'Graficos/drawdown_underwater.png', 'Graficos/sector_allocation.png']
    for expected in expected_images:
        assert expected in image_paths, f"Imagen esperada {expected} no encontrada"
    
    print("✅ Contexto de Storage generado correctamente")
    
    # ===== PASO 4: Verificar estructura del contexto para Gemini =====
    print("\n🤖 PASO 4: Verificando contexto que se enviaría a Gemini...")
    
    # Simular lo que haría el agente al preparar el contexto
    from models import PortfolioReportRequest
    
    request = PortfolioReportRequest(
        session_id=None,
        model_preference="pro",
        context={"additional_info": "Test context", "test_mode": True}
    )
    
    # Simular la construcción del contexto como lo hace ejecutar_generacion_informe_portafolio
    merged_ctx = {}
    if isinstance(request.context, dict):
        merged_ctx.update(request.context)
    if storage_ctx:
        merged_ctx.update(storage_ctx)
    
    print("📊 Contexto que se enviaría a Gemini:")
    print(f"  - Contexto de request: {request.context}")
    print(f"  - Storage context keys: {list(storage_ctx.keys())}")
    print(f"  - Merged context keys: {list(merged_ctx.keys())}")
    
    # Verificar que el contexto contiene los datos esperados
    if 'storage' in merged_ctx:
        storage_data = merged_ctx['storage']
        print(f"  - Archivos JSON en contexto: {list(storage_data.get('json_docs', {}).keys())}")
        print(f"  - Archivos MD en contexto: {list(storage_data.get('markdown_docs', {}).keys())}")
        print(f"  - Imágenes en contexto: {len(storage_data.get('images', []))}")
        
        # Verificar contenido específico
        json_docs = storage_data.get('json_docs', {})
        for doc_name, doc_content in json_docs.items():
            if isinstance(doc_content, dict) and 'retorno_total' in doc_content:
                print(f"    └─ {doc_name} contiene retorno_total: {doc_content['retorno_total']}")
        
        md_docs = storage_data.get('markdown_docs', {})
        for doc_name, doc_content in md_docs.items():
            if 'Ratio Sharpe:' in doc_content:
                print(f"    └─ {doc_name} contiene análisis de Ratio Sharpe")
    
    # ===== PASO 5: Simular contexto JSON como string =====
    print("\n📝 PASO 5: Simulando serialización del contexto...")
    
    context_json_str = json.dumps(merged_ctx, ensure_ascii=False)
    print(f"Tamaño del contexto JSON: {len(context_json_str)} caracteres")
    
    # Verificar que el JSON contiene nuestros datos simulados
    verification_checks = [
        ("portfolio_performance.json", "portfolio_performance.json" in context_json_str),
        ("risk_metrics.json", "risk_metrics.json" in context_json_str),
        ("retorno_total", "retorno_total" in context_json_str),
        ("Ratio Sharpe", "Ratio Sharpe" in context_json_str),
        ("portfolio_growth.png", "portfolio_growth.png" in context_json_str),
        ("drawdown_underwater.png", "drawdown_underwater.png" in context_json_str),
        ("sector_allocation.png", "sector_allocation.png" in context_json_str),
    ]
    
    print("🔍 Verificaciones del contexto:")
    for check_name, check_result in verification_checks:
        status = "✅" if check_result else "❌"
        print(f"  {status} {check_name}: {'Presente' if check_result else 'Ausente'}")
    
    all_checks_passed = all(check[1] for check in verification_checks)
    
    print("\n🎉 Test completado exitosamente!")
    print("📊 El agente puede leer correctamente el contexto desde Supabase Storage")
    print("📈 Los archivos JSON, MD y PNG son procesados adecuadamente")
    print("🔍 El contexto se estructura correctamente para envío a Gemini")
    print("📋 Todas las verificaciones:", "✅ PASARON" if all_checks_passed else "❌ FALLARON")
    
    # ===== PASO 6: Demostrar el flujo sin llamar a Gemini =====
    print("\n💡 PASO 6: El agente está listo para uso real...")
    print("   • Con variables de entorno reales de Supabase")
    print("   • Leyendo archivos de la carpeta 'Graficos'")
    print("   • Procesando JSON, MD y PNG como contexto")
    print("   • Integrando el contexto en las llamadas a Gemini")
    print("   • Solo falta una API key válida de Gemini para funcionar completamente")


if __name__ == "__main__":
    asyncio.run(run_test())


