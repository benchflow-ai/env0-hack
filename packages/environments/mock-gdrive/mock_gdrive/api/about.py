"""About API endpoint — Drive API v3."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from mock_gdrive.models import User, File
from .deps import get_db, resolve_user
from .schemas import AboutResource, UserInfo, StorageQuota
from .fields import parse_fields, filter_response

router = APIRouter()

# Real Drive API import/export format mappings
_IMPORT_FORMATS = {
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": [
        "application/vnd.google-apps.document"
    ],
    "text/plain": ["application/vnd.google-apps.document"],
    "text/html": ["application/vnd.google-apps.document"],
    "application/rtf": ["application/vnd.google-apps.document"],
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": [
        "application/vnd.google-apps.spreadsheet"
    ],
    "text/csv": ["application/vnd.google-apps.spreadsheet"],
    "text/tab-separated-values": ["application/vnd.google-apps.spreadsheet"],
    "application/vnd.openxmlformats-officedocument.presentationml.presentation": [
        "application/vnd.google-apps.presentation"
    ],
    "application/pdf": ["application/vnd.google-apps.document"],
    "image/jpeg": ["application/vnd.google-apps.document"],
    "image/png": ["application/vnd.google-apps.document"],
}

_EXPORT_FORMATS = {
    "application/vnd.google-apps.document": [
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/pdf",
        "text/plain",
        "text/html",
        "application/rtf",
        "application/epub+zip",
    ],
    "application/vnd.google-apps.spreadsheet": [
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "application/pdf",
        "text/csv",
        "text/tab-separated-values",
    ],
    "application/vnd.google-apps.presentation": [
        "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        "application/pdf",
        "text/plain",
    ],
    "application/vnd.google-apps.drawing": [
        "image/svg+xml",
        "image/png",
        "image/jpeg",
        "application/pdf",
    ],
}

_MAX_IMPORT_SIZES = {
    "application/vnd.google-apps.document": "10485760",
    "application/vnd.google-apps.spreadsheet": "104857600",
    "application/vnd.google-apps.presentation": "104857600",
    "application/vnd.google-apps.drawing": "2097152",
}

_FOLDER_COLOR_PALETTE = [
    "#ac725e", "#d06b64", "#f83a22", "#fa573c", "#ff7537", "#ffad46",
    "#42d692", "#16a765", "#7bd148", "#b3dc6c", "#fbe983", "#fad165",
    "#92e1c0", "#9fe1e7", "#9fc5e8", "#4986e7", "#9a9cff", "#b99aff",
    "#c2c2c2", "#cabdbf", "#cca6ac", "#f691b2", "#cd74e6", "#a47ae2",
]


@router.get("/drive/v3/about", tags=["about"])
def get_about(
    fields: str | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(resolve_user),
):
    # Compute storage usage
    from sqlalchemy import func
    usage = db.query(func.coalesce(func.sum(File.size), 0)).filter(
        File.owner_id == current_user.id,
    ).scalar()
    trash_usage = db.query(func.coalesce(func.sum(File.size), 0)).filter(
        File.owner_id == current_user.id,
        File.trashed == True,
    ).scalar()

    result = AboutResource(
        user=UserInfo(
            displayName=current_user.display_name,
            emailAddress=current_user.email,
            me=True,
            permissionId=current_user.id,
        ),
        storageQuota=StorageQuota(
            limit=str(current_user.storage_quota_limit),
            usage=str(usage),
            usageInDrive=str(usage - trash_usage),
            usageInDriveTrash=str(trash_usage),
        ),
        importFormats=_IMPORT_FORMATS,
        exportFormats=_EXPORT_FORMATS,
        maxImportSizes=_MAX_IMPORT_SIZES,
        folderColorPalette=_FOLDER_COLOR_PALETTE,
    ).model_dump(exclude_none=True)

    if fields:
        spec = parse_fields(fields)
        if spec:
            result = filter_response(result, spec)
    return result
