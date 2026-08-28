# Phase 1 Foundation and Product Catalog Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** ساخت یک برنامه FastAPI قابل اجرا که ادمین بتواند امن وارد شود، داشبورد شکیل را ببیند و محصول را همراه عکس معتبر ایجاد، مشاهده و ویرایش کند.

**Architecture:** این فاز اولین زیرسیستم مستقل Modular Monolith است. کد مشترک در `app/core`، قابلیت محصول در `app/catalog`، ذخیره فایل در `app/media` و UI در `app/admin` قرار می‌گیرد؛ Routeها فقط ورودی HTTP را ترجمه می‌کنند و منطق در Serviceها می‌ماند.

**Tech Stack:** Python 3.12+، FastAPI، SQLAlchemy 2.x، Alembic، SQLite، Pydantic Settings، Jinja2، HTMX، Pillow، pwdlib/Argon2، pytest و httpx TestClient.

**Spec:** `docs/superpowers/specs/2026-08-28-agentic-content-platform-design.md`

## Global Constraints

- معماری `Modular Monolith` است؛ Microservices، Redis، Celery، LangChain و React وارد این فاز نمی‌شوند.
- مقصد انتشار در MVP فقط Channel و Support فقط گفت‌وگوی خصوصی است؛ این فاز هنوز پیام واقعی ارسال نمی‌کند.
- هیچ Secret یا Token در Source، Test Output یا Log ذخیره نمی‌شود.
- `.env` هرگز Commit نمی‌شود و `.env.example` فقط نام متغیرها را دارد.
- همه File Uploadها باید Extension، MIME، Signature، Size و نام امن را Validate کنند.
- رابط ادمین باید RTL، Responsive، قابل‌استفاده با Keyboard و از نظر بصری منسجم باشد.
- هر Task با تست شکست‌خورده شروع، با تست پاس‌شده تمام و در Commit مستقل ثبت می‌شود.
- فایل‌های `.tmp/` و `tmp/` موجود متعلق به ورودی‌های تحقیقاتی هستند و نباید Stage یا حذف شوند.

## Scope Decomposition

این سند فقط Phase 1 را اجرا می‌کند. پس از قبولی آن، برنامه‌های جداگانه برای این زیرسیستم‌ها نوشته می‌شوند:

1. Phase 2: Brand Assets، OpenAI image edit، کنترل هویت محصول، لوگو/متن فارسی، Voice و تولید کپشن.
2. Phase 3: Campaign، Manual/Auto/Pause، Scheduler، Publication و Telegram.
3. Phase 4: Bale و Rubika با تست واقعی و fallback صوت روبیکا.
4. Phase 5: Support Bot، FAQ، Grounded Answering و Human Review.
5. Phase 6: Analytics، هزینه AI، گزارش، استقرار و Hardening.
6. Phase 7: WhatsApp best-effort و گزارش صریح قابلیت‌های واقعی.

## Target File Map

- `pyproject.toml`: نسخه Python، dependencyهای runtime/dev و تنظیمات pytest/ruff.
- `.env.example`: قرارداد تنظیمات بدون Secret.
- `.gitignore`: فایل‌های محیط، دیتابیس، Upload و Cache.
- `app/factory.py`: Application Factory، Middleware، Router و Health Check با Settings تزریق‌شده.
- `app/main.py`: ساخت نمونه production برای Uvicorn از Environment واقعی.
- `app/core/config.py`: مدل Settings و Cache کنترل‌شده آن.
- `app/core/database.py`: Base، Engine/Session Factory و Dependency دیتابیس.
- `app/core/security.py`: Password Hash، Session Auth و CSRF.
- `app/core/logging.py`: پیکربندی Log بدون Secret.
- `app/catalog/models.py`: مدل SQLAlchemy محصول.
- `app/catalog/schemas.py`: قرارداد Create/Update/Read محصول.
- `app/catalog/repository.py`: عملیات persistence محصول.
- `app/catalog/service.py`: Validation و use caseهای محصول.
- `app/catalog/routes.py`: Routeهای HTML محصول.
- `app/media/images.py`: اعتبارسنجی Signature و ذخیره امن عکس.
- `app/admin/routes.py`: Login، Logout و Dashboard.
- `app/admin/dependencies.py`: Guard ورود ادمین.
- `app/templates/`: Layout، Login، Dashboard و صفحات محصول.
- `app/static/css/app.css`: Design tokens، RTL و Responsive layout.
- `app/static/js/app.js`: رفتار کوچک UI بدون framework.
- `alembic.ini` و `migrations/`: Migration قابل تکرار دیتابیس.
- `tests/`: Unit و integration testهای این فاز.
- `README.md`: Setup و شواهد اجرای Phase 1.

