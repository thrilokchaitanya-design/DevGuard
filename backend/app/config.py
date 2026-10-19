from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    app_name: str = "DevGuard"
    app_env: str = "development"
    auth_mode: str = "local"
    database_url: str = "sqlite:///./devguard.db"
    github_webhook_secret: str = ""
    allowed_origins: str = "http://localhost:5173,http://127.0.0.1:5173,http://localhost:8080"
    session_secret: str = ""
    session_cookie_samesite: str = "strict"
    demo_access_password: str = ""
    session_ttl_seconds: int = 28800
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"
    log_retention_days: int = 30
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @property
    def cors_origins(self) -> list[str]:
        return [origin.strip().rstrip("/") for origin in self.allowed_origins.split(",") if origin.strip()]

    def validate_security_config(self) -> None:
        if self.auth_mode not in {"local", "demo"}:
            raise ValueError("AUTH_MODE must be 'local' or 'demo'. OAuth is not configured in this release.")
        if self.app_env.lower() == "production":
            if self.auth_mode != "demo":
                raise ValueError("Production requires AUTH_MODE=demo; loopback-only local auth is not available in production.")
            if len(self.session_secret) < 32:
                raise ValueError("Production requires SESSION_SECRET with at least 32 characters.")
            if len(self.demo_access_password) < 14:
                raise ValueError("Production requires DEMO_ACCESS_PASSWORD with at least 14 characters.")
            if not self.cors_origins or any(origin == "*" for origin in self.cors_origins):
                raise ValueError("Production ALLOWED_ORIGINS must list specific HTTPS origins.")
            if any(not origin.startswith("https://") for origin in self.cors_origins):
                raise ValueError("Production ALLOWED_ORIGINS must use HTTPS.")
            if not self.database_url.lower().startswith(("postgres://", "postgresql://", "postgresql+psycopg://")):
                raise ValueError("Production requires a PostgreSQL DATABASE_URL; local SQLite is not persistent production storage.")
        if self.session_cookie_samesite.lower() not in {"strict", "lax", "none"}:
            raise ValueError("SESSION_COOKIE_SAMESITE must be Strict, Lax, or None.")
        if self.session_cookie_samesite.lower() == "none" and self.app_env.lower() != "production":
            raise ValueError("SESSION_COOKIE_SAMESITE=None requires APP_ENV=production and secure cookies.")


def sqlalchemy_database_url(value: str) -> str:
    """Use the psycopg 3 driver declared in requirements for Render Postgres URLs."""
    if value.startswith("postgres://"):
        return "postgresql+psycopg://" + value[len("postgres://"):]
    if value.startswith("postgresql://"):
        return "postgresql+psycopg://" + value[len("postgresql://"):]
    return value

settings = Settings()
