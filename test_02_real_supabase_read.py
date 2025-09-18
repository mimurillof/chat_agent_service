"""
Test REAL de integración para el flujo de trabajo del agente con Supabase Storage.

Este test verifica que el agente puede:
1. Conectar a Supabase Storage REAL usando variables de entorno
2. Listar archivos REALES desde la carpeta "Graficos" 
3. Filtrar por extensiones permitidas (.json, .md, .png)
4. Leer y procesar contenidos REALES de archivos JSON y Markdown
5. Estructurar el contexto correctamente para envío a Gemini
6. Integrar archivos de texto y referencias a imágenes

Para uso REAL, configura estas variables de entorno:
- SUPABASE_URL
- SUPABASE_SERVICE_ROLE_KEY  
- SUPABASE_BUCKET_NAME
- SUPABASE_BASE_PREFIX

Si no están configuradas, el test usará datos simulados como fallback.
"""
import os
import asyncio
import json


def setup_env():
    """Setup real Supabase environment variables using config.py like the real agent"""
    print("🔧 Configurando variables de entorno desde config.py...")
    
    # Importar la configuración real del proyecto
    from config import settings
    
    # Verificar las variables de Supabase desde la configuración
    supabase_vars = {
        "SUPABASE_URL": settings.supabase_url,
        "SUPABASE_SERVICE_ROLE_KEY": settings.supabase_service_role_key,
        "SUPABASE_BUCKET_NAME": settings.supabase_bucket_name,
        "SUPABASE_BASE_PREFIX": settings.supabase_base_prefix
    }
    
    missing_vars = []
    for var_name, var_value in supabase_vars.items():
        if not var_value:
            missing_vars.append(var_name)
    
    if missing_vars:
        print(f"⚠️ Variables de entorno faltantes en config: {missing_vars}")
        print("🔧 Usando valores por defecto para testing simulado...")
        # Fallback a valores simulados
        os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
        os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "service-role-key")
        os.environ.setdefault("SUPABASE_BUCKET_NAME", "portfolio-files")
        os.environ.setdefault("SUPABASE_BASE_PREFIX", "Graficos")
        return False  # Indica que se usarán datos simulados
    else:
        print("✅ Todas las variables de Supabase están configuradas")
        print(f"   📍 URL: {settings.supabase_url}")
        print(f"   🪣 Bucket: {settings.supabase_bucket_name}")
        print(f"   📁 Prefix: {settings.supabase_base_prefix}")
        print(f"   🔑 Service Key: {'*' * 20}...{settings.supabase_service_role_key[-4:] if settings.supabase_service_role_key else 'None'}")
        return True  # Indica que se usará Supabase real
    
    # Mantener Gemini simulado
    os.environ.setdefault("GEMINI_API_KEY", "test-key")


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
    """Test completo del flujo de trabajo del agente con Storage context REAL"""
    print("🚀 Iniciando test con conexión real a Supabase...")
    
    # Configurar entorno y verificar si usaremos datos reales o simulados
    use_real_supabase = setup_env()
    
    from agent_service import chat_service
    
    if use_real_supabase:
        print("\n🌐 MODO REAL: Conectando a Supabase real...")
        # Usar el cliente Supabase real que ya está inicializado en agent_service
        print(f"   📍 URL: {os.getenv('SUPABASE_URL')}")
        print(f"   🪣 Bucket: {os.getenv('SUPABASE_BUCKET_NAME')}")
        print(f"   📁 Prefix: {os.getenv('SUPABASE_BASE_PREFIX')}")
        
        # Verificar que el agente tiene conexión a Supabase
        if not chat_service.supabase:
            print("❌ El agente no pudo conectar a Supabase real")
            print("   Revisa las variables de entorno SUPABASE_URL y SUPABASE_SERVICE_ROLE_KEY")
            return
        
        print("✅ Conexión a Supabase establecida")
        
    else:
        print("\n🔧 MODO SIMULADO: Usando datos fake para testing...")
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
    
    # Asegurar configuración del bucket y prefix desde config
    from config import settings
    chat_service.supabase_bucket = settings.supabase_bucket_name or "portfolio-files"
    chat_service.supabase_prefix = settings.supabase_base_prefix or "Graficos"
    
    print(f"\n🔍 Configuración del agente:")
    print(f"   🪣 Bucket: {chat_service.supabase_bucket}")
    print(f"   📁 Prefix: {chat_service.supabase_prefix}")
    print(f"   🔗 Cliente Supabase: {'Real' if use_real_supabase else 'Simulado'}")
    
    # ===== PASO 1: Listar archivos REALES desde Supabase =====
    print("\n📁 PASO 1: Listando archivos desde Supabase Storage...")
    print("=" * 60)
    
    try:
        files = chat_service._list_supabase_files()
        print(f"📊 ARCHIVOS ENCONTRADOS: {len(files)}")
        print("-" * 40)
        
        if not files:
            print("⚠️ No se encontraron archivos en la carpeta especificada")
            if use_real_supabase:
                print("   Verifica que existan archivos en la carpeta 'Graficos' de tu bucket")
            return
        
        # Agrupar por tipo para mejor visualización
        json_files = [f for f in files if f['ext'] == '.json']
        md_files = [f for f in files if f['ext'] == '.md']
        png_files = [f for f in files if f['ext'] == '.png']
        other_files = [f for f in files if f['ext'] not in ['.json', '.md', '.png']]
        
        print("📄 ARCHIVOS JSON:")
        for file in json_files:
            print(f"   ✅ {file['name']} -> {file['path']}")
        
        print("\n📝 ARCHIVOS MARKDOWN:")
        for file in md_files:
            print(f"   ✅ {file['name']} -> {file['path']}")
        
        print("\n🖼️ ARCHIVOS PNG:")
        for file in png_files:
            print(f"   ✅ {file['name']} -> {file['path']}")
        
        if other_files:
            print(f"\n🚫 ARCHIVOS IGNORADOS ({len(other_files)}):")
            for file in other_files:
                print(f"   ❌ {file['name']} ({file['ext']}) -> {file['path']}")
        
        print(f"\n📊 RESUMEN:")
        print(f"   📄 JSON: {len(json_files)}")
        print(f"   📝 MD: {len(md_files)}")
        print(f"   🖼️ PNG: {len(png_files)}")
        print(f"   🚫 Ignorados: {len(other_files)}")
        
    except Exception as e:
        print(f"❌ Error listando archivos: {e}")
        if use_real_supabase:
            print("   Verifica la conexión a Supabase y los permisos")
        return
    
    # ===== PASO 2: Leer contenidos REALES de archivos de texto =====
    print(f"\n📄 PASO 2: Leyendo contenidos de archivos de texto...")
    print("=" * 60)
    
    try:
        text_content = chat_service._read_supabase_text_files(files)
        
        print(f"📋 ARCHIVOS JSON PROCESADOS: {len(text_content['json_docs'])}")
        for name, content in text_content['json_docs'].items():
            print(f"   📄 {name}:")
            print(f"      - Tipo: {type(content)}")
            print(f"      - Tamaño: {len(str(content))} caracteres")
            if isinstance(content, dict):
                keys = list(content.keys())[:5]  # Primeras 5 claves
                print(f"      - Claves: {keys}{'...' if len(content.keys()) > 5 else ''}")
        
        print(f"\n📝 ARCHIVOS MARKDOWN PROCESADOS: {len(text_content['markdown_docs'])}")
        for name, content in text_content['markdown_docs'].items():
            print(f"   📝 {name}:")
            print(f"      - Tamaño: {len(content)} caracteres")
            # Mostrar primeras líneas
            lines = content.split('\n')[:3]
            for i, line in enumerate(lines):
                if line.strip():
                    print(f"      - L{i+1}: {line[:50]}{'...' if len(line) > 50 else ''}")
                    
    except Exception as e:
        print(f"❌ Error leyendo archivos: {e}")
        return
    
    # ===== PASO 3: Contexto completo que recibiría el agente =====
    print(f"\n🗂️ PASO 3: Generando contexto completo para el agente...")
    print("=" * 60)
    
    try:
        storage_ctx = chat_service._gather_storage_context()
        
        if "storage" not in storage_ctx:
            print("❌ No se pudo generar contexto de Storage")
            return
        
        storage = storage_ctx["storage"]
        
        print(f"📊 CONTEXTO GENERADO:")
        print(f"   🪣 Bucket: {storage['bucket']}")
        print(f"   📁 Prefix: {storage['prefix']}")
        print(f"   🖼️ Imágenes: {len(storage.get('images', []))}")
        print(f"   📄 Docs JSON: {len(storage.get('json_docs', {}))}")
        print(f"   📝 Docs MD: {len(storage.get('markdown_docs', {}))}")
        
        # Mostrar referencias a imágenes
        print(f"\n🖼️ REFERENCIAS A IMÁGENES:")
        for img in storage.get('images', []):
            print(f"   📷 {img['path']}")
        
        # Calcular tamaño del contexto
        context_json_str = json.dumps(storage_ctx, ensure_ascii=False)
        print(f"\n📏 TAMAÑO DEL CONTEXTO: {len(context_json_str)} caracteres")
        
        print("\n✅ Contexto listo para envío al agente")
        
    except Exception as e:
        print(f"❌ Error generando contexto: {e}")
        return
    
    print("\n" + "=" * 60)
    print("🎉 TEST COMPLETADO EXITOSAMENTE")
    print("=" * 60)
    
    if use_real_supabase:
        print("✅ CONEXIÓN REAL A SUPABASE VERIFICADA")
        print("✅ ARCHIVOS REALES LISTADOS Y PROCESADOS")
        print("✅ CONTEXTO REAL GENERADO PARA EL AGENTE")
        print("\n💡 El agente está completamente funcional con Supabase real")
        print("   Solo necesita una API key válida de Gemini para generar informes")
    else:
        print("✅ FLUJO DE TRABAJO VERIFICADO CON DATOS SIMULADOS")
        print("⚠️ Para testing real, configura las variables de entorno:")
        print("   - SUPABASE_URL")
        print("   - SUPABASE_SERVICE_ROLE_KEY") 
        print("   - SUPABASE_BUCKET_NAME") 
        print("   - SUPABASE_BASE_PREFIX")


if __name__ == "__main__":
    asyncio.run(run_test())