---

### Task 1: Application Skeleton, Settings, and Health Check

**Files:**
- Create: `pyproject.toml`
- Create: `.gitignore`
- Create: `.env.example`
- Create: `app/__init__.py`
- Create: `app/factory.py`
- Create: `app/main.py`
- Create: `app/core/__init__.py`
- Create: `app/core/config.py`
- Create: `tests/__init__.py`
- Create: `tests/test_health.py`

**Interfaces:**
- Consumes: هیچ رابط داخلی؛ این Task ریشه برنامه است.
- Produces: `Settings`, `get_settings() -> Settings`, `create_app(settings: Settings) -> FastAPI` و `GET /health`.

- [ ] **Step 1: Write the failing health and settings tests**

```python
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.factory import create_app


def test_health_returns_service_status(tmp_path):
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'test.db'}",
        upload_dir=tmp_path / "uploads",
        secret_key="test-secret-key-with-32-characters",
        admin_username="admin",
        admin_password_hash="$argon2id$v=19$m=65536,t=3,p=4$invalid$invalid",
    )
    client = TestClient(create_app(settings))

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "agentic-content-platform"}


def test_settings_reject_short_secret():
    try:
        Settings(
            secret_key="short",
            admin_password_hash="$argon2id$v=19$m=65536,t=3,p=4$invalid$invalid",
        )
    except ValueError as exc:
        assert "secret_key" in str(exc)
    else:
        raise AssertionError("short secret key must be rejected")
```

- [ ] **Step 2: Run the test and verify the missing application fails**

Run: `python -m pytest tests/test_health.py -v`

Expected: FAIL during collection with `ModuleNotFoundError: No module named 'app'` or missing `create_app`.

- [ ] **Step 3: Add dependencies and minimal application factory**

`pyproject.toml` must declare these runtime dependencies with compatible lower bounds: `fastapi>=0.116`, `uvicorn[standard]>=0.35`, `sqlalchemy>=2.0`, `alembic>=1.16`, `pydantic-settings>=2.10`, `jinja2>=3.1`, `python-multipart>=0.0.20`, `itsdangerous>=2.2`, `pwdlib[argon2]>=0.2`, `pillow>=11.3`, `httpx>=0.28`. The `dev` extra must include `pytest>=8.4`, `pytest-cov>=6.2` and `ruff>=0.12`.

```python
# app/core/config.py
from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "Agentic Content Platform"
    app_timezone: str = "Asia/Tehran"
    database_url: str = "sqlite:///./data/app.db"
    upload_dir: Path = Path("uploads")
    secret_key: str = Field(min_length=32)
    admin_username: str = "admin"
    admin_password_hash: str
    debug: bool = False


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
```

```python
# app/factory.py
from fastapi import FastAPI

from app.core.config import Settings


def create_app(settings: Settings) -> FastAPI:
    app = FastAPI(title=settings.app_name, debug=settings.debug)
    app.state.settings = settings

    @app.get("/health", tags=["system"])
    def health() -> dict[str, str]:
        return {"status": "ok", "service": "agentic-content-platform"}

    return app
```

```python
# app/main.py
from app.core.config import get_settings
from app.factory import create_app


app = create_app(get_settings())
```

`.env.example` must include `SECRET_KEY=`, `ADMIN_USERNAME=admin`, `ADMIN_PASSWORD_HASH=`, `DATABASE_URL=sqlite:///./data/app.db`, `UPLOAD_DIR=uploads`, `APP_TIMEZONE=Asia/Tehran` and `DEBUG=false`. `.gitignore` must cover `.env`, `.venv/`, `__pycache__/`, `.pytest_cache/`, `.ruff_cache/`, `*.db`, `uploads/` and generated coverage files.

- [ ] **Step 4: Install the project and run focused tests**

Run: `python -m pip install -e ".[dev]"`

Run: `python -m pytest tests/test_health.py -v`

Expected: 2 tests PASS.

- [ ] **Step 5: Run lint and commit**

Run: `python -m ruff check app tests`

Expected: exit code 0.

```bash
git add pyproject.toml .gitignore .env.example app tests
git commit -m "chore: scaffold FastAPI application"
```

---

### Task 2: Database Foundation, Product Model, and Migration

**Files:**
- Create: `app/core/database.py`
- Create: `app/catalog/__init__.py`
- Create: `app/catalog/models.py`
- Create: `alembic.ini`
- Create: `migrations/env.py`
- Create: `migrations/script.py.mako`
- Create: `migrations/versions/20260828_0001_create_products.py`
- Create: `tests/conftest.py`
- Create: `tests/catalog/test_product_model.py`
- Modify: `app/factory.py`

