"""Deterministic branding shared by studio and cinematic image outputs."""

from io import BytesIO
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps

from app.media.images import ValidatedImage, validate_image

LOGO_PATH = Path(__file__).resolve().parents[1] / 'static/branding/hayka-logo.jpg'
PHONE = '+98 918 396 2948'


def brand_image(image: ValidatedImage) -> ValidatedImage:
    with Image.open(BytesIO(image.data)) as source:
        canvas = ImageOps.exif_transpose(source).convert('RGB')
    width, height = canvas.size
    margin = max(1, round(min(width, height) * 0.035))
    size = max(1, round(min(width, height) * 0.18))
    with Image.open(LOGO_PATH) as source_logo:
        # The supplied portrait has large black margins around the circular mark.
        logo = source_logo.convert('RGB')
        bounds = logo.convert('L').point(lambda value: 255 if value > 45 else 0).getbbox()
        if bounds:
            logo = logo.crop(bounds)
        logo.thumbnail((size, size), Image.Resampling.LANCZOS)
        mask = Image.new('L', logo.size)
        ImageDraw.Draw(mask).ellipse((0, 0, logo.width - 1, logo.height - 1), fill=255)
        canvas.paste(logo, (width - margin - logo.width, height - margin - logo.height), mask)
    draw = ImageDraw.Draw(canvas)
    font = ImageFont.load_default(size=max(1, round(min(width, height) * 0.025)))
    box = draw.textbbox((0, 0), PHONE, font=font)
    padding = max(1, round(min(width, height) * 0.012))
    text_width, text_height = box[2] - box[0], box[3] - box[1]
    top = height - margin - text_height - padding * 2
    draw.rounded_rectangle((margin, top, margin + text_width + padding * 2,
                            height - margin), radius=padding, fill='#141414')
    draw.text((margin + padding - box[0], top + padding - box[1]), PHONE,
              font=font, fill='#F2D49B')
    output = BytesIO()
    canvas.save(output, format='PNG')
    return validate_image(output.getvalue(), 'branded.png', 'image/png')
