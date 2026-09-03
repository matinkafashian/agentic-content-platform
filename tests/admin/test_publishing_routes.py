import re
from datetime import UTC, datetime, timedelta
from io import BytesIO

from PIL import Image
from sqlalchemy import select

from app.content.models import ContentDraft, DraftStatus
from app.publishing.adapters import DeliveryResult
from app.publishing.models import Publication


class SuccessfulImageEditor:
    name = "openai:gpt-image-2"

    def edit(self, *, source, filename, mime_type, background_style, **instructions):
        from app.media.images import validate_image

        output = BytesIO()
        Image.new("RGB", (64, 64), "teal").save(output, format="PNG")
        return validate_image(output.getvalue(), "edited.png", "image/png")


class SuccessfulTelegramAdapter:
    platform = "telegram"

    def __init__(self):
        self.send_count = 0

    def send(self, bundle, destination, idempotency_key):
        self.send_count += 1
        return DeliveryResult.success(["telegram-test-message"])


class SuccessfulBaleAdapter:
    platform = "bale"

    def send(self, bundle, destination, idempotency_key):
        return DeliveryResult.success(["bale-test-message"])


class SuccessfulRubikaAdapter:
    platform = "rubika"

    def send(self, bundle, destination, idempotency_key):
        return DeliveryResult.success(["rubika-test-message"])


class SuccessfulWhatsAppAdapter:
    platform = "whatsapp"

    def send(self, bundle, destination, idempotency_key):
        return DeliveryResult.success(["whatsapp-test-message"])


class FailedBaleAdapter:
    platform = "bale"

    def send(self, bundle, destination, idempotency_key):
        return DeliveryResult.failure(
            code="bale_forbidden",
            message="ارسال بله انجام نشد؛ دسترسی ربات به کانال را بررسی کنید",
            retryable=False,
        )


def _draft_id(client, csrf_token, product):
    response = client.post(
        "/admin/content",
        data={
            "csrf_token": csrf_token,
            "product_id": product.id,
            "content_mode": "ai",
            "ai_brief": "برای ساخت بسته نهایی یک معرفی دقیق و حرفه‌ای آماده شود.",
            "manual_caption": "",
            "requested_angle": "product_intro",
        },
        follow_redirects=False,
    )
    match = re.fullmatch(r"/admin/content/(\d+)", response.headers["location"])
    assert match
    return int(match.group(1))


def _set_product_image(client, product, png_upload):
    relative = f"products/{product.id}/original/source.png"
    path = client.app.state.settings.upload_dir / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(png_upload)
    with client.app.state.session_factory() as session:
        stored = session.get(type(product), product.id)
        stored.primary_image_path = relative
        session.commit()


def test_admin_can_prepare_bundle_schedule_and_run_sandbox_delivery(
    authenticated_client, csrf_token, product, png_upload
):
    _set_product_image(authenticated_client, product, png_upload)
    draft_id = _draft_id(authenticated_client, csrf_token, product)
    authenticated_client.post(
        f"/admin/content/{draft_id}/approve",
        data={"csrf_token": csrf_token},
    )

    created = authenticated_client.post(
        f"/admin/content/{draft_id}/bundle",
        data={"csrf_token": csrf_token},
        follow_redirects=False,
    )
    assert created.status_code == 303
    page = authenticated_client.get(f"/admin/content/{draft_id}")
    assert "بسته نهایی آماده است" in page.text
    assert 'class="schedule-form aligned-control-grid"' in page.text
    bundle_match = re.search(r'action="/admin/publishing/bundles/(\d+)/schedule"', page.text)
    assert bundle_match

    scheduled = authenticated_client.post(
        f"/admin/publishing/bundles/{bundle_match.group(1)}/schedule",
        data={
            "csrf_token": csrf_token,
            "destination": "کانال آزمایشی",
            "scheduled_for": (
                datetime.now(UTC) - timedelta(minutes=1)
            ).strftime("%Y-%m-%dT%H:%M"),
        },
        follow_redirects=False,
    )
    assert scheduled.status_code == 303, scheduled.text

    run = authenticated_client.post(
        "/admin/publishing/run-due",
        data={"csrf_token": csrf_token},
        follow_redirects=False,
    )
    assert run.status_code == 303
    queue = authenticated_client.get("/admin/publishing")
    assert "موفق" in queue.text
    assert "کانال آزمایشی" in queue.text
    assert "شبیه‌ساز داخلی" in queue.text


