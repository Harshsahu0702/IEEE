import os
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # App Settings
    ENVIRONMENT: str = "development"
    DEBUG: bool = True
    PROJECT_NAME: str = "OmniSense AI"
    API_V1_STR: str = "/api"

    # Database
    DATABASE_URL: str = "sqlite:///./omnisense.db"

    # Security & Auth
    SECRET_KEY: str = "omnisense-super-secret-jwt-key-change-in-production-2026"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440  # 24 hours

    # Gemini LLM API
    GEMINI_API_KEY: str = ""

    # MQTT Settings
    MQTT_BROKER_HOST: str = "localhost"
    MQTT_BROKER_PORT: int = 1883
    MQTT_KEEPALIVE: int = 60
    MQTT_CLIENT_ID: str = "omnisense_backend_gateway"
    MQTT_USERNAME: str = "omnisense_user"
    MQTT_PASSWORD: str = "omnisense_pass"
    MQTT_TOPIC_TELEMETRY: str = "omnisense/devices/+/telemetry"
    MQTT_TOPIC_STATUS: str = "omnisense/devices/+/status"
    DEVICE_OFFLINE_TIMEOUT_SECONDS: int = 30

    # Vision & Camera
    CAMERA_INDEX: int = 0
    FRAME_WIDTH: int = 640
    FRAME_HEIGHT: int = 480
    TARGET_FPS: int = 15
    YOLO_MODEL_NAME: str = "yolov8n.pt"

    # Evidence Directory & Data Retention
    EVIDENCE_DIR: str = "./evidence"
    DATA_RETENTION_DAYS: int = 30


    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    def setup_directories(self):
        """Ensure necessary runtime directories exist."""
        evidence_path = Path(self.EVIDENCE_DIR)
        evidence_path.mkdir(parents=True, exist_ok=True)


settings = Settings()
settings.setup_directories()
