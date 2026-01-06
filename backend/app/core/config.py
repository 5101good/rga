"""Application configuration using Pydantic Settings."""

from functools import lru_cache
from typing import List

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # Supabase
    supabase_url: str = ""
    supabase_key: str = ""
    supabase_service_key: str = ""

    # AgentBay
    agentbay_api_key: str = ""
    agentbay_image_id: str = "mobile-use-android-12"
    # ADB key configuration
    # Production: NAS mount point (/mnt/rga)
    # Debug: default location (~/.android)
    adb_key_dir: str = ""  # If empty, auto-detect based on debug mode

    # GLM Agent Model API (default/legacy config)
    model_base_url: str = "http://localhost:8000/v1"
    model_name: str = "autoglm-phone-9b"
    model_api_key: str = "EMPTY"

    # GLM Agent specific config (uses default if not set)
    glm_model_base_url: str = ""
    glm_model_name: str = ""
    glm_model_api_key: str = ""

    # GELab Agent Model API
    gelab_model_base_url: str = ""
    gelab_model_name: str = "gelab-zero-4b-preview"
    gelab_model_api_key: str = ""

    @property
    def glm_config(self) -> dict:
        """Get GLM Agent model configuration."""
        return {
            "base_url": self.glm_model_base_url or self.model_base_url,
            "model_name": self.glm_model_name or self.model_name,
            "api_key": self.glm_model_api_key or self.model_api_key,
        }

    @property
    def gelab_config(self) -> dict:
        """Get GELab Agent model configuration."""
        return {
            "base_url": self.gelab_model_base_url or self.model_base_url,
            "model_name": self.gelab_model_name or self.model_name,
            "api_key": self.gelab_model_api_key or self.model_api_key,
        }

    # Session limits
    max_sessions_per_day: int = 30
    max_active_sessions: int = 10

    # Server
    host: str = "0.0.0.0"
    port: int = 8080
    debug: bool = False

    # Feature flags
    # When enabled, use AgentBay SDK mobile primitives (tap/swipe/send_key/screenshot/start_app)
    # to replace local adb subprocess-based primitives. (get_current_app remains adb-based.)
    use_agentbay_mobile: bool = True

    # When enabled, fetch current foreground app via ADB and include it in the prompt.
    # To remove ADB dependency in the agent loop, set PHONE_AGENT_INCLUDE_CURRENT_APP=false.
    phone_agent_include_current_app: bool = False

    # Logging
    log_level: str = "INFO"  # DEBUG, INFO, WARNING, ERROR, CRITICAL
    log_to_file: bool = False  # Whether to save logs to file
    log_file_path: str = "logs/app.log"  # Log file path
    log_max_bytes: int = 10485760  # Max file size before rotation (10MB)
    log_backup_count: int = 5  # Number of backup files to keep

    # CORS - add your LAN IP here
    cors_origins: str = "http://localhost:5173,http://localhost:3000,http://30.221.210.223:5173"

    @property
    def cors_origins_list(self) -> List[str]:
        """Parse CORS origins from comma-separated string."""
        return [origin.strip() for origin in self.cors_origins.split(",")]


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()


settings = get_settings()