def test_automatic_mode_can_package_waiting_draft(
    authenticated_client, csrf_token, product, png_upload
):
    _set_product_image(authenticated_client, product, png_upload)
    draft_id = _draft_id(authenticated_client, csrf_token, product)
    changed = authenticated_client.post(
        "/admin/publishing/mode",
        data={"csrf_token": csrf_token, "mode": "automatic"},
        follow_redirects=False,
    )
    assert changed.status_code == 303

    bundled = authenticated_client.post(
        f"/admin/content/{draft_id}/bundle",
        data={"csrf_token": csrf_token},
        follow_redirects=False,
    )

    assert bundled.status_code == 303
    with authenticated_client.app.state.session_factory() as session:
        assert session.get(ContentDraft, draft_id).status == DraftStatus.APPROVED.value


def test_automatic_mode_generates_required_studio_image_before_bundle(
    authenticated_client, csrf_token, product, png_upload
):
    _set_product_image(authenticated_client, product, png_upload)
    draft_id = _draft_id(authenticated_client, csrf_token, product)
    authenticated_client.app.state.image_editor = SuccessfulImageEditor()
    authenticated_client.post(
        "/admin/publishing/mode",
        data={"csrf_token": csrf_token, "mode": "automatic"},
    )

    response = authenticated_client.post(
        f"/admin/content/{draft_id}/bundle",
        data={"csrf_token": csrf_token},
        follow_redirects=False,
    )

    assert response.status_code == 303
    image = authenticated_client.get(f"/admin/content/{draft_id}/image")
    assert image.status_code == 200
    assert image.content != png_upload


def test_manual_mode_requires_studio_image_when_openai_editor_is_available(
    authenticated_client, csrf_token, product, png_upload
):
    _set_product_image(authenticated_client, product, png_upload)
    draft_id = _draft_id(authenticated_client, csrf_token, product)
    authenticated_client.app.state.image_editor = SuccessfulImageEditor()
    authenticated_client.post(
        f"/admin/content/{draft_id}/approve",
        data={"csrf_token": csrf_token},
    )

    response = authenticated_client.post(
        f"/admin/content/{draft_id}/bundle",
        data={"csrf_token": csrf_token},
    )

    assert response.status_code == 422
    assert "نسخه استودیویی" in response.text


def test_paused_mode_prevents_manual_run(
    authenticated_client, csrf_token
):
    authenticated_client.post(
        "/admin/publishing/mode",
        data={"csrf_token": csrf_token, "mode": "paused"},
    )

    response = authenticated_client.post(
        "/admin/publishing/run-due",
        data={"csrf_token": csrf_token},
        follow_redirects=False,
    )

    assert response.status_code == 303
    page = authenticated_client.get("/admin/publishing?paused=1")
    assert "انتشار متوقف است" in page.text


