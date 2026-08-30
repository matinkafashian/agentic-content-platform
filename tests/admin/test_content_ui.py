import re


def generate_content(client, csrf_token: str, product_id: int) -> int:
    response = client.post(
        "/admin/content",
        data={
            "csrf_token": csrf_token,
            "product_id": str(product_id),
            "user_brief": "این مدل برای پروژه نئوکلاسیک معرفی شود و مشخصات واقعی برجسته شود.",
            "requested_angle": "product_intro",
        },
        follow_redirects=False,
    )
    match = re.fullmatch(r"/admin/content/(\d+)", response.headers["location"])
    assert match is not None
    return int(match.group(1))


def test_admin_navigation_exposes_content_studio_and_brand_settings(
    authenticated_client,
):
    page = authenticated_client.get("/admin")

    assert 'href="/admin/content/new"' in page.text
    assert "استودیوی محتوا" in page.text
    assert 'href="/admin/brand"' in page.text
    assert "تنظیمات برند" in page.text


def test_product_detail_links_directly_to_prefilled_content_form(
    authenticated_client, product
):
    page = authenticated_client.get(f"/admin/products/{product.id}")

    assert f'href="/admin/content/new?product_id={product.id}"' in page.text
    assert "ساخت محتوا" in page.text


def test_content_form_has_persian_guidance_and_all_angles(
    authenticated_client, product
):
    page = authenticated_client.get(f"/admin/content/new?product_id={product.id}")

    assert "خلاصه کوتاه شما" in page.text
    assert "معرفی محصول" in page.text
    assert "آموزشی" in page.text
    assert "پرسش رایج" in page.text
    assert "اعتمادسازی" in page.text
    assert "راهنمای سفارش" in page.text


def test_content_preview_separates_source_facts_from_editable_caption(
    authenticated_client, csrf_token, product
):
    draft_id = generate_content(authenticated_client, csrf_token, product.id)

    page = authenticated_client.get(f"/admin/content/{draft_id}")

    assert 'class="source-facts' in page.text
    assert "اطلاعات قطعی محصول" in page.text
    assert "۱۲٬۵۰۰٬۰۰۰" in page.text
    assert 'name="final_caption"' in page.text
    assert 'class="provider-warning' in page.text
    assert "حالت آزمایشی — بدون OpenAI" in page.text
    assert 'class="revision-list' in page.text


def test_voice_recorder_has_accessible_controls_and_private_source(
    authenticated_client, csrf_token, product
):
    draft_id = generate_content(authenticated_client, csrf_token, product.id)
    voice = b"\x1aE\xdf\xa3recorded" + b"\x00" * 24
    authenticated_client.post(
        f"/admin/content/{draft_id}/voice",
        data={"csrf_token": csrf_token, "duration_ms": "1500"},
        files={"voice": ("recording.webm", voice, "audio/webm")},
    )

    page = authenticated_client.get(f"/admin/content/{draft_id}")

    for hook in (
        "data-voice-recorder",
        "data-record-start",
        "data-record-stop",
        "data-record-preview",
        "data-record-file",
        "data-record-duration",
        "data-record-timer",
        "data-record-save",
    ):
        assert hook in page.text
    assert 'id="voice-studio"' in page.text
    assert 'class="recorder-button recorder-start"' in page.text
    assert 'class="recorder-button recorder-stop"' in page.text
    assert f'src="/admin/content/{draft_id}/voice"' in page.text
    assert "وویس ذخیره‌شده و آماده پخش است" in page.text
    assert "/uploads/private" not in page.text
    assert 'src="/static/js/voice-recorder.js"' in page.text
    assert 'type="file" name="voice"' in page.text
    assert 'type="file" name="voice" hidden' in page.text
    assert "فایل وویس" not in page.text
    assert "یک فایل صوتی انتخاب کنید" not in page.text
