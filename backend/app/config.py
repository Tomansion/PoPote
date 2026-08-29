from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    arango_url: str = "http://localhost:8529"
    arango_db: str = "everymeal"
    arango_user: str = "root"
    arango_password: str = "everymeal"

    # Comma-separated list, or "*" to allow any origin.
    # The APK runs from https://localhost (Capacitor's own origin), so that one
    # is always needed on top of whatever the web app is served from.
    cors_origins: str = "*"

    # Insert a handful of demo recipes when the collection is empty.
    seed_demo_data: bool = True

    @property
    def cors_origin_list(self) -> list[str]:
        if self.cors_origins.strip() == "*":
            return ["*"]
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


settings = Settings()
