import re


def product_form(csrf_token: str, **overrides) -> dict[str, str]:
    values = {
        "csrf_token": csrf_token,
        "name": "میز کانتر",
        "description": "طراحی منحنی",
        "price": "25000000",
        "availability": "available",
        "shipping_info": "ارسال سراسر ایران",
        "tags": "کانتر، دکوراسیون",
        "active": "true",
    }
    values.update(overrides)
    return values


def create_product(client, csrf_token: str, image: bytes):
    return client.post(
        "/admin/products",
        data=product_form(csrf_token),
        files={"image": ("counter.png", image, "image/png")},
        follow_redirects=False,
    )


def test_product_pages_redirect_anonymous_user(client):
    response = client.get("/admin/products", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/admin/login"


def test_admin_creates_product_with_real_image(
    authenticated_client, csrf_token, png_upload
):
    response = create_product(authenticated_client, csrf_token, png_upload)

    assert response.status_code == 303
    assert response.headers["location"].startswith("/admin/products/")
    detail = authenticated_client.get(response.headers["location"])
    assert "میز کانتر" in detail.text
    assert "۲۵٬۰۰۰٬۰۰۰" in detail.text
    assert "counter.png" not in detail.text
    image = re.search(
        r'src="(/uploads/products/\d+/original/[a-f0-9]{32}\.png)"', detail.text
    )
    assert image is not None
    image_response = authenticated_client.get(image.group(1))
    assert image_response.status_code == 200
    assert image_response.headers["content-type"] == "image/png"
    assert image_response.content == png_upload


def test_invalid_price_returns_feedback_without_creating_product(
    authenticated_client, csrf_token, png_upload
):
    response = authenticated_client.post(
        "/admin/products",
        data=product_form(csrf_token, price="-1"),
        files={"image": ("counter.png", png_upload, "image/png")},
    )

    assert response.status_code == 422
    assert "قیمت" in response.text
    assert "میز کانتر" not in authenticated_client.get("/admin/products").text


def test_invalid_image_does_not_create_product(authenticated_client, csrf_token):
    response = authenticated_client.post(
        "/admin/products",
        data=product_form(csrf_token),
        files={"image": ("counter.png", b"not-an-image", "image/png")},
    )

    assert response.status_code == 422
    assert "ساختار تصویر معتبر نیست" in response.text
    assert "میز کانتر" not in authenticated_client.get("/admin/products").text


def test_create_product_rejects_missing_csrf(authenticated_client, png_upload):
    response = authenticated_client.post(
        "/admin/products",
        data=product_form(""),
        files={"image": ("counter.png", png_upload, "image/png")},
    )

    assert response.status_code == 403


def test_edit_without_new_upload_preserves_existing_image(
    authenticated_client, csrf_token, png_upload
):
    created = create_product(authenticated_client, csrf_token, png_upload)
    detail_url = created.headers["location"]
    before = authenticated_client.get(detail_url).text
    image_url = re.search(r'src="(/uploads/products/[^"]+)"', before)
    assert image_url is not None

    response = authenticated_client.post(
        detail_url,
        data=product_form(csrf_token, name="میز کانتر ویرایش‌شده"),
        follow_redirects=False,
    )

    assert response.status_code == 303
    after = authenticated_client.get(detail_url).text
    assert "میز کانتر ویرایش‌شده" in after
    assert image_url.group(1) in after


def test_storage_failure_removes_incomplete_product(
    authenticated_client, csrf_token, png_upload, monkeypatch
):
    def fail_storage(*args, **kwargs):
        raise OSError("private filesystem detail")

    monkeypatch.setattr("app.catalog.routes.save_product_image", fail_storage)
    response = create_product(authenticated_client, csrf_token, png_upload)

    assert response.status_code == 500
    assert "ذخیره تصویر انجام نشد" in response.text
    assert "private filesystem detail" not in response.text
    assert "میز کانتر" not in authenticated_client.get("/admin/products").text
