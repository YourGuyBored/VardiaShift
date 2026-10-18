"""The kiosk language toggle: English by default, Filipino when chosen.

The kiosk is the screen employees face, so that is the surface the toggle
covers. The dictionary lookup falls back to English for anything missing,
and names, employee codes and the clock are never translated.
"""

from __future__ import annotations

from app.utils.language import (
    LANGUAGE_ENGLISH,
    LANGUAGE_FILIPINO,
    kiosk_greeting,
    kiosk_remaining_line,
    kiosk_text,
    kiosk_week_line,
    language_label,
)


# -- translation core ---------------------------------------------------------
def test_english_is_passthrough():
    assert kiosk_text("Time in recorded", LANGUAGE_ENGLISH) == "Time in recorded"


def test_known_strings_translate():
    assert kiosk_text("Time in recorded", LANGUAGE_FILIPINO) == "Naitala ang time in"
    assert (
        kiosk_text("TIME IN SUCCESSFUL", LANGUAGE_FILIPINO) == "TAGUMPAY ANG TIME IN"
    )
    assert (
        kiosk_text("SCAN YOUR EMPLOYEE QR CODE", LANGUAGE_FILIPINO)
        == "I-SCAN ANG QR CODE NG EMPLEYADO"
    )


def test_unknown_strings_fall_back_to_english():
    assert (
        kiosk_text("Some string nobody translated", LANGUAGE_FILIPINO)
        == "Some string nobody translated"
    )


def test_composed_lines_carry_values():
    assert (
        kiosk_greeting("Ana", LANGUAGE_FILIPINO)
        == "Kumusta, Ana! Pagkatapos, i-scan ang TIME IN o TIME OUT code."
    )
    assert (
        kiosk_week_line("8h 00m", "8h 00m", 100, LANGUAGE_FILIPINO)
        == "Ngayong linggo  8h 00m / 8h 00m  (100%)"
    )
    assert kiosk_remaining_line("1h 12m", LANGUAGE_FILIPINO) == "Natitira: 1h 12m"
    assert (
        kiosk_week_line("2h", "8h", 25, LANGUAGE_ENGLISH)
        == "This week  2h / 8h  (25%)"
    )


def test_labels_are_readable():
    assert language_label(LANGUAGE_ENGLISH) == "English"
    assert language_label(LANGUAGE_FILIPINO) == "Filipino"


# -- the setting --------------------------------------------------------------
def test_the_setting_defaults_to_english(context):
    assert context.settings.settings.kiosk_language == LANGUAGE_ENGLISH


def test_the_setting_accepts_filipino_only(context, admin):
    context.settings.set("kiosk_language", "Filipino", "admin")
    assert context.settings.settings.kiosk_language == LANGUAGE_FILIPINO
    context.settings.set("kiosk_language", "English", "admin")
    assert context.settings.settings.kiosk_language == LANGUAGE_ENGLISH


def test_an_unknown_language_is_refused(context, admin):
    import pytest

    with pytest.raises(ValueError):
        context.settings.set("kiosk_language", "Klingon", "admin")


def test_the_spec_lives_in_the_kiosk_group(context):
    specs = {spec.key: spec for spec in context.settings.settings.specs_for_group(
        "Attendance Kiosk"
    )}
    assert "kiosk_language" in specs
    assert tuple(specs["kiosk_language"].choices) == ("English", "Filipino")


# -- on the actual kiosk ------------------------------------------------------
def test_the_kiosk_renders_english_by_default(context, qt_app, admin):
    from app.ui.attendance_kiosk import KioskWindow

    window = KioskWindow(context)
    assert window._prompt.text() == "SCAN YOUR EMPLOYEE QR CODE"
    assert window._fallback_button.text() == "Having trouble? Enter ID manually"
    window.deleteLater()


def test_the_kiosk_renders_filipino(context, qt_app, admin):
    from app.ui.attendance_kiosk import KioskWindow

    context.settings.set("kiosk_language", "Filipino", "admin")
    window = KioskWindow(context)
    assert window._prompt.text() == "I-SCAN ANG QR CODE NG EMPLEYADO"
    assert window._fallback_button.text() == "May problema? Maglagay ng ID nang mano-mano"
    assert window._reset_button.text() == "Mag-scan muli"
    window.deleteLater()


def test_the_kiosk_result_screens_translate(context, qt_app, admin, employee, frozen):
    from app.ui.attendance_kiosk import KioskWindow

    context.settings.set("kiosk_language", "Filipino", "admin")
    window = KioskWindow(context)
    window._employee = employee

    context.attendance.set_now_provider(lambda: frozen.at(10, 0, 1))
    window._perform_clock("time_in", "time_in:1")
    assert window._status.text() == "Naitala ang time in"
    assert window._result_title.text() == "TAGUMPAY ANG TIME IN"
    assert "Maging masikap ngayong araw!" in window._result_details.text()
    window.deleteLater()
