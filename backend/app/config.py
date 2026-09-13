from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    postgres_host: str | None = None
    postgres_port: int = 5432
    postgres_db: str = "callout"
    postgres_user: str = "callout"
    postgres_password: str = "callout"

    # Only used when POSTGRES_HOST is unset (local dev outside Docker). The
    # shipped docker-compose.yml always sets POSTGRES_HOST, so the real
    # runtime is always Postgres.
    sqlite_path: str = "./dev.sqlite3"

    anthropic_api_key: str = ""
    ai_timeout_seconds: float = 8.0

    @property
    def database_url(self) -> str:
        if self.postgres_host:
            return (
                f"postgresql+psycopg://{self.postgres_user}:{self.postgres_password}"
                f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
            )
        return f"sqlite:///{self.sqlite_path}"


settings = Settings()
