import re


def extract_csrf(html: str) -> str:
    match = re.search(r'name="csrf_token" value="([^"]+)"', html)
    assert match is not None, "CSRF field was not rendered"
    return match.group(1)


def login(client, password: str = "correct-password"):
    login_page = client.get("/admin/login")
    return client.post(
        "/admin/login",
        data={
            "username": "admin",
            "password": password,
            "csrf_token": extract_csrf(login_page.text),
        },
        follow_redirects=False,
    )


def test_dashboard_redirects_anonymous_user(client):
    response = client.get("/admin", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/admin/login"


def test_admin_can_login(client):
    response = login(client)

    assert response.status_code == 303
    assert response.headers["location"] == "/admin"
    dashboard = client.get("/admin")
    assert dashboard.status_code == 200
    assert '<main data-page="dashboard">' in dashboard.text


def test_login_rejects_missing_csrf(client):
    response = client.post(
        "/admin/login",
        data={"username": "admin", "password": "correct-password"},
    )

    assert response.status_code == 403


def test_login_returns_generic_error_for_invalid_credentials(client):
    bad_password = login(client, password="wrong-password")

    page = client.get("/admin/login")
    bad_username = client.post(
        "/admin/login",
        data={
            "username": "someone-else",
            "password": "correct-password",
            "csrf_token": extract_csrf(page.text),
        },
    )

    assert bad_password.status_code == 401
    assert bad_username.status_code == 401
    assert "نام کاربری یا رمز عبور صحیح نیست" in bad_password.text
    assert "نام کاربری یا رمز عبور صحیح نیست" in bad_username.text


def test_logout_requires_csrf_and_clears_session(client):
    assert login(client).status_code == 303

    rejected = client.post("/admin/logout")
    assert rejected.status_code == 403
    assert client.get("/admin").status_code == 200

    dashboard = client.get("/admin")
    response = client.post(
        "/admin/logout",
        data={"csrf_token": extract_csrf(dashboard.text)},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/admin/login"
    assert client.get("/admin", follow_redirects=False).status_code == 303
