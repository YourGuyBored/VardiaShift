"""Accent colours and the login window's spacing."""

from __future__ import annotations

import pytest

from app.utils import appearance
from app.utils.appearance import (
    ACCENT_FIELDS,
    ACCENT_NAMES,
    ACCENTS,
    DEFAULT_ACCENT,
    accent_from_color,
    hex_to_rgb,
    is_valid_color,
    lighten,
    darken,
    resolve,
)


def teardown_function():
    """Each test leaves the module's colours behind, so put them back."""
    from app.ui import theme

    theme.use_accent(ACCENTS[DEFAULT_ACCENT])


# -- colour maths ------------------------------------------------------------
@pytest.mark.parametrize(
    "value,expected",
    [("#000000", (0, 0, 0)), ("#FFFFFF", (255, 255, 255)), ("#2563EB", (37, 99, 235))],
)
def test_hex_to_rgb(value, expected):
    assert hex_to_rgb(value) == expected


def test_short_hex_expands():
    assert hex_to_rgb("#0F8") == (0, 255, 136)


def test_lighten_moves_towards_white():
    assert lighten("#2563EB") == "#9DB9F6"


def test_darken_moves_towards_black():
    assert darken("#2563EB") == "#1C4AB0"


def test_lighten_never_exceeds_the_channel_range():
    assert lighten("#FFFFFF") == "#FFFFFF"
    assert darken("#000000") == "#000000"


# -- validation --------------------------------------------------------------
@pytest.mark.parametrize("value", ["#0D9488", "#fff", "#ABCDEF", "  #0D9488  "])
def test_valid_colors(value):
    assert is_valid_color(value) is True


@pytest.mark.parametrize(
    "value", ["", "0D9488", "#0D948", "#GGGGGG", "blue", "#1234567", None]
)
def test_invalid_colors(value):
    assert is_valid_color(value) is False


# -- accents -----------------------------------------------------------------
def test_every_named_accent_supplies_every_field():
    for name in ACCENT_NAMES:
        assert set(ACCENTS[name]) == set(ACCENT_FIELDS), name


def test_every_named_accent_colour_is_valid_hex():
    for name, accent in ACCENTS.items():
        for field, value in accent.items():
            assert is_valid_color(value), f"{name}.{field} = {value}"


def test_accent_names_match_the_dict():
    assert set(ACCENT_NAMES) == set(ACCENTS)


def test_default_accent_is_one_of_the_named_ones():
    assert DEFAULT_ACCENT in ACCENTS


def test_named_accents_are_visibly_different():
    primaries = {ACCENTS[name]["PRIMARY"] for name in ACCENT_NAMES}
    assert len(primaries) == len(ACCENT_NAMES)


def test_custom_colour_fills_every_field():
    accent = accent_from_color("#0D9488")
    assert set(accent) == set(ACCENT_FIELDS)
    assert accent["PRIMARY"] == "#0D9488"


def test_custom_colour_is_normalised_to_upper_case():
    assert accent_from_color("#ea580c")["PRIMARY"] == "#EA580C"


def test_derived_dark_is_darker_than_the_primary():
    accent = accent_from_color("#0D9488")
    assert hex_to_rgb(accent["PRIMARY_DARK"]) < hex_to_rgb(accent["PRIMARY"])


def test_derived_soft_is_lighter_than_the_primary():
    accent = accent_from_color("#0D9488")
    assert hex_to_rgb(accent["PRIMARY_SOFT"]) > hex_to_rgb(accent["PRIMARY"])


# -- resolution --------------------------------------------------------------
def test_resolve_uses_the_named_accent_when_no_custom_is_given():
    assert resolve("Green", "") == ACCENTS["Green"]


def test_resolve_prefers_a_valid_custom_colour():
    assert resolve("Green", "#0D9488")["PRIMARY"] == "#0D9488"


def test_resolve_falls_back_when_the_custom_colour_is_junk():
    assert resolve("Green", "not-a-colour") == ACCENTS["Green"]


def test_resolve_falls_back_on_an_unknown_name():
    assert resolve("Chartreuse", "") == ACCENTS[DEFAULT_ACCENT]


def test_resolve_defaults_when_nothing_is_set():
    assert resolve() == ACCENTS[DEFAULT_ACCENT]


def test_resolve_returns_a_copy():
    first = resolve("Green", "")
    first["PRIMARY"] = "#000000"
    assert ACCENTS["Green"]["PRIMARY"] == "#16A34A"


# -- the settings model ------------------------------------------------------
def test_accent_settings_are_declared(context):
    specs = {spec.key: spec for spec in context.settings.settings.specs_for_group("Appearance")}
    assert "accent_color" in specs
    assert "custom_accent" in specs


