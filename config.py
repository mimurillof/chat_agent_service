import os
from typing import Optional
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    """Configuración del servicio de agente de chat"""
    
    # API Keys
    gemini_api_key: Optional[str] = None
    google_api_key: Optional[str] = None
    
    # Configuración del servicio
    service_host: str = "0.0.0.0"
    service_port: int = 8001
    service_name: str = "Chat Agent Service"
    service_version: str = "1.0.0"
    
    # Configuración CORS
    cors_origins: list[str] = ["http://localhost:3000", "http://localhost:8000"]
    
    # Configuración de logging
    log_level: str = "INFO"
    
    # Configuración de modelos
    model_flash: str = "gemini-2.5-flash"
    model_pro: str = "gemini-2.5-pro"
    
    class Config:
        env_file = ".env"
        case_sensitive = False

    def get_api_key(self) -> Optional[str]:
        """Obtener la clave API disponible"""
        return self.gemini_api_key or self.google_api_key

# Instancia global de configuración
settings = Settings()