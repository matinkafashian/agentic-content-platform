import re
from io import BytesIO

from PIL import Image

from app.content.openai_provider import ContentProviderUnavailable


class UnavailableContentProvider:
    name = "openai:gpt-test-model"

    def generate(self, request):
        raise ContentProviderUnavailable(
            "سرویس OpenAI موقتاً در دسترس نیست؛ دوباره تلاش کنید."
        )


class SuccessfulImageEditor:
    name = "openai:gpt-image-2"

    def edit(self, *, source, filename, mime_type, background_style):
        from app.media.images import validate_image

        output = BytesIO()
        Image.new("RGB", (64, 64), "teal").save(output, format="PNG")
        return validate_image(output.getvalue(), "edited.png", "image/png")


def generate_content(client, csrf_token: str, product_id: int):
    return client.post(
        "/admin/content",
        data={
            "csrf_token": csrf_token,
            "product_id": str(product_id),
            "user_brief": "این مدل برای پروژه نئوکلاسیک معرفی شود و مشخصات واقعی برجسته شود.",
            "requested_angle": "product_intro",
        },
        follow_redirects=False,
    )


def draft_id_from(response) -> int:
    match = re.fullmatch(r"/admin/content/(\d+)", response.headers["location"])
    assert match is not None
    return int(match.group(1))


