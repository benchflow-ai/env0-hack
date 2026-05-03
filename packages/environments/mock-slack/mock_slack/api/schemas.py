"""Pydantic schemas mirroring Slack API response format."""

from __future__ import annotations

import time
from typing import Any
from pydantic import BaseModel, ConfigDict, Field, model_serializer


class SlackResponse(BaseModel):
    ok: bool = True


class SlackError(BaseModel):
    ok: bool = False
    error: str


_WARNING = "missing_charset"
_RESPONSE_METADATA = {"warnings": ["missing_charset"]}


class UserProfileSchema(BaseModel):
    real_name: str = ""
    real_name_normalized: str = ""
    display_name: str = ""
    display_name_normalized: str = ""
    first_name: str = ""
    last_name: str = ""
    email: str = ""
    title: str = ""
    phone: str = ""
    skype: str = ""
    status_text: str = ""
    status_text_canonical: str = ""
    status_emoji: str = ""
    status_emoji_display_info: list = Field(default_factory=list)
    status_expiration: int = 0
    tz: str = "America/Los_Angeles"
    team: str = ""
    image_24: str = ""
    image_32: str = ""
    image_48: str = ""
    image_72: str = ""


class UserSchema(BaseModel):
    id: str
    name: str
    real_name: str = ""
    deleted: bool = False
    is_admin: bool = False
    is_bot: bool = False
    is_app_user: bool = False
    is_email_confirmed: bool = True
    is_owner: bool = False
    is_primary_owner: bool = False
    is_restricted: bool = False
    is_ultra_restricted: bool = False
    updated: int = 0
    team_id: str = ""
    color: str = "674b1b"
    tz: str = "America/Los_Angeles"
    tz_label: str = "Pacific Daylight Time"
    tz_offset: int = -25200
    who_can_share_contact_card: str = "EVERYONE"
    enterprise_user: dict | None = None
    profile: UserProfileSchema = Field(default_factory=UserProfileSchema)


class UsersListResponse(SlackResponse):
    members: list[UserSchema] = Field(default_factory=list)
    cache_ts: int = Field(default_factory=lambda: int(time.time()))
    response_metadata: dict = Field(default_factory=lambda: {"next_cursor": ""})


class UserInfoResponse(SlackResponse):
    user: UserSchema | None = None


class WorkspaceSchema(BaseModel):
    id: str
    name: str
    domain: str = ""
    url: str = ""
    email_domain: str = ""
    avatar_base_url: str = "https://ca.slack-edge.com/"
    is_verified: bool = False
    discoverable: str = "closed"
    enterprise_id: str = ""
    enterprise_name: str = ""
    enterprise_domain: str = ""
    lob_sales_home_enabled: bool = False
    is_sfdc_auto_slack: bool = False
    icon: dict = Field(default_factory=lambda: {"image_default": True})


class TeamInfoResponse(SlackResponse):
    team: WorkspaceSchema | None = None


class ChannelTopicSchema(BaseModel):
    value: str = ""
    creator: str = ""
    last_set: int = 0


class ChannelPurposeSchema(BaseModel):
    value: str = ""
    creator: str = ""
    last_set: int = 0


class ChannelSchema(BaseModel):
    id: str
    name: str
    is_channel: bool = True
    is_group: bool = False
    is_im: bool = False
    is_mpim: bool = False
    is_private: bool = False
    is_archived: bool = False
    is_general: bool = False
    is_shared: bool = False
    is_org_shared: bool = False
    is_ext_shared: bool = False
    is_pending_ext_shared: bool = False
    is_member: bool = True
    is_moved: int = 0
    creator: str = ""
    name_normalized: str = ""
    topic: ChannelTopicSchema = Field(default_factory=ChannelTopicSchema)
    purpose: ChannelPurposeSchema = Field(default_factory=ChannelPurposeSchema)
    created: int = 0
    updated: int = 0
    unlinked: int = 0
    context_team_id: str = ""
    num_members: int | None = None
    priority: int | None = None
    parent_conversation: None = None
    pending_shared: list = Field(default_factory=list)
    pending_connected_team_ids: list = Field(default_factory=list)
    shared_team_ids: list[str] = Field(default_factory=list)
    internal_team_ids: list[str] = Field(default_factory=list)
    previous_names: list[str] = Field(default_factory=list)
    last_read: str | None = None
    properties: dict = Field(default_factory=lambda: {
        "tabs": [
            {"type": "bookmarks", "label": "", "id": "bookmarks"},
            {"type": "files", "label": "", "id": "files"},
        ],
        "tabz": [{"type": "bookmarks"}, {"type": "files"}],
    })