**Interfaces:**
- Consumes: `Settings.database_url` از Task 1.
- Produces: `Base`, `build_engine(url: str) -> Engine`, `build_session_factory(engine: Engine) -> sessionmaker[Session]`, `get_db(request: Request) -> Iterator[Session]` و مدل `Product`.

- [ ] **Step 1: Write the failing model round-trip test**

```python
from decimal import Decimal

from app.catalog.models import Product


def test_product_round_trip(db_session):
    product = Product(
        name="میز کانتر",
        description="کانتر چوبی با نمای شیاردار",
        price=Decimal("25000000"),
        availability="available",
        shipping_info="ارسال سراسر ایران",
        attributes={"material": "MDF"},
        tags=["کانتر", "دکوراسیون"],
        active=True,
    )
    db_session.add(product)
    db_session.commit()
    db_session.refresh(product)

    assert product.id is not None
    assert product.price == Decimal("25000000.00")
    assert product.attributes == {"material": "MDF"}
    assert product.tags == ["کانتر", "دکوراسیون"]
    assert product.created_at.tzinfo is not None
```

- [ ] **Step 2: Run the model test and verify failure**

Run: `python -m pytest tests/catalog/test_product_model.py -v`

Expected: FAIL with missing `app.catalog.models` or `Product`.

- [ ] **Step 3: Implement database helpers and the Product model**

```python
# app/core/database.py
from collections.abc import Iterator

from fastapi import Request
from datetime import datetime, timezone

from sqlalchemy import DateTime, Engine, create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.types import TypeDecorator


class Base(DeclarativeBase):
    pass


class UTCDateTime(TypeDecorator[datetime]):
    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect: object) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError("datetime must be timezone-aware")
        return value.astimezone(timezone.utc)

    def process_result_value(self, value: datetime | None, dialect: object) -> datetime | None:
        if value is None or value.tzinfo is not None:
            return value
        return value.replace(tzinfo=timezone.utc)


def build_engine(url: str) -> Engine:
    connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
    return create_engine(url, connect_args=connect_args, pool_pre_ping=True)


def build_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, expire_on_commit=False)


def get_db(request: Request) -> Iterator[Session]:
    factory = request.app.state.session_factory
    with factory() as session:
        yield session
```

```python
# app/catalog/models.py
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import JSON, Boolean, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base, UTCDateTime


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Product(Base):
    __tablename__ = "products"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200), index=True)
    description: Mapped[str] = mapped_column(Text, default="")
    price: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    availability: Mapped[str] = mapped_column(String(40), default="available")
    shipping_info: Mapped[str] = mapped_column(Text, default="")
    attributes: Mapped[dict[str, str]] = mapped_column(JSON, default=dict)
    tags: Mapped[list[str]] = mapped_column(JSON, default=list)
    primary_image_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now, onupdate=utc_now)
```

In `create_app`, build the engine/session factory once and store both on `app.state`. `tests/conftest.py` must use a temporary SQLite database, call `Base.metadata.create_all(engine)`, yield a session and remove the temporary schema after each test. Test settings set `debug=True` so secure production cookies are not required over TestClient HTTP.

- [ ] **Step 4: Add and verify the initial Alembic migration**

The migration must create `products` with the exact columns and indexes from `Product`. Set `target_metadata = Base.metadata` in `migrations/env.py` and import `app.catalog.models` before configuring the context.

Run: `python -m alembic upgrade head`

Expected: a local development database is created and revision `20260828_0001` is current.

Run: `python -m alembic downgrade base`

Run: `python -m alembic upgrade head`

Expected: both commands exit 0, proving reversible migration.

- [ ] **Step 5: Run focused tests and commit**

Run: `python -m pytest tests/catalog/test_product_model.py -v`

Expected: 1 test PASS.

```bash
git add app/core/database.py app/catalog alembic.ini migrations tests/conftest.py tests/catalog/test_product_model.py app/factory.py
git commit -m "feat: add product persistence foundation"
```

---

### Task 3: Secure Admin Login, Session Guard, and CSRF

**Files:**
- Create: `app/core/security.py`
- Create: `app/admin/__init__.py`
- Create: `app/admin/dependencies.py`
- Create: `app/admin/routes.py`
- Create: `app/templates/auth/login.html`
- Create: `tests/admin/test_auth.py`
- Modify: `app/factory.py`

**Interfaces:**
- Consumes: `Settings.admin_username`, `Settings.admin_password_hash` و `Settings.secret_key`.
- Produces: `hash_password(password: str) -> str`, `verify_password(password: str, password_hash: str) -> bool`, `ensure_csrf_token(request: Request) -> str`, `validate_csrf(request: Request, submitted: str) -> None` و `require_admin(request: Request) -> str`.