def test_accent_colour_offers_the_named_accents(context):
    from app.models.settings import GROUP_APPEARANCE

    spec = next(
        item
        for item in context.settings.settings.specs_for_group(GROUP_APPEARANCE)
        if item.key == "accent_color"
    )
    assert tuple(spec.choices) == ACCENT_NAMES


def test_default_accent_is_blue(context):
    settings = context.settings.settings
    assert settings.accent["PRIMARY"] == ACCENTS[DEFAULT_ACCENT]["PRIMARY"]


def test_saving_a_custom_accent_is_picked_up(context, admin):
    context.settings.set("custom_accent", "#0D9488", "admin")
    context.settings.refresh()
    assert context.settings.settings.accent["PRIMARY"] == "#0D9488"


def test_saving_a_junk_accent_is_refused_not_silently_ignored(context, admin):
    context.settings.set("accent_color", "Green", "admin")
    with pytest.raises(ValueError):
        context.settings.set("custom_accent", "purple-ish", "admin")
    context.settings.refresh()
    assert context.settings.settings.accent["PRIMARY"] == ACCENTS["Green"]["PRIMARY"]


# -- the running application -------------------------------------------------
def test_switching_accent_recolours_the_stylesheet(qt_app):
    from app.ui import theme

    theme.use_accent(ACCENTS["Teal"])
    css = theme.build_stylesheet()
    assert ACCENTS["Teal"]["PRIMARY"] in css
    assert ACCENTS[DEFAULT_ACCENT]["PRIMARY"] not in css


def test_switching_accent_leaves_no_default_colours_behind(qt_app):
    """The sidebar and hero gradients must follow, or the app looks half-done."""
    from app.ui import theme

    theme.use_accent(ACCENTS["Purple"])
    css = theme.build_stylesheet()
    for stale in (
        ACCENTS[DEFAULT_ACCENT]["BG"],
        ACCENTS[DEFAULT_ACCENT]["BG_ACCENT"],
        ACCENTS[DEFAULT_ACCENT]["ACCENT_LIGHT"],
    ):
        if stale == theme.TEXT:
            continue  # a colour the text tokens legitimately share
        assert stale not in css, f"{stale} survived the accent change"


def test_apply_accent_changes_the_live_theme(qt_app):
    from app.ui import theme

    theme.apply_accent(qt_app, ACCENTS["Orange"])
    assert theme.PRIMARY == ACCENTS["Orange"]["PRIMARY"]
    assert qt_app.styleSheet()


def test_apply_accent_ignores_a_missing_accent(qt_app):
    from app.ui import theme

    theme.apply_accent(qt_app, ACCENTS["Green"])
    theme.apply_accent(qt_app, None)
    assert theme.PRIMARY == ACCENTS["Green"]["PRIMARY"]


def test_current_accent_reports_what_is_active(qt_app):
    from app.ui import theme

    theme.use_accent(ACCENTS["Slate"])
    assert theme.current_accent()["PRIMARY"] == ACCENTS["Slate"]["PRIMARY"]


def test_every_named_accent_builds_a_usable_stylesheet(qt_app):
    from app.ui import theme

    for name in ACCENT_NAMES:
        theme.use_accent(ACCENTS[name])
        css = theme.build_stylesheet()
        assert ACCENTS[name]["PRIMARY"] in css
        assert "{{" not in css and "}}" not in css


def test_a_junk_custom_accent_is_rejected_at_save(context, admin):
    import pytest

    with pytest.raises(ValueError) as excinfo:
        context.settings.set("custom_accent", "purple-ish", "admin")
    assert "hex colour" in str(excinfo.value)


def test_an_empty_custom_accent_is_accepted(context, admin):
    context.settings.set("accent_color", "Green", "admin")
    context.settings.set("custom_accent", "", "admin")
    context.settings.refresh()
    assert context.settings.settings.accent["PRIMARY"] == ACCENTS["Green"]["PRIMARY"]


def test_a_short_hex_custom_accent_is_accepted(context, admin):
    context.settings.set("custom_accent", "#0F8", "admin")
    context.settings.refresh()
    assert context.settings.settings.accent["PRIMARY"] == "#0F8"


def test_settings_page_has_an_appearance_tab(context, qt_app):
    from app.ui.settings import SettingsPage

    page = SettingsPage(context)
    labels = [page._tabs.tabText(index) for index in range(page._tabs.count())]
    assert "Appearance" in labels
    page.deleteLater()


def test_settings_page_preview_shows_the_accent_buttons(context, qt_app):
    from app.ui.settings import SettingsPage

    page = SettingsPage(context)
    index = next(
        i for i in range(page._tabs.count()) if page._tabs.tabText(i) == "Appearance"
    )
    page._tabs.setCurrentIndex(index)
    assert page._appearance_preview is not None
    page.deleteLater()
