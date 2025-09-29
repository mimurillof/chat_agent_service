import os
from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    """Configuración del servicio de agente de chat"""
    
    # API Keys
    gemini_api_key: Optional[str] = None
    google_api_key: Optional[str] = None
    supabase_url: Optional[str] = None
    supabase_service_role_key: Optional[str] = None
    supabase_anon_key: Optional[str] = None
    supabase_bucket_name: Optional[str] = None
    supabase_base_prefix: Optional[str] = None
    supabase_base_prefix_2: Optional[str] = None
    enable_supabase_upload: bool = False
    supabase_cleanup_after_tests: bool = False
    
    # Configuración del servicio
    service_host: str = "0.0.0.0"
    service_port: int = 8001
    service_name: str = "Chat Agent Service"
    service_version: str = "1.0.0"
    
    # Backend Service URL (para comunicación entre servicios)
    backend_service_url: str = "http://localhost:8000"
    backend_service_url_prod: str = "https://horizon-backend-316b23e32b8b.herokuapp.com"
    
    # Configuración CORS (orígenes permitidos)
    cors_origins: list[str] = [
        # Desarrollo local
        "http://localhost:3000",
        "http://localhost:8000", 
        "http://localhost:5173",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:8000",
        "http://127.0.0.1:5173",
        # Producción
        "https://horizon-backend-316b23e32b8b.herokuapp.com",
        "https://chat-agent-horizon-cc5e16d4b37e.herokuapp.com"
    ]
    
    # Configuración de logging
    log_level: str = "INFO"
    
    # Configuración de modelos
    model_flash: str = "gemini-2.5-flash"
    model_pro: str = "gemini-2.5-pro"
    default_currency: str = "USD"
    
    # Environment
    environment: str = "development"
    
    # Configuración Pydantic v2 para BaseSettings
    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=False,
        extra="ignore",  # Ignorar variables de entorno no declaradas
    )

    def get_api_key(self) -> Optional[str]:
        """Obtener la clave API disponible"""
        return self.gemini_api_key or self.google_api_key
    
    def get_backend_url(self) -> str:
        """Obtener la URL del backend según el entorno"""
        if self.environment == "production":
            return self.backend_service_url_prod
        return self.backend_service_url

# Instancia global de configuración
settings = Settings()