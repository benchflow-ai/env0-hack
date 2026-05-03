"""Reminders API routes — reminders.* methods."""

from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from mock_slack.models import Reminder
from .deps import get_db, resolve_workspace_id
from .schemas import (
    ReminderSchema,
    ReminderListResponse,
)

router = APIRouter()


def _reminder_to_schema(r: Reminder) -> ReminderSchema:
    return ReminderSchema(
        id=r.id,
        creator=r.creator_id,
        user=r.user_id,
        text=r.text,
        recurring=False,
        time=int(r.remind_at.timestamp()) if r.remind_at else 0,
        complete_ts=int(r.complete_ts) if r.complete_ts else 0,
    )


@router.get("/reminders.list")
def reminders_list(
    db: Session = Depends(get_db),
    workspace_id: str = Depends(resolve_workspace_id),
):
    reminders = db.query(Reminder).filter(Reminder.workspace_id == workspace_id).all()
    return ReminderListResponse(
        ok=True, reminders=[_reminder_to_schema(r) for r in reminders]
    )
