from fastapi import HTTPException, Request


def require_admin(request: Request) -> str:
    username = request.session.get("admin_username")
    if not username:
        raise HTTPException(status_code=303, headers={"Location": "/admin/login"})
    return str(username)
