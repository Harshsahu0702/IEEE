import time
import threading
import logging
from typing import Dict
from backend.database.connection import SessionLocal
from backend.database import crud
from backend.monitoring.runner import task_manager

logger = logging.getLogger(__name__)


class TaskDurationScheduler:
    """
    Timer scheduler to automatically terminate monitoring tasks
    after duration_minutes has elapsed.
    """
    _instance = None

    def __init__(self):
        self._timers: Dict[int, threading.Timer] = {}

    @classmethod
    def get_instance(cls) -> "TaskDurationScheduler":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def schedule_auto_stop(self, task_id: int, duration_minutes: int):
        """Schedules auto-stop after duration_minutes."""
        duration_seconds = duration_minutes * 60
        logger.info(f"Scheduling auto-stop for task #{task_id} in {duration_minutes} minutes ({duration_seconds}s).")

        def _stop():
            logger.info(f"Duration expired for task #{task_id}. Stopping task automatically...")
            task_manager.stop_task(task_id)
            db = SessionLocal()
            try:
                crud.update_task_status(db, task_id, "stopped", error_message=f"Stopped automatically after {duration_minutes}m duration.")
            finally:
                db.close()
            self._timers.pop(task_id, None)

        timer = threading.Timer(duration_seconds, _stop)
        timer.daemon = True
        timer.start()
        self._timers[task_id] = timer

    def cancel_timer(self, task_id: int):
        """Cancels any pending auto-stop timer for a task."""
        timer = self._timers.pop(task_id, None)
        if timer:
            timer.cancel()
            logger.info(f"Cancelled duration timer for task #{task_id}.")


duration_scheduler = TaskDurationScheduler.get_instance()
