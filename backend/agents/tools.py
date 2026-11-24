import logging
from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session

from backend.database.connection import SessionLocal
from backend.database import crud
from backend.monitoring.registry import list_plugins
from backend.monitoring.runner import task_manager

logger = logging.getLogger(__name__)


class RegisteredTools:
    """
    Approved tool registry that the Master Agent is permitted to execute.
    Strict Rule: The agent may ONLY call registered tools in this class.
    It MUST NEVER execute generated code, eval(), or run shell commands.
    """

    @staticmethod
    def list_modules() -> List[Dict[str, Any]]:
        """Returns all discovered monitoring plugins from registry."""
        plugins = list_plugins()
        return [
            {
                "name": p.name,
                "display_name": p.display_name,
                "domain": p.domain,
                "description": p.description,
                "default_config": p.default_config
            }
            for p in plugins
        ]

    @staticmethod
    def list_devices() -> List[Dict[str, Any]]:
        """Returns all registered physical or synthetic devices."""
        db: Session = SessionLocal()
        try:
            devices = crud.get_devices(db)
            return [
                {
                    "device_id": d.device_id,
                    "name": d.name,
                    "device_type": d.device_type,
                    "status": d.status,
                    "approval_status": getattr(d, "approval_status", "approved")
                }
                for d in devices
            ]
        finally:
            db.close()

    @staticmethod
    def get_status() -> Dict[str, Any]:
        """Returns current operational status of the OmniSense monitoring engine."""
        db: Session = SessionLocal()
        try:
            tasks = crud.get_tasks(db, limit=10)
            active_tasks = [t for t in tasks if t.status == "running"]
            devices = crud.get_devices(db)
            online_devices = [d for d in devices if d.status == "online"]
            recent_events = crud.get_events(db, limit=5)

            return {
                "active_tasks_count": len(active_tasks),
                "active_tasks": [{"id": t.id, "plugin": t.plugin_name, "source": t.target_source} for t in active_tasks],
                "online_devices_count": len(online_devices),
                "total_devices": len(devices),
                "pending_events_count": len([e for e in recent_events if e.status == "pending_review"]),
                "system_health": "operational"
            }
        finally:
            db.close()

    @staticmethod
    def start_task(task_id: int) -> Dict[str, Any]:
        """Starts a validated monitoring task."""
        db: Session = SessionLocal()
        try:
            task = crud.get_task(db, task_id)
            if not task:
                return {"success": False, "error": f"Task #{task_id} not found"}

            crud.update_task_status(db, task_id, "running")
            user_goal = (task.config or {}).get("user_goal", "Monitor scene")
            from backend.monitoring import universal_runner
            universal_runner.start_universal_task(
                task_id=task.id,
                user_goal=user_goal,
                config=task.config or {},
            )
            return {"success": True, "task_id": task_id, "status": "running"}
        finally:
            db.close()

    @staticmethod
    def stop_task(task_id: int) -> Dict[str, Any]:
        """Stops an active monitoring task cleanly."""
        db: Session = SessionLocal()
        try:
            task = crud.get_task(db, task_id)
            if not task:
                return {"success": False, "error": f"Task #{task_id} not found"}

            from backend.monitoring import universal_runner
            universal_runner.stop_universal_task(task_id)
            crud.update_task_status(db, task_id, "stopped")
            return {"success": True, "task_id": task_id, "status": "stopped"}
        finally:
            db.close()


tool_registry = RegisteredTools()