- [ ] **Step 1: Write failing authentication and CSRF tests**

```python
def test_dashboard_redirects_anonymous_user(client):
    response = client.get("/admin", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/admin/login"


def test_admin_can_login(client, admin_credentials):
    login_page = client.get("/admin/login")
    csrf = extract_csrf(login_page.text)

    response = client.post(
        "/admin/login",
        data={"username": "admin", "password": "correct-password", "csrf_token": csrf},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/admin"
    assert client.get("/admin").status_code == 200


def test_login_rejects_missing_csrf(client):
    response = client.post(
        "/admin/login",
        data={"username": "admin", "password": "correct-password"},
    )
    assert response.status_code == 403
```

- [ ] **Step 2: Run auth tests and verify route failure**

Run: `python -m pytest tests/admin/test_auth.py -v`

Expected: FAIL because `/admin/login` and security helpers do not exist.

- [ ] **Step 3: Implement password, session, and CSRF primitives**

```python
# app/core/security.py
import hmac
import secrets

from fastapi import HTTPException, Request, status
from pwdlib import PasswordHash

password_hash = PasswordHash.recommended()


def hash_password(password: str) -> str:
    return password_hash.hash(password)


def verify_password(password: str, encoded: str) -> bool:
    try:
        return password_hash.verify(password, encoded)
    except Exception:
        return False


def ensure_csrf_token(request: Request) -> str:
    token = request.session.get("csrf_token")
    if not token:
        token = secrets.token_urlsafe(32)
        request.session["csrf_token"] = token
    return token


def validate_csrf(request: Request, submitted: str) -> None:
    expected = request.session.get("csrf_token", "")
    if not expected or not hmac.compare_digest(expected, submitted):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid CSRF token")
```

Add `SessionMiddleware` with `same_site="lax"`, `https_only=not settings.debug` and the configured secret. The Login route must regenerate the CSRF token after successful authentication, store only `admin_username` in the signed session, return a generic Persian error for invalid credentials and never log the submitted password.

- [ ] **Step 4: Implement admin guard and minimal dashboard response**

```python
# app/admin/dependencies.py
from fastapi import HTTPException, Request


def require_admin(request: Request) -> str:
    username = request.session.get("admin_username")
    if not username:
        raise HTTPException(status_code=303, headers={"Location": "/admin/login"})
    return str(username)
```

The `/admin` handler must use `Depends(require_admin)` and return an HTML response containing `<main data-page="dashboard">`. The Logout action must require POST plus CSRF, clear the session and redirect to Login.

- [ ] **Step 5: Run auth tests and commit**

Run: `python -m pytest tests/admin/test_auth.py -v`

Expected: anonymous redirect, valid login, invalid login, CSRF rejection and logout tests all PASS.

```bash
git add app/core/security.py app/admin app/templates/auth app/factory.py tests/admin
git commit -m "feat: secure the admin session"
```

---

### Task 4: Product Schemas, Repository, and Service

**Files:**
- Create: `app/catalog/schemas.py`
- Create: `app/catalog/repository.py`
- Create: `app/catalog/service.py`
- Create: `tests/catalog/test_product_service.py`

**Interfaces:**
- Consumes: `Product` و `Session`.
- Produces: `ProductCreate`, `ProductUpdate`, `ProductRead`, `ProductRepository.list()`, `ProductRepository.get(product_id)`, `ProductRepository.add(product)`, `ProductService.create(data)`, `ProductService.update(product_id, data)` و `ProductService.set_image(product_id, path)`.

- [ ] **Step 1: Write failing service validation and persistence tests**

```python
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.catalog.repository import ProductRepository
from app.catalog.schemas import ProductCreate, ProductUpdate
from app.catalog.service import ProductNotFound, ProductService


def test_create_product_normalizes_tags(db_session):
    service = ProductService(ProductRepository(db_session))
    product = service.create(
        ProductCreate(
            name="  میز کانتر  ",
            description="مدل منحنی",
            price=Decimal("25000000"),
            availability="available",
            shipping_info="ارسال سراسر ایران",
            attributes={"جنس": "MDF"},
            tags=["دکوراسیون", " دکوراسیون ", "کانتر"],
            active=True,
        )
    )

    assert product.name == "میز کانتر"
    assert product.tags == ["دکوراسیون", "کانتر"]


def test_product_rejects_negative_price():
    with pytest.raises(ValidationError):
        ProductCreate(name="محصول", price=Decimal("-1"))


def test_update_unknown_product_raises(db_session):
    service = ProductService(ProductRepository(db_session))
    with pytest.raises(ProductNotFound):
        service.update(999, ProductUpdate(name="نام جدید"))
```

