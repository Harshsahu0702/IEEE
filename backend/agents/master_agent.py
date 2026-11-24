import logging
from typing import Dict, Any, Optional
from sqlalchemy.orm import Session

from backend.database.connection import SessionLocal
from backend.database import crud
from backend.agents.schemas import MonitoringPlan, PlanExplanation, CommandResponse
from backend.agents.safety import SafetyPolicy
from backend.agents.fallback_parser import fallback_parser
from backend.agents.llm_parser import llm_parser
from backend.agents.tools import tool_registry

logger = logging.getLogger(__name__)


class MasterAgent:
    """
    OmniSense Master Agent.
    Pipeline:
    1. Safety & Guardrail Policy evaluation (Block facial recognition & prompt injections).
    2. Intent parsing (Gemini LLM API with fallback to deterministic keyword parser).
    3. Strict Pydantic validation (reject unknown modules/out-of-range rules).
    4. Plan creation in SQLite with status 'pending_approval' (Approval gate).
    5. Immutable audit logging in audit_logs table.
    """

    def process_command(
        self,
        command: str,
        user_id: Optional[int] = None,
        db: Optional[Session] = None
    ) -> CommandResponse:
        close_db = False
        if db is None:
            db = SessionLocal()
            close_db = True

        try:
            # 1. Safety Policy Check
            decision, safety_reason = SafetyPolicy.evaluate(command)

            if decision == "blocked":
                logger.warning(f"Command BLOCKED by SafetyPolicy: '{command}' - Reason: {safety_reason}")
                # Record audit log
                crud.create_audit_log(
                    db=db,
                    command=command,
                    decision="blocked",
                    user_id=user_id,
                    safety_notes=safety_reason
                )
                return CommandResponse(
                    status="blocked",
                    explanation=PlanExplanation(
                        what_i_understood="Command violates OmniSense AI safety, privacy, or ethical policies.",
                        modules_chosen=[],
                        why="Safety policy violation.",
                        confidence=1.0,
                        safety_decision="blocked",
                        safety_reason=safety_reason
                    )
                )

            # 2. Parse command via LLM (or Fallback Parser)
            parsed_data: Optional[Dict[str, Any]] = None
            if llm_parser.is_available():
                parsed_data = llm_parser.parse(command)

            if not parsed_data:
                parsed_data = fallback_parser.parse(command)

            # Check if domain was identified as unsupported
            if parsed_data.get("domain") == "unsupported":
                why_msg = parsed_data.get("why", "Requested capability is unsupported.")
                crud.create_audit_log(
                    db=db,
                    command=command,
                    decision="unsupported",
                    user_id=user_id,
                    safety_notes=why_msg
                )
                return CommandResponse(
                    status="unsupported",
                    explanation=PlanExplanation(
                        what_i_understood=parsed_data.get("what_i_understood", "Unsupported capability"),
                        modules_chosen=[],
                        why=why_msg,
                        confidence=parsed_data.get("confidence", 0.3),
                        safety_decision=decision,
                        safety_reason=safety_reason
                    )
                )

            # 3. Handle 'get_status' intent directly using registered tools
            if parsed_data.get("intent") == "get_status":
                status_info = tool_registry.get_status()
                crud.create_audit_log(
                    db=db,
                    command=command,
                    decision="executed_status",
                    user_id=user_id,
                    details=status_info
                )
                return CommandResponse(
                    status="executed",
                    plan={"intent": "get_status", "status_data": status_info},
                    explanation=PlanExplanation(
                        what_i_understood="System health and active monitoring status requested.",
                        modules_chosen=[],
                        why="Operator requested diagnostics.",
                        confidence=0.98,
                        safety_decision=decision
                    )
                )

            # 4. Validate with strict Pydantic schema
            try:
                validated_plan = MonitoringPlan(
                    intent=parsed_data.get("intent", "start_monitoring"),
                    domain=parsed_data.get("domain", "vision"),
                    modules=parsed_data.get("modules", []),
                    source=parsed_data.get("source", "webcam_0"),
                    rules=parsed_data.get("rules", {}),
                    duration_minutes=parsed_data.get("duration_minutes"),
                    notify=parsed_data.get("notify", "dashboard")
                )
            except Exception as ve:
                logger.error(f"Plan validation failed: {ve}")
                return CommandResponse(
                    status="unsupported",
                    explanation=PlanExplanation(
                        what_i_understood=f"Validation error: {ve}",
                        modules_chosen=[],
                        why="Plan parameters outside valid boundaries.",
                        confidence=0.2,
                        safety_decision="rejected"
                    )
                )

            # 5. Create AgentPlan in SQLite with status 'pending_approval'
            plan_record = crud.create_plan(
                db=db,
                natural_command=command,
                intent=validated_plan.intent,
                domain=validated_plan.domain,
                modules=validated_plan.modules,
                source=validated_plan.source,
                rules={**validated_plan.rules, "duration_minutes": validated_plan.duration_minutes},
                raw_response=parsed_data.get("what_i_understood", ""),
                user_id=user_id
            )

            # 6. Record Audit Log
            crud.create_audit_log(
                db=db,
                command=command,
                decision=decision,
                user_id=user_id,
                plan_id=plan_record.id,
                safety_notes=safety_reason,
                details=validated_plan.model_dump()
            )

            explanation = PlanExplanation(
                what_i_understood=parsed_data.get("what_i_understood", "Monitoring task generated."),
                modules_chosen=validated_plan.modules,
                why=parsed_data.get("why", "Matched input command requirements."),
                confidence=float(parsed_data.get("confidence", 0.90)),
                safety_decision=decision,
                safety_reason=safety_reason
            )

            plan_dict = {
                "id": plan_record.id,
                "natural_command": plan_record.natural_command,
                "intent": plan_record.intent,
                "domain": plan_record.domain,
                "modules": plan_record.modules,
                "source": plan_record.source,
                "rules": plan_record.rules,
                "status": plan_record.status,
                "created_at": plan_record.created_at.isoformat() if plan_record.created_at else None
            }

            return CommandResponse(
                plan_id=plan_record.id,
                id=plan_record.id,
                plan=plan_dict,
                status="pending_approval",
                explanation=explanation
            )
        finally:
            if close_db:
                db.close()


master_agent = MasterAgent()
