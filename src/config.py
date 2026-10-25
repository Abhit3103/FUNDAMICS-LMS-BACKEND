from typing import List, Optional, Union
from pydantic import Field, field_validator, ValidationInfo
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

    # Hostinger / Standard SMTP Email Configuration
    SMTP_HOST: str = "smtp.hostinger.com"
    SMTP_PORT: int = 587
    SMTP_USE_TLS: bool = True
    SMTP_USERNAME: Optional[str] = None
    SMTP_PASSWORD: Optional[str] = None
    MAIL_FROM: str = "info@fundemicstutorials.in"
    MAIL_FROM_NAME: str = "FUNDAMICS TUTORIALS"
    FRONTEND_BASE_URL: str = "http://localhost:3000"

    # Token Expiration Settings
    EMAIL_VERIFICATION_TOKEN_EXPIRE_HOURS: int = 24
    PASSWORD_RESET_TOKEN_EXPIRE_MINUTES: int = 60

    # WhatsApp Business Cloud API
    WHATSAPP_API_TOKEN: Optional[str] = None
    WHATSAPP_PHONE_NUMBER_ID: Optional[str] = None
    WHATSAPP_BUSINESS_ACCOUNT_ID: Optional[str] = None

    # CORS Whitelist & Dynamic Origins
    CORS_ORIGINS: Union[str, List[str]] = (
        "http://localhost:8081,http://127.0.0.1:8081,http://localhost:3000,http://127.0.0.1:3000,http://localhost:5173,http://127.0.0.1:5173"
    )
    PRODUCTION_CORS_ORIGINS: Optional[Union[str, List[str]]] = None
    ADDITIONAL_CORS_ORIGINS: Optional[Union[str, List[str]]] = None

    @field_validator("CORS_ORIGINS", mode="after")
    @classmethod
    def assemble_cors_origins(cls, v: Union[str, List[str]], info: ValidationInfo) -> List[str]:
        origins: List[str] = []
        if isinstance(v, str):
            origins = [i.strip() for i in v.split(",") if i.strip()]
        elif isinstance(v, list):
            origins = [str(i).strip() for i in v if str(i).strip()]

        # Ensure both localhost and 127.0.0.1 loopbacks for dev ports exist
        dev_ports = ["8081", "3000", "5173"]
        for port in dev_ports:
            local_host = f"http://localhost:{port}"
            local_ip = f"http://127.0.0.1:{port}"
            if local_host in origins and local_ip not in origins:
                origins.append(local_ip)
            if local_ip in origins and local_host not in origins:
                origins.append(local_host)

        # Merge production and additional origins if provided via environment
        extra_sources = []
        if info.data:
            for key in ("PRODUCTION_CORS_ORIGINS", "ADDITIONAL_CORS_ORIGINS"):
                val = info.data.get(key)
                if val:
                    extra_sources.append(val)

        for src in extra_sources:
            if isinstance(src, str):
                items = [i.strip() for i in src.split(",") if i.strip()]
            elif isinstance(src, list):
                items = [str(i).strip() for i in src if str(i).strip()]
            else:
                items = []

            for item in items:
                if item not in origins:
                    origins.append(item)

        return origins


settings = Settings()
