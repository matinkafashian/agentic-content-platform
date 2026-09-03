import re

from app.content.schemas import GeneratedContent


class SuccessfulOpenAIProvider:
    name = "openai:gpt-test-model"

    def generate(self, request):
        return GeneratedContent(
            headline="✨ معرفی حرفه‌ای محصول",
            body="این متن با تکیه بر اطلاعات ثبت‌شده محصول آماده شده است.",
            benefits=["✅ متریال ثبت‌شده: MDF"],
            cta=request.brand.default_cta,
            hashtags=["درب ممبران", "نئوکلاسیک"],
            used_emojis=["✨", "✅"],
            content_angle=request.requested_angle,
        )


def generate_content(client, csrf_token: str, product_id: int) -> int:
    response = client.post(
        "/admin/content",
        data={
            "csrf_token": csrf_token,
            "product_id": str(product_id),
            "content_mode": "ai",
            "ai_brief": "این مدل برای پروژه نئوکلاسیک معرفی شود و مشخصات واقعی برجسته شود.",
            "manual_caption": "",
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
    assert 'href="/admin/publishing"' in page.text
    assert "انتشار و زمان‌بندی" in page.text


def test_product_detail_links_directly_to_prefilled_content_form(authenticated_client, product):
    page = authenticated_client.get(f"/admin/products/{product.id}")

    assert f'href="/admin/content/new?product_id={product.id}"' in page.text
    assert "ساخت محتوا" in page.text


def test_content_form_has_persian_guidance_and_all_angles(authenticated_client, product):
    page = authenticated_client.get(f"/admin/content/new?product_id={product.id}")

    assert "روش آماده‌سازی متن" in page.text
    assert "تولید با هوش مصنوعی" in page.text
    assert "متن کامل خودم" in page.text
    assert "نکته ویژه این پست (اختیاری)" not in page.text
    assert "معرفی محصول" in page.text
    assert "آموزشی" in page.text
    assert "پرسش رایج" in page.text
    assert "اعتمادسازی" in page.text
    assert "راهنمای سفارش" in page.text
    assert 'name="content_mode" value="ai"' in page.text
    assert 'name="content_mode" value="manual"' in page.text
    assert 'name="ai_brief"' in page.text
    assert 'name="manual_caption"' in page.text
    assert 'name="user_brief"' not in page.text


def test_content_detail_uses_aligned_control_grids(
    authenticated_client, csrf_token, product, png_upload
):
    relative_path = f"products/{product.id}/original/aligned.png"
    image_path = authenticated_client.app.state.settings.upload_dir / relative_path
    image_path.parent.mkdir(parents=True, exist_ok=True)
    image_path.write_bytes(png_upload)
    with authenticated_client.app.state.session_factory() as session:
        stored_product = session.get(type(product), product.id)
        stored_product.primary_image_path = relative_path
        session.commit()
    authenticated_client.app.state.image_editor = object()
    draft_id = generate_content(authenticated_client, csrf_token, product.id)

    page = authenticated_client.get(f"/admin/content/{draft_id}")

    assert 'class="image-edit-form aligned-control-grid"' in page.text


def test_openai_mode_is_clear_in_form_and_generated_preview(
    authenticated_client, csrf_token, product
):
    authenticated_client.app.state.content_provider = SuccessfulOpenAIProvider()

    form = authenticated_client.get(f"/admin/content/new?product_id={product.id}")
    draft_id = generate_content(authenticated_client, csrf_token, product.id)
    preview = authenticated_client.get(f"/admin/content/{draft_id}")

    assert "ساخت پیش‌نویس با هوش مصنوعی" in form.text
    assert "تولیدشده با OpenAI" in preview.text
    assert "نیازمند تأیید مدیر" in preview.text
    assert "حالت آزمایشی — بدون OpenAI" not in preview.text
    assert 'class="provider-warning provider-live"' in preview.text


def test_content_preview_separates_source_facts_from_editable_caption(
    authenticated_client, csrf_token, product
):
    draft_id = generate_content(authenticated_client, csrf_token, product.id)

    page = authenticated_client.get(f"/admin/content/{draft_id}")

    assert 'class="source-facts' in page.text
    assert "اطلاعات قطعی محصول" in page.text
    assert '<div class="fact-row"><span>قیمت</span>' not in page.text
    assert "💰 قیمت:" not in page.text
    assert "برای استعلام قیمت و ثبت سفارش" in page.text
    assert 'name="final_caption"' in page.text
    assert 'class="provider-warning' in page.text
    assert "حالت آزمایشی — بدون OpenAI" in page.text
    assert 'class="revision-list' in page.text


def test_content_preview_exposes_one_clear_current_step_and_next_action(
    authenticated_client, csrf_token, product
):
    draft_id = generate_content(authenticated_client, csrf_token, product.id)

    page = authenticated_client.get(f"/admin/content/{draft_id}")

    assert 'aria-label="وضعیت آماده‌سازی محتوا"' in page.text
    assert page.text.count('aria-current="step"') == 1
    assert 'data-workflow-current="caption"' in page.text
    assert "قدم بعدی" in page.text
    assert "بررسی و تأیید متن" in page.text
    assert 'class="button button-primary" href="#caption-studio"' in page.text
    assert '<details class="panel caption-preview workflow-section"' in page.text
    assert 'id="caption-studio" open' in page.text
    assert 'id="image-studio" open' not in page.text


def test_workflow_moves_to_bundle_after_manual_approval_without_image(
    authenticated_client, csrf_token, product
):
    draft_id = generate_content(authenticated_client, csrf_token, product.id)
    authenticated_client.post(
        f"/admin/content/{draft_id}/approve",
        data={"csrf_token": csrf_token},
    )

    page = authenticated_client.get(f"/admin/content/{draft_id}")

    assert 'data-workflow-current="bundle"' in page.text
    assert "ساخت بسته نهایی" in page.text
    assert "نبود تصویر مانع ساخت و ارسال بسته نیست" in page.text
    assert 'id="publishing-bundle" open' in page.text
    assert 'name="include_caption" value="1" checked' in page.text
    assert re.search(r'name="include_image"[^>]*disabled', page.text)
    assert re.search(r'name="include_voice"[^>]*disabled', page.text)


def test_automatic_workflow_points_directly_to_final_bundle(
    authenticated_client, csrf_token, product, png_upload
):
    relative_path = f"products/{product.id}/original/workflow.png"
    image_path = authenticated_client.app.state.settings.upload_dir / relative_path
    image_path.parent.mkdir(parents=True, exist_ok=True)
    image_path.write_bytes(png_upload)
    with authenticated_client.app.state.session_factory() as session:
        stored_product = session.get(type(product), product.id)
        stored_product.primary_image_path = relative_path
        session.commit()
    draft_id = generate_content(authenticated_client, csrf_token, product.id)
    authenticated_client.post(
        "/admin/publishing/mode",
        data={"csrf_token": csrf_token, "mode": "automatic"},
    )

    page = authenticated_client.get(f"/admin/content/{draft_id}")

    assert 'data-workflow-current="bundle"' in page.text
    assert "تأیید خودکار" in page.text
    assert "ساخت بسته نهایی" in page.text
    assert 'id="publishing-bundle" open' in page.text


def test_approval_reports_success_and_removes_actions_that_no_longer_apply(
    authenticated_client, csrf_token, product
):
    draft_id = generate_content(authenticated_client, csrf_token, product.id)

    waiting = authenticated_client.get(f"/admin/content/{draft_id}")
    assert f'action="/admin/content/{draft_id}/approve"' in waiting.text

    approved = authenticated_client.post(
        f"/admin/content/{draft_id}/approve",
        data={"csrf_token": csrf_token},
        follow_redirects=False,
    )
    assert approved.status_code == 303
    assert approved.headers["location"] == (f"/admin/content/{draft_id}?approved=1#caption-studio")

    page = authenticated_client.get(approved.headers["location"])
    assert "متن تأیید شد و برای ساخت بسته نهایی آماده است" in page.text
    assert 'data-toast="success"' in page.text
    assert f'action="/admin/content/{draft_id}/approve"' not in page.text
    assert f'action="/admin/content/{draft_id}/edit"' not in page.text
    assert f'action="/admin/content/{draft_id}/reject"' not in page.text
    assert "این نسخه تأیید و قفل شده است" in page.text


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
    assert 'src="/static/js/voice-recorder.js?v=20260831b"' in page.text
    assert 'type="file" name="voice"' in page.text
    assert 'type="file" name="voice" hidden' in page.text
    assert "فایل وویس" not in page.text
    assert "یک فایل صوتی انتخاب کنید" not in page.text


def test_unsaved_recording_is_clearly_excluded_from_final_bundle(
    authenticated_client, csrf_token, product
):
    draft_id = generate_content(authenticated_client, csrf_token, product.id)

    page = authenticated_client.get(f"/admin/content/{draft_id}")

    assert "این ضبط هنوز ذخیره نشده و به بسته نهایی اضافه نمی‌شود" in page.text
    assert "ذخیره و پیوست وویس" in page.text
    assert "نادیده گرفتن ضبط" in page.text
    assert "data-record-unsaved" in page.text
    assert "data-record-discard" in page.text
    assert "data-bundle-create" in page.text


def test_image_studio_explains_color_preservation_and_separates_text_phase(
    authenticated_client, csrf_token, product, png_upload
):
    relative_path = f"products/{product.id}/original/source.png"
    image_path = authenticated_client.app.state.settings.upload_dir / relative_path
    image_path.parent.mkdir(parents=True, exist_ok=True)
    image_path.write_bytes(png_upload)
    with authenticated_client.app.state.session_factory() as session:
        stored_product = session.get(type(product), product.id)
        stored_product.primary_image_path = relative_path
        session.commit()
    authenticated_client.app.state.image_editor = object()
    draft_id = generate_content(authenticated_client, csrf_token, product.id)

    page = authenticated_client.get(f"/admin/content/{draft_id}")

    assert 'id="image-studio"' in page.text
    assert "ویرایش تصویر محصول" in page.text
    assert "حفظ رنگ واقعی محصول" in page.text
    assert "هوشمند بر اساس رنگ محصول" in page.text
    assert 'name="image_mode"' in page.text
    assert 'value="studio"' in page.text
    assert 'value="cinematic"' in page.text
    assert 'name="overlay_text"' in page.text
    assert 'name="topic"' in page.text
    assert 'name="message"' in page.text
    assert "حالت استودیویی با متن" in page.text
    assert "حالت سینمایی" in page.text
    assert "فقط محیط اطراف تغییر می‌کند" in page.text
    assert "data-image-mode-fields" in page.text
    assert f'action="/admin/content/{draft_id}/image/generate"' in page.text
    assert 'data-long-running-form="image-generation"' in page.text
    assert "ممکن است تا حدود ۲ دقیقه زمان ببرد" in page.text
    assert "در حال ساخت نسخه استودیویی" in page.text
    assert page.text.count("data-image-lightbox") == 1
    assert "مشاهده کامل تصویر اصلی" in page.text