class IMChannelSchema(BaseModel):
    """Schema for IM (direct message) channels — different shape from public/private."""
    id: str
    created: int = 0
    is_im: bool = True
    is_org_shared: bool = False
    is_archived: bool = False
    is_shared: bool = False
    context_team_id: str = ""
    updated: int = 0
    user: str = ""
    is_user_deleted: bool = False
    priority: int = 0


class ConversationsListResponse(SlackResponse):
    channels: list[Any] = Field(default_factory=list)
    response_metadata: dict = Field(default_factory=lambda: {"next_cursor": ""})


class ConversationInfoResponse(SlackResponse):
    channel: Any | None = None


class ConversationMembersResponse(SlackResponse):
    members: list[str] = Field(default_factory=list)
    response_metadata: dict = Field(default_factory=lambda: {"next_cursor": ""})


class ReactionItemSchema(BaseModel):
    name: str
    count: int = 1
    users: list[str] = Field(default_factory=list)


class EditedSchema(BaseModel):
    user: str = ""
    ts: str = ""


class MessageSchema(BaseModel):
    type: str = "message"
    subtype: str | None = None
    user: str = ""
    text: str = ""
    ts: str = ""
    team: str | None = None
    thread_ts: str | None = None
    reply_count: int | None = None
    reactions: list[ReactionItemSchema] | None = None
    edited: EditedSchema | None = None
    blocks: list[dict] | None = None
    attachments: list[dict] | None = None
    bot_id: str | None = None
    app_id: str | None = None
    bot_profile: dict | None = None
    # Thread parent fields (present on thread root messages in conversations.replies)
    is_locked: bool | None = None
    subscribed: bool | None = None
    latest_reply: str | None = None
    reply_users_count: int | None = None
    reply_users: list[str] | None = None
    # Reply fields (present on reply messages in conversations.replies)
    parent_user_id: str | None = None

    @model_serializer(mode="wrap")
    def _exclude_none(self, handler):
        d = handler(self)
        return {k: v for k, v in d.items() if v is not None}


class MessagesListResponse(SlackResponse):
    messages: list[MessageSchema] = Field(default_factory=list)
    has_more: bool = False
    pin_count: int = 0
    channel_actions_ts: None = None
    channel_actions_count: int = 0
    response_metadata: dict = Field(default_factory=lambda: {"next_cursor": ""})


class PostMessageResponse(SlackResponse):
    channel: str = ""
    ts: str = ""
    message: MessageSchema | None = None
    warning: str = _WARNING
    response_metadata: dict = Field(default_factory=lambda: {"warnings": ["missing_charset"]})


class ChatUpdateResponse(SlackResponse):
    channel: str = ""
    ts: str = ""
    text: str = ""
    message: dict | None = None
    warning: str = _WARNING
    response_metadata: dict = Field(default_factory=lambda: {"warnings": ["missing_charset"]})


class PermalinkResponse(SlackResponse):
    channel: str = ""
    permalink: str = ""


class ReactionSchema(BaseModel):
    name: str
    count: int = 0
    users: list[str] = Field(default_factory=list)


class ReactionsGetResponse(SlackResponse):
    type: str = "message"
    channel: str = ""
    message: MessageSchema | None = None


class FileSchema(BaseModel):
    id: str
    created: int = 0
    timestamp: int = 0
    name: str = ""
    title: str = ""
    mimetype: str = "text/plain"
    filetype: str = "text"
    pretty_type: str = ""
    user: str = ""
    user_team: str = ""
    editable: bool = False
    size: int = 0
    mode: str = "hosted"
    is_external: bool = False
    external_type: str = ""
    is_public: bool = False
    public_url_shared: bool = False
    display_as_bot: bool = False
    username: str = ""
    url_private: str = ""
    url_private_download: str = ""
    media_display_type: str = "unknown"
    permalink: str = ""
    permalink_public: str = ""
    comments_count: int = 0
    is_starred: bool = False
    shares: dict = Field(default_factory=dict)
    channels: list[str] = Field(default_factory=list)
    groups: list[str] = Field(default_factory=list)
    ims: list[str] = Field(default_factory=list)
    has_more_shares: bool = False
    has_rich_preview: bool = False
    file_access: str = "visible"
    content: str | None = None


