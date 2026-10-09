"""Accent colour sets, and how to pick one.

Lives in ``app.utils`` rather than ``app.ui`` because the settings model needs
the list of names for its drop-down and a model must not import the view layer.
It also cannot live under ``app.services``, whose package import pulls in the
attendance service and so back round to the models. Nothing here touches Qt;
``app.ui.theme`` consumes these values to build the stylesheet and palette.
"""

from __future__ import annotations

#: Every colour a complete accent has to supply. The stylesheet, the palette and
#: the hand-drawn charts all read these, so an accent that set only the main
#: colour would leave unreadable contrast behind.
ACCENT_FIELDS = (
    "PRIMARY",
    "PRIMARY_DARK",
    "PRIMARY_SOFT",
    "BG",
    "BG_ACCENT",
    "ACCENT_LIGHT",
)

DEFAULT_ACCENT = "Blue (default)"

#: Ordered names of the named accents, for drop-downs and settings specs.
ACCENT_NAMES: tuple[str, ...] = (
    "Blue (default)",
    "Green",
    "Purple",
    "Teal",
    "Orange",
    "Slate",
)

#: Named accents offered in Settings, each a complete set so the contrast is
#: already known to work.
ACCENTS: dict[str, dict[str, str]] = {
    "Blue (default)": {
        "PRIMARY": "#2563EB",
        "PRIMARY_DARK": "#1D4ED8",
        "PRIMARY_SOFT": "#DBEAFE",
        "BG": "#0F172A",
        "BG_ACCENT": "#1E3A8A",
        "ACCENT_LIGHT": "#60A5FA",
    },
    "Green": {
        "PRIMARY": "#16A34A",
        "PRIMARY_DARK": "#15803D",
        "PRIMARY_SOFT": "#DCFCE7",
        "BG": "#0B1F16",
        "BG_ACCENT": "#14532D",
        "ACCENT_LIGHT": "#4ADE80",
    },
    "Purple": {
        "PRIMARY": "#7C3AED",
        "PRIMARY_DARK": "#6D28D9",
        "PRIMARY_SOFT": "#EDE9FE",
        "BG": "#1E1B2E",
        "BG_ACCENT": "#4C1D95",
        "ACCENT_LIGHT": "#A78BFA",
    },
    "Teal": {
        "PRIMARY": "#0D9488",
        "PRIMARY_DARK": "#0F766E",
        "PRIMARY_SOFT": "#CCFBF1",
        "BG": "#0F1F1E",
        "BG_ACCENT": "#134E4A",
        "ACCENT_LIGHT": "#2DD4BF",
    },
    "Orange": {
        "PRIMARY": "#EA580C",
        "PRIMARY_DARK": "#C2410C",
        "PRIMARY_SOFT": "#FFEDD5",
        "BG": "#1F1710",
        "BG_ACCENT": "#7C2D12",
        "ACCENT_LIGHT": "#FB923C",
    },
    "Slate": {
        "PRIMARY": "#475569",
        "PRIMARY_DARK": "#334155",
        "PRIMARY_SOFT": "#E2E8F0",
        "BG": "#0F172A",
        "BG_ACCENT": "#1E293B",
        "ACCENT_LIGHT": "#94A3B8",
    },
}


def hex_to_rgb(value: str) -> tuple[int, int, int]:
    text = value.strip().lstrip("#")
    if len(text) == 3:
        text = "".join(character * 2 for character in text)
    return int(text[0:2], 16), int(text[2:4], 16), int(text[4:6], 16)


def rgb_to_hex(red: int, green: int, blue: int) -> str:
    return "#{:02X}{:02X}{:02X}".format(
        max(0, min(255, red)), max(0, min(255, green)), max(0, min(255, blue))
    )


def mix(first: str, second: str, weight: float) -> str:
    """Blend two colours, ``weight`` being how much of ``second`` to use."""
    a = hex_to_rgb(first)
    b = hex_to_rgb(second)
    return rgb_to_hex(
        round(a[0] + (b[0] - a[0]) * weight),
        round(a[1] + (b[1] - a[1]) * weight),
        round(a[2] + (b[2] - a[2]) * weight),
    )


def lighten(value: str, amount: float = 0.55) -> str:
    return mix(value, "#FFFFFF", amount)


def darken(value: str, amount: float = 0.25) -> str:
    return mix(value, "#000000", amount)


def is_valid_color(value: str) -> bool:
    """True for ``#RGB`` and ``#RRGGBB``."""
    text = (value or "").strip()
    if not text.startswith("#") or len(text) not in (4, 7):
        return False
    try:
        hex_to_rgb(text)
    except ValueError:
        return False
    return True


def accent_from_color(picked: str) -> dict[str, str]:
    """Derive a complete accent set from one chosen colour.

    The dark and light ends are computed rather than asked for, so a colour a
    user types still produces readable buttons and a visible sidebar.
    """
    return {
        "PRIMARY": picked.strip().upper(),
        "PRIMARY_DARK": darken(picked, 0.22),
        "PRIMARY_SOFT": lighten(picked, 0.82),
        "BG": darken(picked, 0.82),
        "BG_ACCENT": darken(picked, 0.6),
        "ACCENT_LIGHT": lighten(picked, 0.42),
    }


def resolve(named: str = "", custom: str = "") -> dict[str, str]:
    """The accent to use: the custom colour if it is valid, else the named one."""
    custom = (custom or "").strip()
    if is_valid_color(custom):
        return accent_from_color(custom)
    return dict(ACCENTS.get(named or DEFAULT_ACCENT, ACCENTS[DEFAULT_ACCENT]))
