from pydantic_settings import BaseSettings
from pydantic import ConfigDict, field_validator
from typing import List


class Settings(BaseSettings):
    """Application configuration"""
    
    # Application
    app_name: str = "CSCATTENDANCE"
    app_version: str = "v1"
    debug: bool = False
    
    # Database
    mongodb_url: str = "mongodb+srv://username:password@cluster.mongodb.net/?retryWrites=true&w=majority"
    mongodb_database: str = "workspace_center"
    
    # Security
    secret_key: str = "your-secret-key-here-change-in-production"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 720
    
    # CORS
    allowed_origins: str = "http://localhost:3000,http://localhost:8000,http://localhost:8001,http://localhost:8002"
    
    # Server
    server_port: int = 8000
    server_host: str = "0.0.0.0"
    
    # Email Configuration - Resend
    resend_api_key: str = ""
    resend_from_email: str = "noreply@cchub.com"
    resend_from_name: str = "CSCATTENDANCE Entry System"
    
    model_config = ConfigDict(
        env_file=".env",
        case_sensitive=False,
        extra="ignore"
    )
    
    @property
    def get_allowed_origins(self) -> List[str]:
        """Parse allowed origins as a list"""
        if isinstance(self.allowed_origins, list):
            return self.allowed_origins
        return [origin.strip() for origin in self.allowed_origins.split(",")]


settings = Settings()
