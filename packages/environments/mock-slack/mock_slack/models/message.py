"""Message model."""

from datetime import datetime

from sqlalchemy import JSON, String, Boolean, DateTime, Text, Integer, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


class Message(Base):
    __tablename__ = "slack_messages"

    id: Mapped[str] = mapped_column(String, primary_key=True)         # uuid hex
    channel_id: Mapped[str] = mapped_column(ForeignKey("channels.id"), nullable=False)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), nullable=False)
    user_id: Mapped[str] = mapped_column(ForeignKey("slack_users.id"), nullable=False)
    text: Mapped[str] = mapped_column(Text, default="")
    ts: Mapped[str] = mapped_column(String, nullable=False)            # Slack timestamp string
    thread_ts: Mapped[str | None] = mapped_column(String, nullable=True)  # parent ts if reply
    is_edited: Mapped[bool] = mapped_column(Boolean, default=False)
    edited_ts: Mapped[str | None] = mapped_column(String, nullable=True)
    reply_count: Mapped[int] = mapped_column(Integer, default=0)
    is_pinned: Mapped[bool] = mapped_column(Boolean, default=False)
    attachments: Mapped[list | None] = mapped_column(JSON, nullable=True)  # Slack-style attachment list
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    channel: Mapped["Channel"] = relationship(back_populates="messages")  # noqa: F821
    workspace: Mapped["Workspace"] = relationship(back_populates="messages")  # noqa: F821
    user: Mapped["SlackUser"] = relationship(back_populates="messages")  # noqa: F821
    reactions: Mapped[list["Reaction"]] = relationship(back_populates="message", cascade="all, delete-orphan")  # noqa: F821

    @property
    def reaction_groups(self) -> list[dict]:
        grouped: dict[str, set[str]] = {}
        for reaction in self.reactions:
            grouped.setdefault(reaction.emoji_name, set()).add(reaction.user_id)
        return [
            {
                "emoji_name": emoji_name,
                "count": len(user_ids),
                "users": sorted(user_ids),
            }
            for emoji_name, user_ids in grouped.items()
        ]
