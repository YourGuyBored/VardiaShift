"""The kiosk's second language.

Employees face the kiosk; their language is what the toggle changes. The
administrator screens stay in English because those users already work in
English throughout. Translation is a plain dictionary lookup: the kiosk's
fixed English strings are the keys, Filipino is the value, and anything
missing falls back to English so a forgotten key shows text rather than
nothing. Names, employee codes and the clock format are never translated.
"""

from __future__ import annotations

LANGUAGE_ENGLISH = "english"
LANGUAGE_FILIPINO = "filipino"
KIOSK_LANGUAGES = (LANGUAGE_ENGLISH, LANGUAGE_FILIPINO)
LANGUAGE_LABELS = {
    LANGUAGE_ENGLISH: "English",
    LANGUAGE_FILIPINO: "Filipino",
}

#: English as written on the kiosk -> Filipino.
FILIPINO = {
    # Header and scan panel
    "Scan your employee QR code to begin": (
        "I-scan ang QR code ng empleyado upang mag-umpisa"
    ),
    "SCAN YOUR EMPLOYEE QR CODE": "I-SCAN ANG QR CODE NG EMPLEYADO",
    "1. Scan your personal employee QR code\n2. Then scan the TIME IN or TIME OUT code": (
        "1. I-scan ang sariling QR code ng empleyado\n"
        "2. Pagkatapos, i-scan ang TIME IN o TIME OUT code"
    ),
    "Having trouble? Enter ID manually": "May problema? Maglagay ng ID nang mano-mano",
    "Start camera": "Buksan ang camera",
    "Stop camera": "Isara ang camera",
    "Retry camera": "Subukan muli ang camera",
    "Camera unavailable": "Hindi magamit ang camera",
    "Start the camera to scan with a webcam.": (
        "Buksan ang camera upang mag-scan gamit ang webcam."
    ),
    "Camera stopped.": "Napatay ang camera.",
    "No camera detected. Connect a USB webcam, then press Start camera - a USB QR reader works without one.": (
        "Walang nadetect na camera. Ikabit ang USB webcam, saka pindutin ang "
        "Buksan ang camera - gumagana ang USB QR reader kahit wala nito."
    ),
    "This build has no webcam support. A USB QR reader works normally, or use manual entry.": (
        "Walang suporta sa webcam ang build na ito. Gumagana ang USB QR reader "
        "nang normal, o magmano-mano."
    ),
    "Camera scanning is unavailable in this build. A USB QR reader works normally, or use manual entry.": (
        "Hindi magamit ang pag-scan gamit ang camera sa build na ito. Gumagana "
        "ang USB QR reader nang normal, o magmano-mano."
    ),
    "Camera unavailable - use the USB scanner or manual entry.": (
        "Hindi magamit ang camera - gamitin ang USB scanner o mano-manong paglagay."
    ),
    # Result panel
    "Ready": "Handa na",
    "Waiting for a scan": "Naghihintay ng pag-scan",
    "Scan again": "Mag-scan muli",
    "A USB QR reader works straight away - just scan and press Enter.": (
        "Gumagana agad ang USB QR reader - i-scan lang at pindutin ang Enter."
    ),
    # Flow states
    "Employee confirmed": "Kinilala ang empleyado",
    "SCAN TIME IN / TIME OUT": "I-SCAN ANG TIME IN / TIME OUT",
    "Time in recorded": "Naitala ang time in",
    "TIME IN SUCCESSFUL": "TAGUMPAY ANG TIME IN",
    "Have a productive day!": "Maging masikap ngayong araw!",
    "Time out recorded": "Naitala ang time out",
    "TIME OUT SUCCESSFUL": "TAGUMPAY ANG TIME OUT",
    "Today's work time": "Oras ng trabaho ngayong araw",
    "This week": "Ngayong linggo",
    "Weekly goal reached!": "Naabot ang lingguhang layunin!",
    "Remaining:": "Natitira:",
    # Errors and gates
    "Scan error": "Error sa pag-scan",
    "Unknown employee": "Hindi kilalang empleyado",
    "Not an employee code": "Hindi code ng empleyado",
    "Wrong code": "Maling code",
    "Scan your employee QR code first.": "I-scan muna ang QR code ng empleyado.",
    "Cannot record": "Hindi maitala",
    "No employees": "Walang mga empleyado",
    "Add employees first.": "Magdagdag muna ng empleyado.",
    "Exit kiosk": "Lumabas sa kiosk",
    "Administrator password needed": "Kailangan ang password ng administrator",
}


def kiosk_text(english: str, language: str = LANGUAGE_ENGLISH) -> str:
    """The kiosk string in the chosen language, falling back to English."""
    if language == LANGUAGE_FILIPINO:
        return FILIPINO.get(english, english)
    return english


def kiosk_greeting(name: str, language: str = LANGUAGE_ENGLISH) -> str:
    """The personal greeting after a valid employee scan."""
    if language == LANGUAGE_FILIPINO:
        return f"Kumusta, {name}! Pagkatapos, i-scan ang TIME IN o TIME OUT code."
    return f"Hello, {name}! Now scan the TIME IN or TIME OUT code."


def kiosk_week_line(this_week: str, goal: str, percent: int, language: str) -> str:
    label = kiosk_text("This week", language)
    return f"{label}  {this_week} / {goal}  ({percent}%)"


def kiosk_remaining_line(remaining: str, language: str) -> str:
    return f"{kiosk_text('Remaining:', language)} {remaining}"


def language_label(language: str) -> str:
    return LANGUAGE_LABELS.get(language, language)