class FilesListResponse(SlackResponse):
    files: list[FileSchema] = Field(default_factory=list)
    paging: dict = Field(
        default_factory=lambda: {"count": 100, "total": 0, "page": 1, "pages": 1}
    )


class FileInfoResponse(SlackResponse):
    file: FileSchema | None = None
    comments: list = Field(default_factory=list)
    response_metadata: dict = Field(default_factory=lambda: {"next_cursor": ""})


class FileUploadResponse(SlackResponse):
    file: FileSchema | None = None


class PinItemSchema(BaseModel):
    type: str = "message"
    channel: str = ""
    message: MessageSchema | None = None
    created: int = 0
    created_by: str = ""


class PinsListResponse(SlackResponse):
    items: list[PinItemSchema] = Field(default_factory=list)


class ReminderSchema(BaseModel):
    id: str
    creator: str = ""
    user: str = ""
    text: str = ""
    recurring: bool = False
    time: int = 0
    complete_ts: int | None = None


class ReminderListResponse(SlackResponse):
    reminders: list[ReminderSchema] = Field(default_factory=list)


class AuthTestResponse(SlackResponse):
    url: str = ""
    team: str = ""
    user: str = ""
    team_id: str = ""
    user_id: str = ""
    bot_id: str | None = None
    enterprise_id: str = ""
    is_enterprise_install: bool = False


class SearchMatchSchema(BaseModel):
    iid: str = ""
    type: str = "message"
    text: str = ""
    ts: str = ""
    team: str = ""
    score: float = 1.0
    db_message: dict = Field(default_factory=dict)
    channel: dict = Field(default_factory=dict)
    user: str = ""
    username: str = ""
    permalink: str = ""
    blocks: list[dict] = Field(default_factory=list)


class SearchMessagesResponse(SlackResponse):
    query: str = ""
    messages: dict = Field(
        default_factory=lambda: {
            "total": 0,
            "pagination": {},
            "paging": {},
            "matches": [],
        }
    )


# ---------------------------------------------------------------------------
# Request bodies
# ---------------------------------------------------------------------------


class ConversationsCreateRequest(BaseModel):
    name: str
    is_private: bool = False


class ConversationsRenameRequest(BaseModel):
    channel: str
    name: str


class ConversationsInviteRequest(BaseModel):
    channel: str
    users: str  # comma-separated user IDs


class ConversationsKickRequest(BaseModel):
    channel: str
    user: str


class ConversationsPurposeRequest(BaseModel):
    channel: str
    purpose: str


class ConversationsTopicRequest(BaseModel):
    channel: str
    topic: str


class ConversationsOpenRequest(BaseModel):
    channel: str | None = None
    users: str | None = None  # comma-separated user IDs


class ChatPostMessageRequest(BaseModel):
    channel: str
    text: str = ""
    thread_ts: str | None = None
    blocks: list[dict] | None = None
    attachments: list[dict] | None = None
    username: str | None = None
    icon_emoji: str | None = None
    icon_url: str | None = None


class ChatPostEphemeralRequest(BaseModel):
    channel: str
    user: str
    text: str = ""
    thread_ts: str | None = None


class ChatUpdateRequest(BaseModel):
    channel: str
    ts: str
    text: str


class ChatDeleteRequest(BaseModel):
    channel: str
    ts: str


class ChatScheduleMessageRequest(BaseModel):
    channel: str
    text: str
    post_at: int  # Unix timestamp
    thread_ts: str | None = None


class ChatDeleteScheduledMessageRequest(BaseModel):
    channel: str
    scheduled_message_id: str


class ReactionsAddRequest(BaseModel):
    channel: str
    timestamp: str
    name: str


class ReactionsRemoveRequest(BaseModel):
    channel: str
    timestamp: str
    name: str


class FileUploadRequest(BaseModel):
    channels: str | None = None
    content: str = ""
    filename: str = "file.txt"
    filetype: str = "text"
    title: str = ""


class FileDeleteRequest(BaseModel):
    file: str


class PinsAddRequest(BaseModel):
    channel: str
    timestamp: str


class PinsRemoveRequest(BaseModel):
    channel: str
    timestamp: str