- [ ] **Step 2: Run the service tests and verify missing interfaces**

Run: `python -m pytest tests/catalog/test_product_service.py -v`

Expected: FAIL because schemas, repository and service are missing.

- [ ] **Step 3: Implement strict schemas**

```python
# app/catalog/schemas.py
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ProductCreate(BaseModel):
    name: str = Field(min_length=2, max_length=200)
    description: str = ""
    price: Decimal = Field(ge=0, max_digits=18, decimal_places=2)
    availability: str = Field(default="available", max_length=40)
    shipping_info: str = ""
    attributes: dict[str, str] = Field(default_factory=dict)
    tags: list[str] = Field(default_factory=list, max_length=30)
    active: bool = True

    @field_validator("name", "description", "availability", "shipping_info")
    @classmethod
    def strip_text(cls, value: str) -> str:
        return value.strip()

    @field_validator("tags")
    @classmethod
    def normalize_tags(cls, values: list[str]) -> list[str]:
        return list(dict.fromkeys(value.strip() for value in values if value.strip()))


class ProductUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=200)
    description: str | None = None
    price: Decimal | None = Field(default=None, ge=0, max_digits=18, decimal_places=2)
    availability: str | None = Field(default=None, max_length=40)
    shipping_info: str | None = None
    attributes: dict[str, str] | None = None
    tags: list[str] | None = Field(default=None, max_length=30)
    active: bool | None = None


class ProductRead(ProductCreate):
    model_config = ConfigDict(from_attributes=True)
    id: int
    primary_image_path: str | None
```

- [ ] **Step 4: Implement repository and transaction-owning service**

Repository methods only query/mutate the Session. Service methods validate use cases and call `session.commit()` exactly once per successful operation; failed operations call `session.rollback()`. Define `ProductNotFound(LookupError)` and never return `None` from update operations.

```python
class ProductService:
    def __init__(self, repository: ProductRepository) -> None:
        self.repository = repository

    def create(self, data: ProductCreate) -> Product:
        product = Product(**data.model_dump())
        self.repository.add(product)
        self.repository.commit()
        self.repository.refresh(product)
        return product

    def update(self, product_id: int, data: ProductUpdate) -> Product:
        product = self.repository.get(product_id)
        if product is None:
            raise ProductNotFound(product_id)
        for field, value in data.model_dump(exclude_unset=True).items():
            setattr(product, field, value)
        self.repository.commit()
        self.repository.refresh(product)
        return product
```

- [ ] **Step 5: Run service tests and commit**

Run: `python -m pytest tests/catalog/test_product_service.py -v`

Expected: all service tests PASS.

```bash
git add app/catalog/schemas.py app/catalog/repository.py app/catalog/service.py tests/catalog/test_product_service.py
git commit -m "feat: add product catalog service"
```

---

### Task 5: Safe Product Image Storage

**Files:**
- Create: `app/media/__init__.py`
- Create: `app/media/images.py`
- Create: `tests/media/test_images.py`

**Interfaces:**
- Consumes: `Settings.upload_dir` و byteهای Upload.
- Produces: `ValidatedImage`, `InvalidImage(ValueError)`, `validate_image(data: bytes, filename: str, content_type: str) -> ValidatedImage` و `save_product_image(root: Path, product_id: int, image: ValidatedImage) -> Path`.

- [ ] **Step 1: Write failing image signature, size, and safe-name tests**

```python
from io import BytesIO

import pytest
from PIL import Image

from app.media.images import InvalidImage, save_product_image, validate_image


def png_bytes() -> bytes:
    output = BytesIO()
    Image.new("RGB", (32, 32), "white").save(output, format="PNG")
    return output.getvalue()


def test_valid_image_is_saved_under_product_directory(tmp_path):
    image = validate_image(png_bytes(), "../unsafe.png", "image/png")
    path = save_product_image(tmp_path, 12, image)

    assert path.parent == tmp_path / "products" / "12" / "original"
    assert path.suffix == ".png"
    assert "unsafe" not in path.name
    assert path.read_bytes() == png_bytes()


def test_fake_image_is_rejected():
    with pytest.raises(InvalidImage, match="ساختار تصویر معتبر نیست"):
        validate_image(b"not-an-image", "fake.png", "image/png")


def test_oversized_image_is_rejected(monkeypatch):
    monkeypatch.setattr("app.media.images.MAX_IMAGE_BYTES", 8)
    with pytest.raises(InvalidImage, match="حجم تصویر"):
        validate_image(png_bytes(), "photo.png", "image/png")
```

