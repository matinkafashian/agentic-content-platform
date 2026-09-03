from io import BytesIO

from PIL import Image

from app.catalog.models import Product
from app.content.models import ContentDraft, DraftStatus
from app.media.image_edit_service import EditedImageRepository, EditedImageService
from app.media.images import validate_image


def png_bytes(color: str) -> bytes:
    output = BytesIO()
    Image.new("RGB", (32, 32), color).save(output, format="PNG")
    return output.getvalue()


def create_draft(db_session) -> tuple[Product, ContentDraft]:
    product = Product(
        name="محصول رنگی",
        description="نمونه تست",
        availability="available",
        shipping_info="",
        attributes={"رنگ": "مطابق تصویر"},
        tags=[],
        primary_image_path="products/1/original/source.png",
        active=True,
    )
    db_session.add(product)
    db_session.flush()
    product.primary_image_path = f"products/{product.id}/original/source.png"
    draft = ContentDraft(
        product_id=product.id,
        series_key="series-image",
        revision=1,
        user_brief="معرفی محصول",
        requested_angle="product_intro",
        provider_name="template",
        provider_payload={"headline": "محصول"},
        final_caption="معرفی محصول",
        status=DraftStatus.WAITING_APPROVAL.value,
    )
    db_session.add(draft)
    db_session.commit()
    return product, draft


def test_edited_image_is_private_and_does_not_replace_product_original(
    db_session, tmp_path
):
    product, draft = create_draft(db_session)
    original_path = product.primary_image_path
    edited = validate_image(png_bytes("green"), "edited.png", "image/png")
    service = EditedImageService(EditedImageRepository(db_session), tmp_path)

    asset = service.attach_or_replace(draft.id, edited)

    assert asset.kind == "image_edited"
    assert asset.relative_path.startswith("private/edited_images/")
    assert service.path_for(asset).read_bytes() == edited.data
    assert product.primary_image_path == original_path


def test_replacing_edited_image_removes_previous_private_file(db_session, tmp_path):
    _, draft = create_draft(db_session)
    service = EditedImageService(EditedImageRepository(db_session), tmp_path)
    first = service.attach_or_replace(
        draft.id, validate_image(png_bytes("red"), "first.png", "image/png")
    )
    old_path = service.path_for(first)

    second = service.attach_or_replace(
        draft.id, validate_image(png_bytes("blue"), "second.png", "image/png")
    )

    assert not old_path.exists()
    assert service.path_for(second).read_bytes() == png_bytes("blue")
