"""Task framework for mock-gdrive evaluation tasks."""

from .base import Task
from .registry import get_task, list_tasks, register_task

# Import task modules to trigger registration
from . import demo as _demo_tasks  # noqa: F401

__all__ = ["Task", "get_task", "list_tasks", "register_task"]
