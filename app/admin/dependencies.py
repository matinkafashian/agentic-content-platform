from fastapi import HTTPException, Request

from app.admin.credentials import effective_password


def admin_session_is_current(request: Request) -> bool:
    if not request.session.get("admin_username"):
        return False
    with request.app.state.session_factory() as session:
        _, current_version = effective_password(session, request.app.state.settings)
    try:
        session_version = int(request.session.get("admin_session_version", 0))
    except (TypeError, ValueError):
        return False
    return session_version == current_version


def require_admin(request: Request) -> str:
    username = request.session.get("admin_username")
    if not username or not admin_session_is_current(request):
        request.session.clear()
        raise HTTPException(status_code=303, headers={"Location": "/admin/login"})
    return str(username)
