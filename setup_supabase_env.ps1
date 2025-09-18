# Script para configurar variables de entorno de Supabase
# Ejecuta este archivo para configurar las variables antes del test

# ============================================================
# CONFIGURACIÓN DE SUPABASE PARA TEST REAL
# ============================================================

# 1. Copia estos comandos y actualiza con tus valores reales:

# Para Windows PowerShell:
$env:SUPABASE_URL = "https://tu-proyecto.supabase.co"
$env:SUPABASE_SERVICE_ROLE_KEY = "tu-service-role-key-aqui"
$env:SUPABASE_BUCKET_NAME = "portfolio-files"
$env:SUPABASE_BASE_PREFIX = "Graficos"

# Para Linux/Mac bash:
# export SUPABASE_URL="https://tu-proyecto.supabase.co"
# export SUPABASE_SERVICE_ROLE_KEY="tu-service-role-key-aqui"
# export SUPABASE_BUCKET_NAME="portfolio-files"
# export SUPABASE_BASE_PREFIX="Graficos"

# ============================================================
# CÓMO OBTENER TUS VALORES REALES:
# ============================================================

# 1. SUPABASE_URL:
#    - Ve a tu proyecto en https://supabase.com/dashboard
#    - En Settings > API
#    - Copia la "Project URL"

# 2. SUPABASE_SERVICE_ROLE_KEY:
#    - En la misma página Settings > API  
#    - Copia la "service_role" secret key (NO la anon key)

# 3. SUPABASE_BUCKET_NAME:
#    - Ve a Storage en tu dashboard de Supabase
#    - Usa el nombre de tu bucket (ej: "portfolio-files")

# 4. SUPABASE_BASE_PREFIX:
#    - Es la carpeta dentro del bucket donde están tus archivos
#    - Ej: "Graficos" para la carpeta /Graficos/

# ============================================================
# DESPUÉS DE CONFIGURAR, EJECUTA:
# ============================================================
# python test_02_real_supabase_read.py

Write-Host "🔧 Script de configuración de variables de entorno"
Write-Host "   Edita este archivo con tus valores reales de Supabase"
Write-Host "   Luego ejecuta: python test_02_real_supabase_read.py"