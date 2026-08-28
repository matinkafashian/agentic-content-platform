from hashlib import sha256
from io import BytesIO

import pytest
from PIL import Image

from app.media.images import InvalidImage, save_product_image, validate_image


def png_bytes() -> bytes:
    output = BytesIO()
    Image.new("RGB", (32, 32), "white").save(output, format="PNG")
    return output.getvalue()


def test_valid_image_is_verified_and_saved_under_product_directory(tmp_path):
    source = png_bytes()
    image = validate_image(source, "product.png", "image/png")
    path = save_product_image(tmp_path, 12, image)

    assert image.width == 32
    assert image.height == 32
    assert image.sha256 == sha256(source).hexdigest()
    assert path.parent == tmp_path / "products" / "12" / "original"
    assert path.suffix == ".png"
    assert "product" not in path.name
    assert path.read_bytes() == source


def test_fake_image_is_rejected():
    with pytest.raises(InvalidImage, match="ساختار تصویر معتبر نیست"):
        validate_image(b"not-an-image", "fake.png", "image/png")


def test_oversized_image_is_rejected(monkeypatch):
    monkeypatch.setattr("app.media.images.MAX_IMAGE_BYTES", 8)

    with pytest.raises(InvalidImage, match="حجم تصویر"):
        validate_image(png_bytes(), "photo.png", "image/png")


def test_declared_mime_must_match_image_signature():
    with pytest.raises(InvalidImage, match="نوع اعلام‌شده"):
        validate_image(png_bytes(), "photo.jpg", "image/jpeg")


def test_filename_extension_must_match_verified_format():
    with pytest.raises(InvalidImage, match="پسوند فایل"):
        validate_image(png_bytes(), "photo.txt", "image/png")


def test_unsupported_mime_is_rejected_before_decoding():
    with pytest.raises(InvalidImage, match="نوع تصویر پشتیبانی نمی‌شود"):
        validate_image(png_bytes(), "photo.png", "application/octet-stream")


def test_excessive_pixel_count_is_rejected(monkeypatch):
    monkeypatch.setattr("app.media.images.MAX_IMAGE_PIXELS", 100)

    with pytest.raises(InvalidImage, match="ابعاد تصویر"):
        validate_image(png_bytes(), "photo.png", "image/png")
