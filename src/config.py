from typing import List, Optional, Union
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    APP_ENV: str = "development"
    DEBUG: bool = True
    API_V1_PREFIX: str = "/api/v1"
    PROJECT_NAME: str = "FUNDAMICS LMS API"
    VERSION: str = "1.4.0"

    HOST: str = "0.0.0.0"
    PORT: int = 8000

    DATABASE_URL: str = "postgresql+asyncpg://fundamics_app:fundamics_secure_pass@localhost:5432/fundamics_lms"
    SYNC_DATABASE_URL: str = "postgresql://fundamics_app:fundamics_secure_pass@localhost:5432/fundamics_lms"

    # Supabase credentials (optional)
    SUPABASE_URL: Optional[str] = None
    SUPABASE_KEY: Optional[str] = None

    JWT_SECRET_KEY: str = "change_this_to_a_secure_random_hex_key_in_production_min_32_chars"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    TIMEZONE: str = "Asia/Kolkata"

    STORAGE_BACKEND: str = "local"
    LOCAL_STORAGE_DIR: str = "./storage/notes"

    SECUREYE_DEVICE_SECRET: str = "change_this_to_a_secure_shared_device_secret"

    NOTIFICATIONS_ENABLED: bool = True
    ERP_API_KEY: str = "test_erp_key"

    CORS_ORIGINS: Union[str, List[str]] = "http://localhost:3000,http://localhost:5173,http://localhost:8081"

    @field_validator("CORS_ORIGINS", mode="after")
    @classmethod
    def assemble_cors_origins(cls, v: Union[str, List[str]]) -> List[str]:
        if isinstance(v, str):
            return [i.strip() for i in v.split(",") if i.strip()]
        return v


settings = Settings()
