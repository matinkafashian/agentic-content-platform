from io import BytesIO

from PIL import Image, ImageChops

from app.media import images


def test_branding_preserves_dimensions_and_center_but_marks_both_corners():
    from app.media.image_branding import brand_image

    buffer = BytesIO()
    original = Image.new('RGB', (1024, 1536), 'white')
    original.save(buffer, format='PNG')
    result = brand_image(images.validate_image(buffer.getvalue(), 'a.png', 'image/png'))
    rendered = Image.open(BytesIO(result.data)).convert('RGB')
    assert rendered.size == original.size
    assert rendered.getpixel((512, 768)) == (255, 255, 255)
    assert not ImageChops.difference(rendered, original).crop((750, 0, 1024, 300)).getbbox()
    assert ImageChops.difference(rendered, original).crop((750, 1200, 1024, 1536)).getbbox()
    assert ImageChops.difference(rendered, original).crop((0, 1400, 600, 1536)).getbbox()
