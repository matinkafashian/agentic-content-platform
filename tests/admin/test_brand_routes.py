def test_brand_page_redirects_anonymous_user(client):
    response = client.get("/admin/brand", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/admin/login"


def test_brand_page_shows_safe_hayka_defaults(authenticated_client):
    response = authenticated_client.get("/admin/brand")

    assert response.status_code == 200
    assert "هایکا" in response.text
    assert "@hayka_poshtibani" in response.text
    assert "۱۸ ماه" not in response.text


def test_admin_updates_brand_profile(authenticated_client, csrf_token):
    response = authenticated_client.post(
        "/admin/brand",
        data={
            "csrf_token": csrf_token,
            "business_name": "هایکا",
            "tagline": "هر قطعه چوب، یک اثر",
            "audience": "کابینت‌سازان حرفه‌ای",
            "tone_guidelines": "تخصصی، حرفه‌ای و محترمانه",
            "support_handle": "hayka_poshtibani",
            "default_cta": "برای ثبت سفارش پیام دهید.",
            "approved_claim": ["ارسال رایگان به سراسر ایران"],
            "default_hashtag": ["#هایکا", "درب ممبران"],
        },
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/admin/brand"
    page = authenticated_client.get("/admin/brand")
    assert "هر قطعه چوب، یک اثر" in page.text
    assert "@hayka_poshtibani" in page.text


def test_brand_update_rejects_missing_csrf(authenticated_client):
    response = authenticated_client.post(
        "/admin/brand",
        data={"business_name": "هایکا", "support_handle": "hayka_poshtibani"},
    )

    assert response.status_code == 403

