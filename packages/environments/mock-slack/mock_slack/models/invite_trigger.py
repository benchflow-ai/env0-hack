"""InviteTrigger model.

When the bot sends a DM to `trigger_user_id`, the bot is automatically
added as a member of `channel_id`.  This simulates a human admin
responding to an access request by inviting the bot.

Configured per-task via SEED_INVITE_TRIGGERS in needles.py.
"""

from sqlalchemy import String, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class InviteTrigger(Base):
    __tablename__ = "invite_triggers"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), nullable=False)
    # Private channel the bot will be granted access to
    channel_id: Mapped[str] = mapped_column(String, nullable=False)
    # User the bot must DM to activate the trigger
    trigger_user_id: Mapped[str] = mapped_column(String, nullable=False)
