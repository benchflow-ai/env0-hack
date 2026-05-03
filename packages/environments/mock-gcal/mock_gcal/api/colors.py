"""Calendar colors endpoint."""

from __future__ import annotations

from fastapi import APIRouter

from mock_gcal.color_palette import CALENDAR_COLORS, EVENT_COLORS

from .schemas import ColorsResponse

router = APIRouter()


@router.get("/colors", response_model=ColorsResponse, response_model_exclude_none=True)
def colors_get():
    return ColorsResponse(
        updated="2012-02-14T00:00:00.000Z",
        calendar=CALENDAR_COLORS,
        event=EVENT_COLORS,
    )
