"""Shared Google Calendar color palette helpers."""

from __future__ import annotations


DEFAULT_CALENDAR_COLOR_ID = "14"
ALLOWED_CALENDAR_COLOR_IDS: tuple[str, ...] = ("14", "9", "6", "16", "10")

_UNIFIED_SWATCHES: dict[str, dict[str, str]] = {
    "14": {"background": "#039be5", "foreground": "#ffffff"},
    "9": {"background": "#33b679", "foreground": "#ffffff"},
    "6": {"background": "#f29900", "foreground": "#ffffff"},
    "16": {"background": "#4285f4", "foreground": "#ffffff"},
    "10": {"background": "#7cb342", "foreground": "#ffffff"},
}


def _cycle_aliases(limit: int, canonical_ids: tuple[str, ...]) -> dict[str, str]:
    aliases = {
        str(idx): canonical_ids[(idx - 1) % len(canonical_ids)]
        for idx in range(1, limit + 1)
    }
    for color_id in canonical_ids:
        aliases[color_id] = color_id
    return aliases


_CALENDAR_ALIASES = _cycle_aliases(24, ALLOWED_CALENDAR_COLOR_IDS)
_EVENT_ALIASES = _cycle_aliases(11, ALLOWED_CALENDAR_COLOR_IDS)


def _build_palette(limit: int, aliases: dict[str, str]) -> dict[str, dict[str, str]]:
    return {
        str(idx): dict(_UNIFIED_SWATCHES[aliases[str(idx)]])
        for idx in range(1, limit + 1)
    }


CALENDAR_COLORS: dict[str, dict[str, str]] = _build_palette(24, _CALENDAR_ALIASES)
EVENT_COLORS: dict[str, dict[str, str]] = _build_palette(11, _EVENT_ALIASES)


def canonical_calendar_color_id(color_id: str | None) -> str:
    key = str(color_id or "").strip()
    return _CALENDAR_ALIASES.get(key, DEFAULT_CALENDAR_COLOR_ID)


def _color_pair(
    palette: dict[str, dict[str, str]],
    color_id: str | None,
    *,
    fallback_id: str,
) -> tuple[str, str]:
    color = palette.get(str(color_id or ""), palette[fallback_id])
    return color["background"], color["foreground"]


def calendar_color_pair(color_id: str | None) -> tuple[str, str]:
    return _color_pair(CALENDAR_COLORS, color_id, fallback_id=DEFAULT_CALENDAR_COLOR_ID)


def calendar_background(color_id: str | None) -> str:
    return calendar_color_pair(color_id)[0]


def calendar_foreground(color_id: str | None) -> str:
    return calendar_color_pair(color_id)[1]


def event_color_pair(color_id: str | None) -> tuple[str, str]:
    return _color_pair(EVENT_COLORS, color_id, fallback_id="1")