- [ ] **Step 2: Run media tests and verify missing module failure**

Run: `python -m pytest tests/media/test_images.py -v`

Expected: FAIL because `app.media.images` is missing.

- [ ] **Step 3: Implement byte-level validation and deterministic metadata**

`validate_image` must enforce 15 MiB maximum, MIME allowlist `image/jpeg`, `image/png`, `image/webp`, Pillow `verify()`, maximum 20,000,000 pixels and format/MIME agreement. It returns immutable bytes, lowercase suffix, SHA-256 digest, width and height.

```python
from dataclasses import dataclass
from hashlib import sha256
from io import BytesIO
from pathlib import Path
from uuid import uuid4

from PIL import Image, UnidentifiedImageError

MAX_IMAGE_BYTES = 15 * 1024 * 1024
MAX_IMAGE_PIXELS = 20_000_000
ALLOWED_MIME = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}


@dataclass(frozen=True)
class ValidatedImage:
    data: bytes
    suffix: str
    sha256: str
    width: int
    height: int


class InvalidImage(ValueError):
    pass


def validate_image(data: bytes, filename: str, content_type: str) -> ValidatedImage:
    if len(data) > MAX_IMAGE_BYTES:
        raise InvalidImage("حجم تصویر بیشتر از حد مجاز است")
    expected_suffix = ALLOWED_MIME.get(content_type.lower())
    if expected_suffix is None:
        raise InvalidImage("نوع تصویر پشتیبانی نمی‌شود")
    try:
        with Image.open(BytesIO(data)) as opened:
            opened.verify()
        with Image.open(BytesIO(data)) as opened:
            width, height = opened.size
            actual_format = (opened.format or "").upper()
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
        raise InvalidImage("ساختار تصویر معتبر نیست") from exc
    format_suffix = {"JPEG": ".jpg", "PNG": ".png", "WEBP": ".webp"}.get(actual_format)
    if format_suffix != expected_suffix:
        raise InvalidImage("نوع اعلام‌شده با محتوای تصویر یکسان نیست")
    if width * height > MAX_IMAGE_PIXELS:
        raise InvalidImage("ابعاد تصویر بیشتر از حد مجاز است")
    return ValidatedImage(data, format_suffix, sha256(data).hexdigest(), width, height)


def save_product_image(root: Path, product_id: int, image: ValidatedImage) -> Path:
    directory = root / "products" / str(product_id) / "original"
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / f"{uuid4().hex}{image.suffix}"
    target.write_bytes(image.data)
    return target
```

The implementation must catch `UnidentifiedImageError`, `OSError` and decompression-bomb errors and convert them to Persian `InvalidImage` messages without exposing filesystem paths.

- [ ] **Step 4: Run media tests and commit**

Run: `python -m pytest tests/media/test_images.py -v`

Expected: valid PNG, fake bytes, wrong MIME, oversized input and excessive pixel tests PASS.

```bash
git add app/media tests/media
git commit -m "feat: validate and store product images"
```

---

### Task 6: Product Admin Routes and End-to-End Form Flow

**Files:**
- Create: `app/catalog/routes.py`
- Create: `app/templates/products/index.html`
- Create: `app/templates/products/form.html`
- Create: `app/templates/products/detail.html`
- Create: `tests/admin/test_product_routes.py`
- Modify: `app/factory.py`
- Modify: `app/catalog/service.py`

**Interfaces:**
- Consumes: `require_admin`, `validate_csrf`, `get_db`, `ProductService`, `validate_image` و `save_product_image`.
- Produces: `GET /admin/products`, `GET /admin/products/new`, `POST /admin/products`, `GET /admin/products/{id}`, `GET /admin/products/{id}/edit`، `POST /admin/products/{id}` و نمایش فایل‌های opaque در `/uploads`.

- [ ] **Step 1: Write failing authenticated product flow test**

```python
def test_admin_creates_product_with_real_image(authenticated_client, csrf_token, png_upload):
    response = authenticated_client.post(
        "/admin/products",
        data={
            "csrf_token": csrf_token,
            "name": "میز کانتر",
            "description": "طراحی منحنی",
            "price": "25000000",
            "availability": "available",
            "shipping_info": "ارسال سراسر ایران",
            "tags": "کانتر، دکوراسیون",
            "active": "true",
        },
        files={"image": ("counter.png", png_upload, "image/png")},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"].startswith("/admin/products/")
    detail = authenticated_client.get(response.headers["location"])
    assert "میز کانتر" in detail.text
    assert "۲۵٬۰۰۰٬۰۰۰" in detail.text
    assert "counter.png" not in detail.text
```

