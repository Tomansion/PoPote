from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    arango_url: str = "http://localhost:8529"
    arango_db: str = "popote"
    arango_user: str = "root"
    arango_password: str = "popote"

    # Comma-separated list, or "*" to allow any origin.
    # The APK runs from https://localhost (Capacitor's own origin), so that one
    # is always needed on top of whatever the web app is served from.
    cors_origins: str = "*"

    # Give every newly registered account a copy of the demo recipes.
    # Recipes are per-user now, so there is no ownerless set to seed at boot.
    seed_demo_data: bool = True

    # Signing key for the session tokens. Leave empty and the backend generates
    # one on first start and stores it in ArangoDB, so tokens keep working
    # across restarts and redeploys without anything to configure. Set it
    # explicitly to share one key across several backends.
    jwt_secret: str = ""

    # Tokens are deliberately long-lived: this is a friends-and-family app and
    # nobody should be asked to log in again on their phone every few weeks.
    jwt_ttl_days: int = 3650

    @property
    def cors_origin_list(self) -> list[str]:
        if self.cors_origins.strip() == "*":
            return ["*"]
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


settings = Settings()
