"""Compute file capabilities based on user's effective role.

Implements all 43 capability flags from the real Google Drive API v3.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from mock_gdrive.models.file import File
from mock_gdrive.models.permission import Permission
from mock_gdrive.models.user import User


# Role hierarchy (higher index = more permission)
_ROLE_RANK = {
    "reader": 0,
    "commenter": 1,
    "writer": 2,
    "fileOrganizer": 3,
    "organizer": 4,
    "owner": 5,
}


def get_effective_role(file: File, user: User, db: Session) -> str | None:
    """Get the highest role a user has on a file, considering inheritance.

    Walks up the parent chain to find inherited permissions.
    Returns the role string or None if the user has no access.
    """
    if file.owner_id == user.id:
        return "owner"

    best_role = None
    best_rank = -1

    # Check direct permissions on this file
    for perm in file.permissions:
        if _perm_matches_user(perm, user):
            rank = _ROLE_RANK.get(perm.role, -1)
            if rank > best_rank:
                best_role = perm.role
                best_rank = rank

    # Walk up parent chain for inherited permissions
    current = file
    visited = {file.id}
    while current.parent_id and current.parent_id not in visited:
        visited.add(current.parent_id)
        parent = db.query(File).filter(File.id == current.parent_id).first()
        if not parent:
            break
        for perm in parent.permissions:
            if _perm_matches_user(perm, user):
                rank = _ROLE_RANK.get(perm.role, -1)
                if rank > best_rank:
                    best_role = perm.role
                    best_rank = rank
        current = parent

    return best_role


def _perm_matches_user(perm: Permission, user: User) -> bool:
    """Check if a permission applies to a user."""
    if perm.type == "anyone":
        return True
    if perm.type == "user" and perm.email_address:
        return perm.email_address.lower() == user.email.lower()
    if perm.type == "domain" and perm.domain:
        return user.email.lower().endswith(f"@{perm.domain.lower()}")
    return False


def compute_capabilities(file: File, user: User, role: str | None) -> dict:
    """Compute all 42 capability flags for a file given the user's effective role."""
    is_owner = file.owner_id == user.id
    rank = _ROLE_RANK.get(role, -1) if role else -1

    can_read = rank >= 0
    can_comment = rank >= _ROLE_RANK["commenter"]
    can_write = rank >= _ROLE_RANK["writer"]
    can_organize = rank >= _ROLE_RANK["organizer"] or is_owner
    is_folder = file.is_folder

    return {
        "canAcceptOwnership": False,  # only for pending ownership transfers
        "canAddChildren": can_write and is_folder,
        "canAddFolderFromAnotherDrive": can_write and is_folder,
        "canAddMyDriveParent": can_write,
        "canChangeCopyRequiresWriterPermission": can_write or is_owner,
        "canChangeItemDownloadRestriction": is_owner,
        "canChangeSecurityUpdateEnabled": is_owner,
        "canChangeViewersCanCopyContent": can_write or is_owner,
        "canComment": can_comment,
        "canCopy": can_read and not is_folder,
        "canDelete": is_owner,
        "canDeleteChildren": is_owner and is_folder,
        "canDisableInheritedPermissions": is_owner,
        "canDownload": can_read,
        "canEdit": can_write,
        "canEnableInheritedPermissions": is_owner,
        "canListChildren": can_read and is_folder,
        "canModifyContent": can_write,
        "canModifyEditorContentRestriction": can_write,
        "canModifyLabels": can_write,
        "canModifyOwnerContentRestriction": is_owner,
        "canMoveChildrenOutOfDrive": is_owner and is_folder,
        "canMoveChildrenOutOfTeamDrive": is_owner and is_folder,
        "canMoveChildrenWithinDrive": can_write and is_folder,
        "canMoveChildrenWithinTeamDrive": can_write and is_folder,
        "canMoveItemIntoTeamDrive": can_write,
        "canMoveItemOutOfDrive": is_owner,
        "canMoveItemOutOfTeamDrive": is_owner,
        "canMoveItemWithinDrive": can_write,
        "canMoveItemWithinTeamDrive": can_write,
        "canMoveTeamDriveItem": can_write,
        "canReadDrive": can_read,
        "canReadLabels": can_read,
        "canReadRevisions": can_read,
        "canReadTeamDrive": can_read,
        "canRemoveChildren": can_write and is_folder,
        "canRemoveContentRestriction": is_owner,
        "canRemoveMyDriveParent": can_write,
        "canRename": can_write,
        "canShare": (can_write and file.writers_can_share) or is_owner,
        "canTrash": is_owner or can_organize,
        "canTrashChildren": (is_owner or can_organize) and is_folder,
        "canUntrash": is_owner or can_organize,
    }


def user_can_view(file: File, user: User, db: Session) -> bool:
    """Check if a user has any access to a file."""
    if file.owner_id == user.id:
        return True
    role = get_effective_role(file, user, db)
    return role is not None
