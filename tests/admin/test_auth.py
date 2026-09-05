import re

from app.admin.models import AdminCredential
from app.core.security import verify_password


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


def test_authenticated_admin_does_not_see_login_form(client):
    assert login(client).status_code == 303

    response = client.get("/admin/login", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/admin"


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


def test_admin_can_change_password_and_old_password_stops_working(client):
    assert login(client).status_code == 303
    old_session_cookie = client.cookies.get("session")
    security_page = client.get("/admin/security")

    changed = client.post(
        "/admin/security",
        data={
            "current_password": "correct-password",
            "new_password": "new-secure-password",
            "confirm_password": "new-secure-password",
            "csrf_token": extract_csrf(security_page.text),
        },
        follow_redirects=False,
    )

    assert changed.status_code == 303
    assert changed.headers["location"] == "/admin/security?changed=1"
    assert client.get("/admin/security?changed=1").status_code == 200
    with client.app.state.session_factory() as session:
        credential = session.get(AdminCredential, 1)
        assert credential is not None
        assert credential.session_version == 1
        assert verify_password("new-secure-password", credential.password_hash)
        assert "new-secure-password" not in credential.password_hash

    client.cookies.clear()
    client.cookies.set("session", old_session_cookie)
    stale_session = client.get("/admin", follow_redirects=False)
    assert stale_session.status_code == 303
    assert stale_session.headers["location"] == "/admin/login"

    assert login(client, password="correct-password").status_code == 401
    assert login(client, password="new-secure-password").status_code == 303


def test_change_password_validates_current_password_and_confirmation(client):
    assert login(client).status_code == 303
    security_page = client.get("/admin/security")

    wrong_current = client.post(
        "/admin/security",
        data={
            "current_password": "wrong-password",
            "new_password": "new-secure-password",
            "confirm_password": "new-secure-password",
            "csrf_token": extract_csrf(security_page.text),
        },
    )
    assert wrong_current.status_code == 422
    assert "رمز فعلی صحیح نیست" in wrong_current.text

    mismatch = client.post(
        "/admin/security",
        data={
            "current_password": "correct-password",
            "new_password": "new-secure-password",
            "confirm_password": "another-password",
            "csrf_token": extract_csrf(wrong_current.text),
        },
    )
    assert mismatch.status_code == 422
    assert "تکرار رمز جدید" in mismatch.text


def test_change_password_requires_csrf(client):
    assert login(client).status_code == 303

    response = client.post(
        "/admin/security",
        data={
            "current_password": "correct-password",
            "new_password": "new-secure-password",
            "confirm_password": "new-secure-password",
        },
    )

    assert response.status_code == 403
