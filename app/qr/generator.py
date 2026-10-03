"""QR generation (images + printable cards)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import qrcode
from qrcode.constants import ERROR_CORRECT_H
from qrcode.image.pil import PilImage

from app.constants import APP_NAME
from app.qr.tokens import build_payload
from app.utils.time_utils import TimeUtils

try:  # Pillow is required for image composition.
    from PIL import Image, ImageDraw, ImageFont
except ImportError:  # pragma: no cover - Pillow ships with requirements
    Image = None  # type: ignore[assignment]
    ImageDraw = None  # type: ignore[assignment]
    ImageFont = None  # type: ignore[assignment]

QR_ERROR_CORRECT = ERROR_CORRECT_H
FILL_DARK = "#0F172A"
FILL_LIGHT = "#FFFFFF"


@dataclass
class QRCardSpec:
    title: str
    subtitle: str
    footer: str
    width: int = 760
    accent: str = "#2563EB"


def _load_font(size: int, bold: bool = False) -> "ImageFont.FreeTypeFont | ImageFont.ImageFont":
    if ImageFont is None:  # pragma: no cover
        return None
    candidates = [
        "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf",
        "/usr/share/fonts/truetype/dejavu/" + ("DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf"),
        "arialbd.ttf" if bold else "arial.ttf",
    ]
    for name in candidates:
        try:
            return ImageFont.truetype(name, size)
        except (OSError, ValueError):
            continue
    try:
        return ImageFont.load_default(size=size)
    except TypeError:  # pragma: no cover - very old Pillow
        return ImageFont.load_default()


def _text_size(draw, text: str, font) -> tuple[int, int]:
    if not text:
        return (0, 0)
    box = draw.textbbox((0, 0), text, font=font)
    return (box[2] - box[0], box[3] - box[1])


def make_qr_image(
    payload: str,
    box_size: int = 12,
    border: int = 3,
) -> "Image.Image":
    """Render a payload into a square :class:`PIL.Image.Image`."""
    if Image is None:  # pragma: no cover
        raise RuntimeError("Pillow is required to generate QR codes.")
    qr = qrcode.QRCode(
        version=None,
        error_correction=QR_ERROR_CORRECT,
        box_size=box_size,
        border=border,
    )
    qr.add_data(payload)
    qr.make(fit=True)
    image: PilImage = qr.make_image(fill_color=FILL_DARK, back_color=FILL_LIGHT)
    return image.convert("RGB")


def make_qr_png(payload: str, path: Path | str, box_size: int = 12) -> Path:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    make_qr_image(payload, box_size=box_size).save(destination, format="PNG")
    return destination


def make_card(
    payload: str,
    spec: QRCardSpec,
    box_size: int = 12,
) -> "Image.Image":
    """Compose a printable card: title, QR image, subtitle and footer."""
    if Image is None:  # pragma: no cover
        raise RuntimeError("Pillow is required to generate QR cards.")

    qr_image = make_qr_image(payload, box_size=box_size)
    qr_size = qr_image.size[0]

    canvas = Image.new("RGB", (spec.width, qr_size + 320), FILL_LIGHT)
    draw = ImageDraw.Draw(canvas)

    title_font = _load_font(52, bold=True)
    sub_font = _load_font(28)
    foot_font = _load_font(22)

    title_w, title_h = _text_size(draw, spec.title, title_font)
    draw.text(
        ((spec.width - title_w) / 2, 40),
        spec.title,
        font=title_font,
        fill=spec.accent,
    )

    qr_x = (spec.width - qr_size) // 2
    qr_y = 120
    canvas.paste(qr_image, (qr_x, qr_y))
    draw.rectangle(
        [qr_x - 6, qr_y - 6, qr_x + qr_size + 6, qr_y + qr_size + 6],
        outline=spec.accent,
        width=4,
    )

    sub_y = qr_y + qr_size + 40
    sub_w, sub_h = _text_size(draw, spec.subtitle, sub_font)
    draw.text(
        ((spec.width - sub_w) / 2, sub_y),
        spec.subtitle,
        font=sub_font,
        fill="#334155",
    )

    foot_w, foot_h = _text_size(draw, spec.footer, foot_font)
    draw.text(
        ((spec.width - foot_w) / 2, sub_y + sub_h + 30),
        spec.footer,
        font=foot_font,
        fill="#64748B",
    )
    return canvas


def build_employee_card(
    payload: str,
    organization: str,
    employee_name: str,
    employee_code: str,
    generated_at: str | None = None,
) -> "Image.Image":
    stamp = generated_at or TimeUtils().format_datetime(None)
    return make_card(
        payload,
        QRCardSpec(
            title="EMPLOYEE ID",
            subtitle=employee_name,
            footer=f"{employee_code}  •  {organization}  •  {stamp}",
            accent="#0EA5E9",
        ),
    )


def build_action_card(
    payload: str,
    organization: str,
    title: str,
    subtitle: str,
    accent: str,
    generated_at: str | None = None,
) -> "Image.Image":
    stamp = generated_at or TimeUtils().format_datetime(None)
    return make_card(
        payload,
        QRCardSpec(
            title=title,
            subtitle=subtitle,
            footer=f"{organization}  •  {APP_NAME}  •  {stamp}",
            accent=accent,
        ),
    )


def save_image(image: "Image.Image", path: Path | str) -> Path:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    image.save(destination, format="PNG")
    return destination


def payloads_summary() -> str:  # pragma: no cover - documentation helper
    return "\n".join(
        [
            f"{kind:>10}: {build_payload(kind, 'x' * 24)}",
        ]
        for kind in ("employee", "time_in", "time_out")
    )