def test_content_pages_redirect_anonymous_user(client):
    response = client.get("/admin/content/new", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/admin/login"


def test_admin_generates_content_from_short_brief(
    authenticated_client, csrf_token, product
):
    original_description = product.description

    response = generate_content(authenticated_client, csrf_token, product.id)

    assert response.status_code == 303
    preview = authenticated_client.get(response.headers["location"])
    assert preview.status_code == 200
    assert "حالت آزمایشی — بدون OpenAI" in preview.text
    assert "@hayka_poshtibani" in preview.text
    assert "#درب_ممبران" in preview.text
    assert product.description == original_description


def test_admin_edits_regenerates_and_approves_content(
    authenticated_client, csrf_token, product
):
    created = generate_content(authenticated_client, csrf_token, product.id)
    first_id = draft_id_from(created)

    edited = authenticated_client.post(
        f"/admin/content/{first_id}/edit",
        data={
            "csrf_token": csrf_token,
            "final_caption": "این کپشن ویرایش‌شده برای تست جریان تأیید محتوا کافی است.",
        },
        follow_redirects=False,
    )
    regenerated = authenticated_client.post(
        f"/admin/content/{first_id}/regenerate",
        data={"csrf_token": csrf_token},
        follow_redirects=False,
    )
    second_id = draft_id_from(regenerated)
    approved = authenticated_client.post(
        f"/admin/content/{second_id}/approve",
        data={"csrf_token": csrf_token},
        follow_redirects=False,
    )

    assert edited.status_code == 303
    assert second_id != first_id
    assert approved.status_code == 303
    assert "تأییدشده" in authenticated_client.get(
        f"/admin/content/{second_id}"
    ).text


def test_admin_rejects_content_and_cannot_approve_it(
    authenticated_client, csrf_token, product
):
    created = generate_content(authenticated_client, csrf_token, product.id)
    draft_id = draft_id_from(created)

    rejected = authenticated_client.post(
        f"/admin/content/{draft_id}/reject",
        data={"csrf_token": csrf_token},
        follow_redirects=False,
    )
    invalid_approval = authenticated_client.post(
        f"/admin/content/{draft_id}/approve",
        data={"csrf_token": csrf_token},
    )

    assert rejected.status_code == 303
    assert invalid_approval.status_code == 422


def test_content_generation_rejects_missing_csrf(authenticated_client, product):
    response = authenticated_client.post(
        "/admin/content",
        data={
            "product_id": str(product.id),
            "user_brief": "این متن بدون توکن امنیتی نباید پذیرفته شود.",
            "requested_angle": "product_intro",
        },
    )

    assert response.status_code == 403


def test_openai_failure_returns_safe_feedback_without_creating_draft(
    authenticated_client, csrf_token, product
):
    authenticated_client.app.state.content_provider = UnavailableContentProvider()

    response = generate_content(authenticated_client, csrf_token, product.id)

    assert response.status_code == 503
    assert "OpenAI موقتاً در دسترس نیست" in response.text
    assert "sk-" not in response.text


def test_voice_upload_is_private_and_byte_identical(
    authenticated_client, csrf_token, product
):
    created = generate_content(authenticated_client, csrf_token, product.id)
    draft_id = draft_id_from(created)
    voice = b"\x1aE\xdf\xa3recorded" + b"\x00" * 24

    uploaded = authenticated_client.post(
        f"/admin/content/{draft_id}/voice",
        data={"csrf_token": csrf_token, "duration_ms": "1500"},
        files={"voice": ("recording.webm", voice, "audio/webm;codecs=opus")},
        follow_redirects=False,
    )
    private_response = authenticated_client.get(
        f"/admin/content/{draft_id}/voice"
    )

    assert uploaded.status_code == 303
    assert uploaded.headers["location"] == (
        f"/admin/content/{draft_id}?voice_saved=1#voice-studio"
    )
    assert private_response.status_code == 200
    assert private_response.content == voice
    assert private_response.headers["content-type"].startswith("audio/webm")
    assert "/uploads/" not in authenticated_client.get(
        f"/admin/content/{draft_id}"
    ).text

    saved_page = authenticated_client.get(
        f"/admin/content/{draft_id}?voice_saved=1"
    )
    assert "وویس با موفقیت ذخیره شد" in saved_page.text
    assert f'href="/admin/content/{draft_id}/voice?download=true"' in saved_page.text

    download = authenticated_client.get(
        f"/admin/content/{draft_id}/voice?download=true"
    )
    assert download.content == voice
    assert download.headers["content-disposition"].startswith(
        f'attachment; filename="voice-{draft_id}.webm"'
    )


def test_private_voice_redirects_anonymous_user(
    client, authenticated_client, csrf_token, product
):
    created = generate_content(authenticated_client, csrf_token, product.id)
    draft_id = draft_id_from(created)
    client.cookies.clear()

    response = client.get(f"/admin/content/{draft_id}/voice", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/admin/login"


def test_admin_generates_private_edited_image_without_changing_original(
    authenticated_client, csrf_token, product, png_upload
):
    upload_root = authenticated_client.app.state.settings.upload_dir
    original_relative = f"products/{product.id}/original/source.png"
    original_path = upload_root / original_relative
    original_path.parent.mkdir(parents=True, exist_ok=True)
    original_path.write_bytes(png_upload)
    with authenticated_client.app.state.session_factory() as session:
        stored_product = session.get(type(product), product.id)
        stored_product.primary_image_path = original_relative
        session.commit()
    created = generate_content(authenticated_client, csrf_token, product.id)
    draft_id = draft_id_from(created)
    authenticated_client.app.state.image_editor = SuccessfulImageEditor()

    generated = authenticated_client.post(
        f"/admin/content/{draft_id}/image/generate",
        data={"csrf_token": csrf_token, "background_style": "adaptive_studio"},
        follow_redirects=False,
    )
    preview = authenticated_client.get(f"/admin/content/{draft_id}/image")

    assert generated.status_code == 303
    assert generated.headers["location"] == (
        f"/admin/content/{draft_id}?image_saved=1#image-studio"
    )
    assert preview.status_code == 200
    assert preview.headers["content-type"] == "image/png"
    assert preview.content != png_upload
    assert original_path.read_bytes() == png_upload


def test_edited_image_requires_admin_session(
    client, authenticated_client, csrf_token, product, png_upload
):
    upload_root = authenticated_client.app.state.settings.upload_dir
    original_relative = f"products/{product.id}/original/source.png"
    original_path = upload_root / original_relative
    original_path.parent.mkdir(parents=True, exist_ok=True)
    original_path.write_bytes(png_upload)
    with authenticated_client.app.state.session_factory() as session:
        stored_product = session.get(type(product), product.id)
        stored_product.primary_image_path = original_relative
        session.commit()
    draft_id = draft_id_from(
        generate_content(authenticated_client, csrf_token, product.id)
    )
    authenticated_client.app.state.image_editor = SuccessfulImageEditor()
    authenticated_client.post(
        f"/admin/content/{draft_id}/image/generate",
        data={"csrf_token": csrf_token, "background_style": "adaptive_studio"},
    )
    client.cookies.clear()

    response = client.get(
        f"/admin/content/{draft_id}/image", follow_redirects=False
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/admin/login"


def test_image_generation_returns_not_found_for_unknown_draft(
    authenticated_client, csrf_token
):
    authenticated_client.app.state.image_editor = SuccessfulImageEditor()

    response = authenticated_client.post(
        "/admin/content/99999/image/generate",
        data={"csrf_token": csrf_token, "background_style": "adaptive_studio"},
    )

    assert response.status_code == 404
