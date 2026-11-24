from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field, field_validator
from backend.monitoring.registry import list_plugins


class MonitoringPlan(BaseModel):
    """
    Strict validated monitoring plan.
    Enforces that modules must exist in the plugin registry,
    sources must be registered, and rules must be in safe ranges.
    """
    intent: str = Field(..., pattern=r"^(start_monitoring|stop_monitoring|switch_monitoring|get_status)$")
    domain: str = Field(..., pattern=r"^(vision|iot|multimodal|system)$")
    modules: List[str] = Field(default_factory=list)
    source: str = Field(default="webcam_0")
    rules: Dict[str, Any] = Field(default_factory=dict)
    duration_minutes: Optional[int] = Field(default=None, ge=1, le=1440)
    notify: Optional[str] = Field(default="dashboard")

    @field_validator("modules")
    def validate_modules_against_registry(cls, v):
        if not v:
            return v
        available = [p.name for p in list_plugins()]
        for m in v:
            if m not in available:
                raise ValueError(
                    f"Module '{m}' does not exist in plugin registry. "
                    f"Available modules: {available}"
                )
        return v

    @field_validator("rules")
    def validate_rules_range(cls, v):
        # Validate person threshold if present
        if "person_threshold" in v:
            val = int(v["person_threshold"])
            if val < 1 or val > 500:
                raise ValueError(f"person_threshold must be between 1 and 500 (got {val})")
            v["person_threshold"] = val

        # Validate temperature threshold if present
        if "temp_threshold" in v:
            val = float(v["temp_threshold"])
            if val < -40.0 or val > 120.0:
                raise ValueError(f"temp_threshold must be between -40°C and 120°C (got {val})")
            v["temp_threshold"] = val

        # Validate gas threshold if present
        if "gas_threshold" in v:
            val = float(v["gas_threshold"])
            if val < 0.0 or val > 10000.0:
                raise ValueError(f"gas_threshold must be between 0 and 10000 ppm (got {val})")
            v["gas_threshold"] = val

        # Validate cooldown
        if "cooldown_seconds" in v:
            val = float(v["cooldown_seconds"])
            if val < 1.0 or val > 3600.0:
                raise ValueError(f"cooldown_seconds must be between 1.0 and 3600.0 (got {val})")
            v["cooldown_seconds"] = val

        return v


class PlanExplanation(BaseModel):
    """Detailed natural-language breakdown of the agent's reasoning."""
    what_i_understood: str
    modules_chosen: List[str]
    why: str
    confidence: float = Field(..., ge=0.0, le=1.0)
    safety_decision: str = "approved_for_review"  # "approved_for_review", "blocked", "requires_human_review"
    safety_reason: Optional[str] = None


class CommandResponse(BaseModel):
    """Unified API response for POST /agent/command."""
    plan_id: Optional[int] = None
    id: Optional[int] = None  # Alias for backward compatibility
    plan: Optional[Dict[str, Any]] = None
    status: str  # "pending_approval", "blocked", "unsupported", "executed"
    explanation: PlanExplanation
    raw_response: Optional[str] = None
