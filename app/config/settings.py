from decouple import config


class Settings:
    # Application settings
    APP_NAME: str = config("APP_NAME", default="Alsabouh Web App")
    DEBUG: bool = config("DEBUG", default=False, cast=bool)

    # Database settings - Supports any PostgreSQL URL (Supabase, Neon, AWS RDS, Local)
    DATABASE_URL: str = config(
        "DATABASE_URL",
        default="postgresql+psycopg2://postgres:postgres@localhost:5432/postgres"
    )

    # Supabase Settings
    SUPABASE_URL: str = config("SUPABASE_URL", default="")
    SUPABASE_KEY: str = config("SUPABASE_KEY", default="")
    SUPABASE_BUCKET_NAME: str = config("SUPABASE_BUCKET_NAME", default="alsabouh-storage")

    # JWT Security settings
    JWT_SECRET_KEY: str = config("JWT_SECRET_KEY", default="super_secret_jwt_alsabouh_key")
    JWT_ALGORITHM: str = config("JWT_ALGORITHM", default="HS256")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = config("ACCESS_TOKEN_EXPIRE_MINUTES", default=1440, cast=int)

    # Admin seed credentials
    ADMIN_EMAIL: str = config("ADMIN_EMAIL", default="admin@alsabouh.com")
    ADMIN_PASSWORD: str = config("ADMIN_PASSWORD", default="Admin@123456")
    ADMIN_NAME: str = config("ADMIN_NAME", default="Alsabouh Super Admin")

    # SMTP / Email settings
    SMTP_HOST: str = config("SMTP_HOST", default="smtp.gmail.com")
    SMTP_PORT: int = config("SMTP_PORT", default=587, cast=int)
    SMTP_USER: str = config("SMTP_USER", default="")
    SMTP_PASSWORD: str = config("SMTP_PASSWORD", default="")
    EMAILS_FROM_NAME: str = config("EMAILS_FROM_NAME", default="Alsabouh")


settings = Settings()
