import re
from datetime import UTC, datetime, timedelta

from app.content.models import ContentDraft, DraftStatus


def _draft_id(client, csrf_token, product):
    response = client.post(
        "/admin/content",
        data={
            "csrf_token": csrf_token,
            "product_id": product.id,
            "user_brief": "برای ساخت بسته نهایی یک معرفی دقیق و حرفه‌ای آماده شود.",
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