Add tests for anonymous redirect, invalid price returning 422-style form feedback, invalid image returning a Persian error without creating a product, edit preserving the existing image, and CSRF rejection.

- [ ] **Step 2: Run route tests and verify 404 failures**

Run: `python -m pytest tests/admin/test_product_routes.py -v`

Expected: FAIL because product routes return 404.

- [ ] **Step 3: Implement thin routes with explicit form parsing**

Routes must be synchronous for SQLAlchemy Session use. Parse Persian/Latin comma-separated tags with one helper and parse attributes from paired form rows only when both key and value are non-empty. On validation errors, re-render the form with status 422, preserve non-secret input and show field-specific Persian messages.

At application startup, create `Settings.upload_dir / "products"` if missing and mount only that product-image subtree with Starlette `StaticFiles` at `/uploads/products`; future Voice/private assets are not exposed. Templates receive only `primary_image_path` relative to the Upload root; attempts containing `..` or absolute paths are rejected by `ProductService.set_image` before persistence.

The create flow order is:

1. validate CSRF;
2. read and validate image bytes;
3. validate `ProductCreate`;
4. create Product;
5. save image under the new Product ID;
6. call `ProductService.set_image` with a path relative to Upload root;
7. redirect to detail.

If file storage fails after Product creation, delete the incomplete Product in a compensating transaction and show a safe error. The edit flow must never delete or replace the old image until a new image has validated and saved successfully.

- [ ] **Step 4: Implement accessible RTL templates**

`products/index.html` must include a clear Add Product action, active/inactive badge, formatted price, image thumbnail fallback and empty state. `form.html` must use `<label for>`, server-rendered errors, accepted format/size hint and image preview. `detail.html` must show stored business facts and an Edit action; it must not expose absolute filesystem paths.

- [ ] **Step 5: Run route and service tests and commit**

Run: `python -m pytest tests/admin/test_product_routes.py tests/catalog/test_product_service.py tests/media/test_images.py -v`

Expected: all selected tests PASS.

```bash
git add app/catalog app/templates/products app/factory.py tests/admin/test_product_routes.py
git commit -m "feat: manage products from the admin panel"
```

---

### Task 7: Polished RTL Admin Shell and Useful Dashboard

**Files:**
- Create: `app/templates/base.html`
- Create: `app/templates/dashboard/index.html`
- Create: `app/templates/components/flash.html`
- Create: `app/static/css/app.css`
- Create: `app/static/js/app.js`
- Create: `tests/admin/test_dashboard.py`
- Modify: `app/admin/routes.py`
- Modify: `app/templates/auth/login.html`
- Modify: `app/templates/products/index.html`
- Modify: `app/templates/products/form.html`
- Modify: `app/templates/products/detail.html`
- Modify: `app/factory.py`

**Interfaces:**
- Consumes: Product repository counts and authenticated admin session.
- Produces: shared RTL layout, responsive navigation, dashboard cards and `GET /static/*` assets.

- [ ] **Step 1: Write failing dashboard semantics test**

```python
def test_dashboard_has_useful_phase_one_metrics(authenticated_client):
    response = authenticated_client.get("/admin")

    assert response.status_code == 200
    assert 'dir="rtl"' in response.text
    assert 'data-metric="total-products"' in response.text
    assert 'data-metric="active-products"' in response.text
    assert 'data-action="create-product"' in response.text
    assert 'aria-label="ناوبری اصلی"' in response.text
    assert "Pause All Publishing" not in response.text
```

The last assertion keeps later unavailable features out of the UI instead of presenting fake controls.

- [ ] **Step 2: Run dashboard tests and verify missing layout markers**

Run: `python -m pytest tests/admin/test_dashboard.py -v`

Expected: FAIL because the dashboard does not expose the required layout and metrics.

- [ ] **Step 3: Implement dashboard query and shared layout**

Dashboard must query total and active products through a repository method rather than SQL inside the template. `base.html` must include Persian page title, sidebar/compact mobile navigation, current-page state, logout POST form with CSRF and a content slot. Static files must be mounted at `/static`.

- [ ] **Step 4: Implement restrained visual system**

`app.css` must define CSS custom properties for neutral background, deep navy text, turquoise accent, success/warning/error, 8/12/16/24/32 spacing and consistent radius/shadow. Use a system Persian-capable font stack without loading third-party trackers. Required breakpoints: desktop sidebar at `min-width: 960px`; compact top bar below it; form fields become one column below `640px`.

All interactive elements require visible `:focus-visible`, 44px minimum touch target, readable contrast, disabled state and reduced-motion handling. Product cards use `aspect-ratio` and `object-fit: cover` without distorting images.

