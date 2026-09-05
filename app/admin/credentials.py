from sqlalchemy.orm import Session

from app.admin.models import AdminCredential
from app.core.config import Settings
from app.core.security import hash_password


def effective_password(session: Session, settings: Settings) -> tuple[str, int]:
    credential = session.get(AdminCredential, 1)
    if credential is None:
        return settings.admin_password_hash, 0
    return credential.password_hash, credential.session_version


def replace_password(session: Session, new_password: str) -> AdminCredential:
    credential = session.get(AdminCredential, 1)
    if credential is None:
        credential = AdminCredential(
            id=1,
            password_hash=hash_password(new_password),
            session_version=1,
        )
        session.add(credential)
    else:
        credential.password_hash = hash_password(new_password)
        credential.session_version += 1
    session.commit()
    session.refresh(credential)
    return credential