def test_publishing_routes_require_authentication(client):
    response = client.get("/admin/publishing", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/admin/login"


def test_admin_can_choose_telegram_channel_when_adapter_is_configured(
    authenticated_client, csrf_token, product, png_upload
):
    authenticated_client.app.state.platform_adapters["telegram"] = (
        SuccessfulTelegramAdapter()
    )
    authenticated_client.app.state.telegram_default_destination = "@test_channel"
    _set_product_image(authenticated_client, product, png_upload)
    draft_id = _draft_id(authenticated_client, csrf_token, product)
    authenticated_client.post(
        f"/admin/content/{draft_id}/approve",
        data={"csrf_token": csrf_token},
    )
    authenticated_client.post(
        f"/admin/content/{draft_id}/bundle",
        data={"csrf_token": csrf_token},
    )
    page = authenticated_client.get(f"/admin/content/{draft_id}")
    bundle_id = re.search(
        r'action="/admin/publishing/bundles/(\d+)/schedule"', page.text
    ).group(1)

    assert '<option value="telegram" selected>تلگرام</option>' in page.text
    assert 'value="@test_channel"' in page.text
    stylesheet = authenticated_client.get("/static/css/app.css")
    assert "grid-template-columns: repeat(3, minmax(0, 1fr)) auto" in stylesheet.text
    assert "align-items: start" in stylesheet.text
    assert 'class="schedule-submit"' in page.text

    response = authenticated_client.post(
        f"/admin/publishing/bundles/{bundle_id}/schedule",
        data={
            "csrf_token": csrf_token,
            "platform": "telegram",
            "destination": "@test_channel",
            "scheduled_for": (
                datetime.now(UTC) + timedelta(hours=1)
            ).strftime("%Y-%m-%dT%H:%M"),
        },
        follow_redirects=False,
    )

    assert response.status_code == 303
    feedback = authenticated_client.get(response.headers["location"])
    assert "هنوز ارسال نشده است" in feedback.text
    assert 'class="alert alert-warning"' in feedback.text
    with authenticated_client.app.state.session_factory() as session:
        publication = session.scalar(select(Publication))
        assert publication.platform == "telegram"
        assert publication.destination == "@test_channel"


def test_publishing_page_distinguishes_real_telegram_from_sandbox(
    authenticated_client,
):
    authenticated_client.app.state.platform_adapters["telegram"] = (
        SuccessfulTelegramAdapter()
    )

    page = authenticated_client.get("/admin/publishing")

    assert "اتصال واقعی تلگرام فعال است" in page.text
    assert "ارسال آزمایشی بدون شبکه نیز در دسترس می‌ماند" in page.text


def test_admin_can_send_bundle_now_to_configured_bale_channel(
    authenticated_client, csrf_token, product, png_upload
):
    authenticated_client.app.state.platform_adapters["bale"] = (
        SuccessfulBaleAdapter()
    )
    authenticated_client.app.state.platform_default_destinations["bale"] = (
        "@bale_test_channel"
    )
    _set_product_image(authenticated_client, product, png_upload)
    draft_id = _draft_id(authenticated_client, csrf_token, product)
    authenticated_client.post(
        f"/admin/content/{draft_id}/approve",
        data={"csrf_token": csrf_token},
    )
    authenticated_client.post(
        f"/admin/content/{draft_id}/bundle",
        data={"csrf_token": csrf_token},
    )
    page = authenticated_client.get(f"/admin/content/{draft_id}")
    bundle_id = re.search(
        r'action="/admin/publishing/bundles/(\d+)/schedule"', page.text
    ).group(1)

    assert re.search(r'<option value="bale"[^>]*>بله</option>', page.text)
    assert "@bale_test_channel" in page.text

    response = authenticated_client.post(
        f"/admin/publishing/bundles/{bundle_id}/schedule",
        data={
            "csrf_token": csrf_token,
            "platform": "bale",
            "destination": "@bale_test_channel",
            "delivery_action": "send_now",
            "scheduled_for": "",
        },
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert "sent=" in response.headers["location"]
    with authenticated_client.app.state.session_factory() as session:
        publication = session.scalar(select(Publication))
        assert publication.platform == "bale"
        assert publication.destination == "@bale_test_channel"
        assert publication.status == "succeeded"


def test_send_now_delivers_selected_bundle_immediately(
    authenticated_client, csrf_token, product, png_upload
):
    authenticated_client.app.state.platform_adapters["telegram"] = (
        SuccessfulTelegramAdapter()
    )
    _set_product_image(authenticated_client, product, png_upload)
    draft_id = _draft_id(authenticated_client, csrf_token, product)
    authenticated_client.post(
        f"/admin/content/{draft_id}/approve",
        data={"csrf_token": csrf_token},
    )
    authenticated_client.post(
        f"/admin/content/{draft_id}/bundle",
        data={"csrf_token": csrf_token},
    )
    page = authenticated_client.get(f"/admin/content/{draft_id}")
    bundle_id = re.search(
        r'action="/admin/publishing/bundles/(\d+)/schedule"', page.text
    ).group(1)

    response = authenticated_client.post(
        f"/admin/publishing/bundles/{bundle_id}/schedule",
        data={
            "csrf_token": csrf_token,
            "platform": "telegram",
            "destination": "@test_channel",
            "delivery_action": "send_now",
            "scheduled_for": "",
        },
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert "sent=" in response.headers["location"]
    feedback = authenticated_client.get(response.headers["location"])
    assert "با موفقیت ارسال شد" in feedback.text
    with authenticated_client.app.state.session_factory() as session:
        publication = session.scalar(select(Publication))
        assert publication.status == "succeeded"
        assert publication.attempt_count == 1


def test_repeated_send_now_request_does_not_deliver_the_same_bundle_twice(
    authenticated_client, csrf_token, product, png_upload
):
    adapter = SuccessfulTelegramAdapter()
    authenticated_client.app.state.platform_adapters["telegram"] = adapter
    _set_product_image(authenticated_client, product, png_upload)
    draft_id = _draft_id(authenticated_client, csrf_token, product)
    authenticated_client.post(
        f"/admin/content/{draft_id}/approve",
        data={"csrf_token": csrf_token},
    )
    authenticated_client.post(
        f"/admin/content/{draft_id}/bundle",
        data={"csrf_token": csrf_token},
    )
    page = authenticated_client.get(f"/admin/content/{draft_id}")
    bundle_id = re.search(
        r'action="/admin/publishing/bundles/(\d+)/schedule"', page.text
    ).group(1)
    form = {
        "csrf_token": csrf_token,
        "platform": "telegram",
        "destination": "@test_channel",
        "delivery_action": "send_now",
        "scheduled_for": "",
    }

    first = authenticated_client.post(
        f"/admin/publishing/bundles/{bundle_id}/schedule",
        data=form,
        follow_redirects=False,
    )
    repeated = authenticated_client.post(
        f"/admin/publishing/bundles/{bundle_id}/schedule",
        data=form,
        follow_redirects=False,
    )

    assert first.status_code == 303
    assert repeated.status_code == 303
    assert adapter.send_count == 1
    with authenticated_client.app.state.session_factory() as session:
        publications = list(session.scalars(select(Publication)))
        assert len(publications) == 1
        assert publications[0].status == "succeeded"


def test_send_to_all_active_platforms_reports_each_result_independently(
    authenticated_client, csrf_token, product, png_upload
):
    authenticated_client.app.state.platform_adapters.update(
        {
            "telegram": SuccessfulTelegramAdapter(),
            "bale": FailedBaleAdapter(),
        }
    )
    authenticated_client.app.state.platform_default_destinations.update(
        {
            "telegram": "@telegram_channel",
            "bale": "@bale_channel",
        }
    )
    authenticated_client.app.state.telegram_default_destination = (
        "@telegram_channel"
    )
    _set_product_image(authenticated_client, product, png_upload)
    draft_id = _draft_id(authenticated_client, csrf_token, product)
    authenticated_client.post(
        f"/admin/content/{draft_id}/approve",
        data={"csrf_token": csrf_token},
    )
    authenticated_client.post(
        f"/admin/content/{draft_id}/bundle",
        data={"csrf_token": csrf_token},
    )
    page = authenticated_client.get(f"/admin/content/{draft_id}")
    bundle_id = re.search(
        r'action="/admin/publishing/bundles/(\d+)/schedule"', page.text
    ).group(1)

    response = authenticated_client.post(
        f"/admin/publishing/bundles/{bundle_id}/schedule",
        data={
            "csrf_token": csrf_token,
            "platform": "all",
            "delivery_action": "send_now",
            "scheduled_for": "",
        },
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert "multi_sent=1" in response.headers["location"]
    assert "multi_failed=bale" in response.headers["location"]
    feedback = authenticated_client.get(response.headers["location"])
    assert "تلگرام با موفقیت ارسال شد" in feedback.text
    assert "ارسال بله انجام نشد" in feedback.text
    with authenticated_client.app.state.session_factory() as session:
        publications = list(
            session.scalars(select(Publication).order_by(Publication.id))
        )
        assert [item.platform for item in publications] == ["telegram", "bale"]
        assert [item.status for item in publications] == ["succeeded", "failed"]


def test_content_page_defaults_to_all_active_channels_with_advanced_single_send(
    authenticated_client, csrf_token, product, png_upload
):
    authenticated_client.app.state.platform_adapters.update(
        {
            "telegram": SuccessfulTelegramAdapter(),
            "bale": SuccessfulBaleAdapter(),
        }
    )
    authenticated_client.app.state.platform_default_destinations.update(
        {
            "telegram": "@telegram_channel",
            "bale": "@bale_channel",
        }
    )
    authenticated_client.app.state.telegram_default_destination = (
        "@telegram_channel"
    )
    _set_product_image(authenticated_client, product, png_upload)
    draft_id = _draft_id(authenticated_client, csrf_token, product)
    authenticated_client.post(
        f"/admin/content/{draft_id}/approve",
        data={"csrf_token": csrf_token},
    )
    authenticated_client.post(
        f"/admin/content/{draft_id}/bundle",
        data={"csrf_token": csrf_token},
    )

    page = authenticated_client.get(f"/admin/content/{draft_id}")

    assert "ارسال همین حالا به همه کانال‌های فعال" in page.text
    assert "تلگرام" in page.text and "@telegram_channel" in page.text
    assert "بله" in page.text and "@bale_channel" in page.text
    assert 'name="platform" value="all"' in page.text
    assert "تنظیمات پیشرفته: ارسال به یک پلتفرم" in page.text


def test_content_page_includes_configured_rubika_in_all_channels(
    authenticated_client, csrf_token, product, png_upload
):
    authenticated_client.app.state.platform_adapters["rubika"] = (
        SuccessfulRubikaAdapter()
    )
    authenticated_client.app.state.platform_default_destinations["rubika"] = (
        "rubika-channel-chat-id"
    )
    _set_product_image(authenticated_client, product, png_upload)
    draft_id = _draft_id(authenticated_client, csrf_token, product)
    authenticated_client.post(
        f"/admin/content/{draft_id}/approve",
        data={"csrf_token": csrf_token},
    )
    authenticated_client.post(
        f"/admin/content/{draft_id}/bundle",
        data={"csrf_token": csrf_token},
    )

    page = authenticated_client.get(f"/admin/content/{draft_id}")

    assert "روبیکا" in page.text
    assert "rubika-channel-chat-id" in page.text
    assert 'name="platform" value="all"' in page.text


def test_content_page_includes_configured_whatsapp_in_all_channels(
    authenticated_client, csrf_token, product, png_upload
):
    authenticated_client.app.state.platform_adapters["whatsapp"] = (
        SuccessfulWhatsAppAdapter()
    )
    authenticated_client.app.state.platform_default_destinations["whatsapp"] = (
        "120363123456789@g.us"
    )
    _set_product_image(authenticated_client, product, png_upload)
    draft_id = _draft_id(authenticated_client, csrf_token, product)
    authenticated_client.post(
        f"/admin/content/{draft_id}/approve",
        data={"csrf_token": csrf_token},
    )
    authenticated_client.post(
        f"/admin/content/{draft_id}/bundle",
        data={"csrf_token": csrf_token},
    )

    page = authenticated_client.get(f"/admin/content/{draft_id}")

    assert "واتساپ" in page.text
    assert "120363123456789@g.us" in page.text
    assert 'name="platform" value="all"' in page.text


def test_publishing_ui_has_one_clear_immediate_action_and_optional_schedule(
    authenticated_client, csrf_token, product, png_upload
):
    _set_product_image(authenticated_client, product, png_upload)
    draft_id = _draft_id(authenticated_client, csrf_token, product)
    authenticated_client.post(
        f"/admin/content/{draft_id}/approve",
        data={"csrf_token": csrf_token},
    )
    authenticated_client.post(
        f"/admin/content/{draft_id}/bundle",
        data={"csrf_token": csrf_token},
    )

    detail = authenticated_client.get(f"/admin/content/{draft_id}")
    publishing = authenticated_client.get("/admin/publishing")

    assert "ارسال همین حالا" in detail.text
    assert "ارسال در زمان دیگر" in detail.text
    assert "زمان‌بندی ارسال" in detail.text
    assert "ثبت در صف انتشار" not in detail.text
    assert "روش تأیید محتوا" in publishing.text
    assert "اعمال روش تأیید" in publishing.text
    assert "با تغییر این گزینه هیچ پستی ارسال نمی‌شود" in publishing.text
    assert "ذخیره حالت" not in publishing.text
    assert "بررسی همین حالا" not in publishing.text
