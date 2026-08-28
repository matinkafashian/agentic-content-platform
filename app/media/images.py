from dataclasses import dataclass
from hashlib import sha256
from io import BytesIO
from pathlib import Path
from uuid import uuid4

from PIL import Image, UnidentifiedImageError

MAX_IMAGE_BYTES = 15 * 1024 * 1024
MAX_IMAGE_PIXELS = 20_000_000
ALLOWED_MIME = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}
ALLOWED_EXTENSIONS = {
    ".jpg": ".jpg",
    ".jpeg": ".jpg",
    ".png": ".png",
    ".webp": ".webp",
}
FORMAT_SUFFIX = {"JPEG": ".jpg", "PNG": ".png", "WEBP": ".webp"}


@dataclass(frozen=True)
class ValidatedImage:
    data: bytes
    suffix: str
    sha256: str
    width: int
    height: int


class InvalidImage(ValueError):
    pass


def validate_image(data: bytes, filename: str, content_type: str) -> ValidatedImage:
    immutable_data = bytes(data)
    if len(immutable_data) > MAX_IMAGE_BYTES:
        raise InvalidImage("حجم تصویر بیشتر از حد مجاز است")

    expected_suffix = ALLOWED_MIME.get(content_type.lower())
    if expected_suffix is None:
        raise InvalidImage("نوع تصویر پشتیبانی نمی‌شود")

    filename_suffix = ALLOWED_EXTENSIONS.get(Path(filename).suffix.lower())
    if filename_suffix != expected_suffix:
        raise InvalidImage("پسوند فایل با نوع تصویر یکسان نیست")

    try:
        with Image.open(BytesIO(immutable_data)) as opened:
            opened.verify()
        with Image.open(BytesIO(immutable_data)) as opened:
            width, height = opened.size
            actual_format = (opened.format or "").upper()
    except (UnidentifiedImageError, OSError, SyntaxError, Image.DecompressionBombError) as exc:
        raise InvalidImage("ساختار تصویر معتبر نیست") from exc

    format_suffix = FORMAT_SUFFIX.get(actual_format)
    if format_suffix != expected_suffix:
        raise InvalidImage("نوع اعلام‌شده با محتوای تصویر یکسان نیست")
    if width * height > MAX_IMAGE_PIXELS:
        raise InvalidImage("ابعاد تصویر بیشتر از حد مجاز است")

    return ValidatedImage(
        data=immutable_data,
        suffix=format_suffix,
        sha256=sha256(immutable_data).hexdigest(),
        width=width,
        height=height,
    )


def save_product_image(root: Path, product_id: int, image: ValidatedImage) -> Path:
    directory = root / "products" / str(product_id) / "original"
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / f"{uuid4().hex}{image.suffix}"
    target.write_bytes(image.data)
    return target
