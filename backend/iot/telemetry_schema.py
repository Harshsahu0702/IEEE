from datetime import datetime
from typing import Optional, Any, Union
from pydantic import BaseModel, Field, field_validator


class TelemetryPayload(BaseModel):
    """
    Pydantic schema for IoT device telemetry.
    Strict Rule: Never trust device input. Drop and log malformed payloads.
    """
    device_id: str = Field(..., min_length=1, max_length=64, pattern=r"^[a-zA-Z0-9_\-]+$")
    temperature: float = Field(..., ge=-50.0, le=120.0, description="Temperature in Celsius")
    humidity: float = Field(..., ge=0.0, le=100.0, description="Relative humidity percentage")
    gas_level: float = Field(..., ge=0.0, le=10000.0, description="MQ-2 Gas sensor reading (ppm)")
    motion: bool = Field(default=False, description="PIR motion detected")
    timestamp: Optional[Union[float, int, str, datetime]] = Field(default=None)

    @field_validator("timestamp", mode="before")
    def parse_timestamp(cls, v):
        if v is None:
            return datetime.utcnow()
        if isinstance(v, (int, float)):
            try:
                return datetime.utcfromtimestamp(v)
            except Exception:
                return datetime.utcnow()
        if isinstance(v, str):
            try:
                return datetime.fromisoformat(v.replace("Z", "+00:00"))
            except Exception:
                return datetime.utcnow()
        if isinstance(v, datetime):
            return v
        return datetime.utcnow()


class DeviceStatusPayload(BaseModel):
    """Payload for omnisense/devices/{device_id}/status topic."""
    device_id: str = Field(..., min_length=1, max_length=64, pattern=r"^[a-zA-Z0-9_\-]+$")
    status: str = Field(..., pattern=r"^(online|offline|booting|error)$")
    ip_address: Optional[str] = None
    firmware_version: Optional[str] = None
    timestamp: Optional[Any] = None