- [ ] **Step 5: Run automated UI tests and manual visual checks**

Run: `python -m pytest tests/admin/test_dashboard.py tests/admin/test_product_routes.py tests/admin/test_auth.py -v`

Expected: all selected tests PASS.

Run the local server: `python -m uvicorn app.main:app --reload`

Manual check at 1440x900 and 390x844:

- login card is centered and readable;
- sidebar/top bar never overlaps content;
- Product Add/Edit is usable without horizontal scroll;
- Persian text direction, price formatting and focus states are correct;
- empty and populated product states both look intentional.

- [ ] **Step 6: Commit the UI shell**

```bash
git add app/templates app/static app/admin/routes.py app/factory.py tests/admin/test_dashboard.py
git commit -m "feat: add polished RTL admin dashboard"
```

---

### Task 8: Logging, Phase Documentation, and Verification Gate

**Files:**
- Create: `app/core/logging.py`
- Create: `tests/core/test_logging.py`
- Create: `README.md`
- Modify: `app/factory.py`
- Modify: `.env.example`
- Modify: `pyproject.toml`

**Interfaces:**
- Consumes: Settings، Application Factory و completed Phase 1 routes.
- Produces: `configure_logging(debug: bool) -> None`, secret redaction filter, complete Phase 1 runbook and final verification evidence.

- [ ] **Step 1: Write failing secret-redaction test**

```python
import logging

from app.core.logging import configure_logging


def test_logs_redact_token_like_values(caplog):
    configure_logging(debug=True)
    logger = logging.getLogger("app.test")

    with caplog.at_level(logging.INFO):
        logger.info("bot_token=%s api_key=%s", "123456:secret", "sk-sensitive")

    combined = " ".join(record.getMessage() for record in caplog.records)
    assert "123456:secret" not in combined
    assert "sk-sensitive" not in combined
    assert "[REDACTED]" in combined
```

- [ ] **Step 2: Run logging test and verify failure**

Run: `python -m pytest tests/core/test_logging.py -v`

Expected: FAIL because logging configuration does not exist.

- [ ] **Step 3: Implement structured, redacted application logging**

Configure timestamp, level, logger and message. Redact values following case-insensitive keys `token`, `api_key`, `authorization`, `password`, `secret` and known prefixes `sk-`. Application startup may log environment name, database dialect and upload root existence, but never the database credential or absolute Secret values.

- [ ] **Step 4: Write the Phase 1 README runbook**

README must include:

- Phase 1 capability list and explicitly unavailable later-phase features;
- Python 3.12 virtual environment setup;
- editable installation command;
- generating an Argon2 admin password hash with a safe one-line module command;
- `.env` setup without example production secrets;
- `alembic upgrade head`;
- server start command;
- login URL;
- running focused and full tests;
- upload directory permissions and backup note;
- current SQLite limitation and future PostgreSQL migration path;
- credential checklist for future OpenAI/Telegram/Bale/Rubika phases.

- [ ] **Step 5: Run the complete Phase 1 verification suite**

Run: `python -m ruff check app tests`

Expected: exit code 0.

Run: `python -m pytest -v --cov=app --cov-report=term-missing`

Expected: all Phase 1 tests PASS and no untested error branch in Auth, Product Service or Upload Validation is hidden by a failing test.

Run: `python -m alembic downgrade base`

Run: `python -m alembic upgrade head`

Expected: both migration commands exit 0.

Run: `git diff --check`

Expected: no whitespace errors.

- [ ] **Step 6: Commit Phase 1 documentation and verification support**

```bash
git add app/core/logging.py app/factory.py tests/core/test_logging.py README.md .env.example pyproject.toml
git commit -m "docs: complete phase one runbook"
```

- [ ] **Step 7: Record the Phase 1 checkpoint**

Run: `git status --short`

Expected: no Phase 1 source file is untracked or modified; only pre-existing research directories `.tmp/` and `tmp/` may remain untracked.

Run: `git log --oneline --max-count=10`

Expected: the eight logical Phase 1 commits are visible, including the approved design and this implementation plan.

## Phase 1 Definition of Done

Phase 1 is complete only if all of these are true:

- Application starts with documented environment variables.
- Database migration is reversible and repeatable.
- Anonymous users cannot access admin pages.
- Login, Logout and every state-changing form enforce CSRF.
- Admin can create, view and edit a Product with a validated real image.
- Original product image is stored under an opaque server filename and no absolute path leaks to HTML.
- Dashboard and Product pages pass automated tests and manual desktop/mobile visual review.
- Logs redact credential-like values.
- Full Phase 1 test and lint commands pass from a clean checkout.
- No AI call or real platform publication occurs in this phase.
