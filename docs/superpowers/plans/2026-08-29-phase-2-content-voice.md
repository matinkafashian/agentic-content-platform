# Phase 2A Content Studio and Original Voice Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a testable Persian content-draft workflow with editable brand facts, deterministic non-production generation, revision/approval history, and unchanged private voice recording/upload.

**Architecture:** Add focused `brand` and `content` modules to the existing FastAPI modular monolith and add private voice validation/storage under `media`. The UI talks only to services; content services depend on a `ContentProvider` protocol so the deterministic template provider can later be replaced by OpenAI without changing routes, persistence, or templates.

**Tech Stack:** Python 3.12+, FastAPI, Jinja2, SQLAlchemy 2.x, Alembic, Pydantic 2, browser MediaRecorder, pytest, Ruff.

**Spec:** `docs/superpowers/specs/2026-08-29-phase-2-content-voice-design.md`

## Global Constraints

- OpenAI is not called in this plan; every preview must say `حالت آزمایشی — بدون OpenAI`.
- Product data is read-only to the content workflow.
- Price, warranty, shipping, material, delivery time, and other claims may appear only when present in Product, BrandProfile approved claims, or the current user brief.
- Original provider JSON is immutable; manual edits affect only `final_caption`.
- Regeneration creates a new revision; it never overwrites an earlier revision.
- Only one revision in a series may be `approved`; the previous approved revision becomes `superseded` atomically.
- Voice bytes are preserved exactly; no transcoding, trimming, denoising, or speech transformation occurs in this plan.
- Voice storage is private and available only through an authenticated route; it is never mounted under `/uploads`.
- Voice upload limit is 25 MiB; browser recording limit is 600,000 ms.
- All mutating routes require the existing session authentication and CSRF validation.
- Tests must be written and observed failing before production implementation for every task.
- Generated `.tmp/` and `tmp/` files in the workspace are unrelated and must not be staged.

---

## File Map

- `app/brand/models.py`: single editable BrandProfile persistence model.
- `app/brand/schemas.py`: normalization and validation for brand facts.
- `app/brand/repository.py`: persistence operations for the one profile.
- `app/brand/service.py`: default creation and updates.
- `app/brand/routes.py`: authenticated settings page.
- `app/content/models.py`: ContentDraft revision model and statuses.
- `app/content/schemas.py`: provider request/output contracts and form validation.
- `app/content/providers.py`: protocol and deterministic TemplateContentProvider.
- `app/content/repository.py`: draft history queries and transaction primitives.
- `app/content/service.py`: request construction, generation, edit, regenerate, approve, reject.
- `app/content/routes.py`: content studio and draft actions.
- `app/media/models.py`: private MediaAsset metadata.
- `app/media/voice.py`: signature validation and byte-preserving storage.
- `app/media/voice_service.py`: transactional attach/replace/delete behavior.
- `app/templates/brand/form.html`: brand profile form.
- `app/templates/content/new.html`: brief and angle form.
- `app/templates/content/detail.html`: preview, revision history, approval, and voice controls.
- `app/static/js/voice-recorder.js`: MediaRecorder lifecycle and local preview.
- `app/static/css/app.css`: responsive content studio and recorder styles.
- `migrations/versions/20260829_0002_content_voice.py`: reversible schema migration.

---

### Task 1: Persistence Models and Reversible Migration

**Files:**
- Create: `app/brand/__init__.py`
- Create: `app/brand/models.py`
- Create: `app/content/__init__.py`
- Create: `app/content/models.py`
- Create: `app/media/models.py`
- Create: `migrations/versions/20260829_0002_content_voice.py`
- Modify: `migrations/env.py`
- Test: `tests/brand/test_brand_model.py`
- Test: `tests/content/test_content_model.py`
- Test: `tests/media/test_media_model.py`

**Interfaces:**
- Produces: `BrandProfile`, `ContentDraft`, `DraftStatus`, `MediaAsset`, and database tables `brand_profiles`, `content_drafts`, `media_assets`.
- Consumes: existing `Product`, `Base`, `UTCDateTime`, and `utc_now()` conventions.

- [ ] **Step 1: Write model round-trip tests**

```python
# tests/content/test_content_model.py
from decimal import Decimal

from app.catalog.models import Product
from app.content.models import ContentDraft, DraftStatus


def test_content_revision_keeps_provider_payload_separate_from_final_caption(db_session):
    product = Product(
        name="میز کانتر",
        description="نمای شیاردار",
        price=Decimal("25000000"),
        availability="available",
        shipping_info="ارسال سراسر ایران",
        attributes={"متریال": "MDF"},
        tags=["دکوراسیون"],
        active=True,
    )
    db_session.add(product)
    db_session.flush()
    draft = ContentDraft(
        product_id=product.id,
        series_key="series-1",
        revision=1,
        user_brief="برای کابینت‌سازان حرفه‌ای",
        requested_angle="product_intro",
        provider_name="template",
        provider_payload={"headline": "عنوان اولیه"},
        final_caption="نسخه قابل ویرایش",
        status=DraftStatus.WAITING_APPROVAL.value,
    )
    db_session.add(draft)
    db_session.commit()
    db_session.refresh(draft)

    assert draft.provider_payload == {"headline": "عنوان اولیه"}
    assert draft.final_caption == "نسخه قابل ویرایش"
    assert draft.product.name == "میز کانتر"
    assert draft.created_at.tzinfo is not None
```

```python
# tests/brand/test_brand_model.py
from app.brand.models import BrandProfile


def test_brand_profile_round_trip(db_session):
    profile = BrandProfile(
        business_name="هایکا",
        tagline="تفاوت در جزئیات",
        audience="کابینت‌سازان حرفه‌ای",
        tone_guidelines="تخصصی و محترمانه",
        support_handle="@hayka_poshtibani",
        default_cta="برای ثبت سفارش پیام دهید.",
        approved_claims=["ارسال رایگان به سراسر ایران"],
        default_hashtags=["هایکا", "درب_ممبران"],
    )
    db_session.add(profile)
    db_session.commit()
    db_session.refresh(profile)

    assert profile.id == 1
    assert profile.approved_claims == ["ارسال رایگان به سراسر ایران"]
```

```python
# tests/media/test_media_model.py
from decimal import Decimal

from app.catalog.models import Product
from app.content.models import ContentDraft, DraftStatus
from app.media.models import MediaAsset


def test_media_asset_requires_private_relative_path(db_session):
    product = Product(
        name="میز کانتر",
        description="نمای شیاردار",
        price=Decimal("25000000"),
        availability="available",
        shipping_info="",
        attributes={},
        tags=[],
        active=True,
    )
    db_session.add(product)
    db_session.flush()
    content_draft = ContentDraft(
        product_id=product.id,
        series_key="series-voice",
        revision=1,
        user_brief="معرفی محصول",
        requested_angle="product_intro",
        provider_name="template",
        provider_payload={"headline": "معرفی محصول"},
        final_caption="متن نهایی معرفی محصول",
        status=DraftStatus.WAITING_APPROVAL.value,
    )
    db_session.add(content_draft)
    db_session.flush()

    asset = MediaAsset(
        content_draft_id=content_draft.id,
        kind="voice_original",
        relative_path="private/voices/1/abc.webm",
        mime_type="audio/webm",
        size_bytes=4,
        sha256="0" * 64,
        duration_ms=1500,
    )
    db_session.add(asset)
    db_session.commit()

    assert asset.relative_path.startswith("private/voices/")
```

- [ ] **Step 2: Run the new tests and verify RED**

Run:

```powershell
& '.\.worktrees\phase-1-foundation\.venv\Scripts\python.exe' -m pytest tests/brand/test_brand_model.py tests/content/test_content_model.py tests/media/test_media_model.py -v
```

Expected: collection fails because the new modules and models do not exist.

- [ ] **Step 3: Implement the three models**

Use these exact status values and relationships:

```python
# app/content/models.py
from datetime import datetime
from enum import StrEnum

from sqlalchemy import JSON, CheckConstraint, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.catalog.models import utc_now
from app.core.database import Base, UTCDateTime


class DraftStatus(StrEnum):
    DRAFT = "draft"
    WAITING_APPROVAL = "waiting_approval"
    APPROVED = "approved"
    REJECTED = "rejected"
    SUPERSEDED = "superseded"


class ContentDraft(Base):
    __tablename__ = "content_drafts"
    __table_args__ = (
        CheckConstraint(
            "status in ('draft','waiting_approval','approved','rejected','superseded')",
            name="ck_content_drafts_status",
        ),
        Index("ix_content_drafts_series_revision", "series_key", "revision", unique=True),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), index=True)
    parent_id: Mapped[int | None] = mapped_column(
        ForeignKey("content_drafts.id"), nullable=True
    )
    series_key: Mapped[str] = mapped_column(String(36), index=True)
    revision: Mapped[int] = mapped_column(Integer)
    user_brief: Mapped[str] = mapped_column(Text)
    requested_angle: Mapped[str] = mapped_column(String(40))
    provider_name: Mapped[str] = mapped_column(String(80))
    provider_payload: Mapped[dict[str, object]] = mapped_column(JSON)
    final_caption: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(
        String(24), default=DraftStatus.WAITING_APPROVAL.value, index=True
    )
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), default=utc_now, onupdate=utc_now
    )
    approved_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)

    product = relationship("Product")
    parent = relationship("ContentDraft", remote_side=[id])
```

`BrandProfile` uses non-null `Text` fields and JSON lists with `default=list`. `MediaAsset` uses a unique constraint on `(content_draft_id, kind)`, a foreign key to `content_drafts.id`, and the exact metadata fields in the design. All timestamps use `Mapped[datetime]` with `UTCDateTime`.

- [ ] **Step 4: Add the reversible Alembic migration**

Set `revision = "20260829_0002"` and `down_revision = "20260828_0001"`. `upgrade()` creates `brand_profiles`, `content_drafts`, then `media_assets`, including foreign keys, status check, the unique series/revision index, and the unique draft/kind constraint. `downgrade()` drops them in reverse dependency order. Import all three model modules in `migrations/env.py` so metadata is complete.

- [ ] **Step 5: Run model tests and migration round trip**

Run:

```powershell
& '.\.worktrees\phase-1-foundation\.venv\Scripts\python.exe' -m pytest tests/brand/test_brand_model.py tests/content/test_content_model.py tests/media/test_media_model.py -v
$env:DATABASE_URL='sqlite:///./.tmp/phase2-migration.db'
& '.\.worktrees\phase-1-foundation\.venv\Scripts\python.exe' -m alembic upgrade head
& '.\.worktrees\phase-1-foundation\.venv\Scripts\python.exe' -m alembic downgrade 20260828_0001
& '.\.worktrees\phase-1-foundation\.venv\Scripts\python.exe' -m alembic upgrade head
Remove-Item Env:DATABASE_URL
```

Expected: tests pass and all three migration commands exit 0.

- [ ] **Step 6: Commit**

```powershell
git add app/brand app/content app/media/models.py migrations tests/brand tests/content/test_content_model.py tests/media/test_media_model.py
git commit -m "feat: add content and voice persistence models"
```

---

### Task 2: Editable Brand Profile Domain

**Files:**
- Create: `app/brand/schemas.py`
- Create: `app/brand/repository.py`
- Create: `app/brand/service.py`
- Test: `tests/brand/test_brand_service.py`

**Interfaces:**
- Consumes: `BrandProfile` from Task 1.
- Produces: `BrandProfileInput`, `normalize_hashtag()`, `normalize_handle()`, `BrandRepository`, `BrandService.get_or_create()`, and `BrandService.update()`.

- [ ] **Step 1: Write normalization and service tests**

```python
from app.brand.repository import BrandRepository
from app.brand.schemas import BrandProfileInput
from app.brand.service import BrandService


def test_brand_input_normalizes_handle_claims_and_hashtags():
    data = BrandProfileInput(
        business_name="  هایکا  ",
        tagline=" تفاوت در جزئیات ",
        audience="کابینت‌سازان",
        tone_guidelines="حرفه‌ای",
        support_handle="hayka_poshtibani",
        default_cta="پیام دهید.",
        approved_claims=[" ارسال سراسر ایران ", "", "ارسال سراسر ایران"],
        default_hashtags=["#درب ممبران", "درب_ممبران", " هایکا "],
    )

    assert data.support_handle == "@hayka_poshtibani"
    assert data.approved_claims == ["ارسال سراسر ایران"]
    assert data.default_hashtags == ["درب_ممبران", "هایکا"]


def test_get_or_create_uses_safe_hayka_defaults_without_approved_sales_claims(db_session):
    profile = BrandService(BrandRepository(db_session)).get_or_create()

    assert profile.business_name == "هایکا"
    assert profile.support_handle == "@hayka_poshtibani"
    assert profile.approved_claims == []
```

- [ ] **Step 2: Run tests and verify RED**

Run:

```powershell
& '.\.worktrees\phase-1-foundation\.venv\Scripts\python.exe' -m pytest tests/brand/test_brand_service.py -v
```

Expected: imports fail because schemas/repository/service are absent.

- [ ] **Step 3: Implement schemas and normalization**

```python
def normalize_hashtag(value: str) -> str:
    normalized = "_".join(value.strip().removeprefix("#").split())
    return normalized.strip("_")


def normalize_handle(value: str) -> str:
    normalized = value.strip()
    if normalized and not normalized.startswith("@"):
        normalized = f"@{normalized}"
    return normalized
```

`BrandProfileInput` forbids extra fields; requires 2–200 characters for business name, at most 500 for tagline/audience/CTA, at most 2,000 for tone, at most 20 unique claims, and at most 20 unique hashtags. Empty list entries are removed and order is preserved.

- [ ] **Step 4: Implement repository and transactional service**

`BrandRepository.get()` selects the lowest ID profile. `BrandService.get_or_create()` inserts exactly one safe default with no approved commercial claim. `update()` changes the same row, commits, refreshes, rolls back on error, and never creates a second profile.

- [ ] **Step 5: Run tests and commit**

```powershell
& '.\.worktrees\phase-1-foundation\.venv\Scripts\python.exe' -m pytest tests/brand -v
git add app/brand tests/brand
git commit -m "feat: add editable brand profile domain"
```

---

### Task 3: Provider Contract and Deterministic Persian Template Provider

**Files:**
- Create: `app/content/schemas.py`
- Create: `app/content/providers.py`
- Test: `tests/content/test_template_provider.py`
- Test: `tests/content/test_content_schemas.py`

**Interfaces:**
- Produces: `ProductFacts`, `BrandFacts`, `ContentGenerationRequest`, `GeneratedContent`, `ContentProvider`, `TemplateContentProvider`, and `compose_caption()`.
- Consumes: normalized product and brand values; no database session.

- [ ] **Step 1: Write contract and deterministic-output tests**

```python
from decimal import Decimal

from app.content.providers import TemplateContentProvider, compose_caption
from app.content.schemas import BrandFacts, ContentGenerationRequest, ProductFacts


def request() -> ContentGenerationRequest:
    return ContentGenerationRequest(
        product=ProductFacts(
            name="درب ممبران مدل آریا",
            description="طراحی نئوکلاسیک با خطوط عمودی",
            price=Decimal("12500000"),
            availability="available",
            shipping_info="ارسال به سراسر ایران",
            attributes={"متریال": "MDF", "رنگ": "سفید"},
            tags=["درب ممبران", "نئوکلاسیک"],
        ),
        brand=BrandFacts(
            business_name="هایکا",
            tagline="تفاوت در جزئیات",
            audience="کابینت‌سازان حرفه‌ای",
            tone_guidelines="تخصصی و محترمانه",
            support_handle="@hayka_poshtibani",
            default_cta="برای مشاوره و ثبت سفارش پیام دهید.",
            approved_claims=[],
            default_hashtags=["هایکا"],
        ),
        user_brief="مدلی مناسب پروژه‌های نئوکلاسیک معرفی شود.",
        requested_angle="product_intro",
    )


def test_template_provider_adds_structure_without_unapproved_claims():
    generated = TemplateContentProvider().generate(request())
    caption = compose_caption(generated, request())

    assert generated.headline.startswith("✨")
    assert "✅ متریال: MDF" in generated.benefits
    assert "۱۸ ماه" not in caption
    assert "@hayka_poshtibani" in caption
    assert "#درب_ممبران" in caption
    assert caption == compose_caption(generated, request())
```

Add schema tests proving duplicate hashtags normalize to one value, unknown angles fail, empty benefits fail, more than six hashtags fail, and extra JSON keys fail.

- [ ] **Step 2: Run tests and verify RED**

```powershell
& '.\.worktrees\phase-1-foundation\.venv\Scripts\python.exe' -m pytest tests/content/test_template_provider.py tests/content/test_content_schemas.py -v
```

Expected: modules are absent.

- [ ] **Step 3: Implement strict Pydantic contracts**

Use `ConfigDict(extra="forbid")`. `requested_angle` is a `Literal` of the six design values. `GeneratedContent` requires a non-empty headline/body, 1–5 unique benefits, 0–6 unique hashtags, 0–6 unique emojis, a non-empty CTA, and echoes a valid `content_angle`.

The `ContentProvider` protocol is exactly:

```python
class ContentProvider(Protocol):
    name: str

    def generate(self, request: ContentGenerationRequest) -> GeneratedContent: ...
```

- [ ] **Step 4: Implement safe deterministic generation and caption composition**

Build benefits only from `attributes`, `shipping_info`, and `approved_claims`; if all are empty, use the manager-provided `user_brief` as the single benefit source. Normalize product tags plus default hashtags, preserve order, and keep the first six. Include price only from `ProductFacts.price`. Never insert warranty, delivery, discount, or inventory prose not present in the request.

Caption order is fixed:

```python
sections = [
    generated.headline,
    generated.body,
    "\n".join(generated.benefits),
    price_line,
    generated.cta,
    request.brand.support_handle,
    " ".join(f"#{tag}" for tag in generated.hashtags),
]
return "\n\n".join(section for section in sections if section)
```

- [ ] **Step 5: Run tests and commit**

```powershell
& '.\.worktrees\phase-1-foundation\.venv\Scripts\python.exe' -m pytest tests/content/test_template_provider.py tests/content/test_content_schemas.py -v
git add app/content/schemas.py app/content/providers.py tests/content
git commit -m "feat: add safe template content provider"
```

---

### Task 4: Draft Generation, Revision, Editing, and Approval Services

**Files:**
- Create: `app/content/repository.py`
- Create: `app/content/service.py`
- Test: `tests/content/test_content_service.py`

**Interfaces:**
- Consumes: `ProductRepository`, `BrandRepository`, Task 3 provider contract, and Task 1 models.
- Produces: `ContentRepository`, `ContentService.generate()`, `regenerate()`, `edit_caption()`, `approve()`, `reject()`, `ContentNotFound`, `ContentStateError`, and `ContentInputError`.
- Constructor: `ContentService(content_repository, product_repository, brand_repository, provider)`.

- [ ] **Step 1: Write service behavior tests**

Tests must cover these concrete behaviors:

```python
@pytest.fixture
def content_service(db_session):
    BrandService(BrandRepository(db_session)).get_or_create()
    return ContentService(
        ContentRepository(db_session),
        ProductRepository(db_session),
        BrandRepository(db_session),
        TemplateContentProvider(),
    )


@pytest.fixture
def product(db_session):
    item = Product(
        name="درب ممبران مدل آریا",
        description="طراحی نئوکلاسیک با خطوط عمودی",
        price=Decimal("12500000"),
        availability="available",
        shipping_info="ارسال به سراسر ایران",
        attributes={"متریال": "MDF"},
        tags=["درب ممبران", "نئوکلاسیک"],
        active=True,
    )
    db_session.add(item)
    db_session.commit()
    db_session.refresh(item)
    return item


@pytest.fixture
def draft(content_service, product):
    return content_service.generate(
        product.id,
        user_brief="روی طراحی نئوکلاسیک تمرکز شود.",
        requested_angle="product_intro",
    )
```

```python
def test_generate_persists_provider_snapshot_and_does_not_change_product(content_service, product):
    original_description = product.description
    draft = content_service.generate(
        product.id,
        user_brief="روی طراحی نئوکلاسیک تمرکز شود.",
        requested_angle="product_intro",
    )

    assert draft.status == "waiting_approval"
    assert draft.revision == 1
    assert draft.provider_name == "template"
    assert draft.provider_payload["headline"]
    assert product.description == original_description


def test_regenerate_creates_revision_without_overwriting_previous(content_service, draft):
    second = content_service.regenerate(draft.id)

    assert second.id != draft.id
    assert second.series_key == draft.series_key
    assert second.parent_id == draft.id
    assert second.revision == 2


def test_approving_new_revision_supersedes_old_approved_atomically(content_service, draft):
    content_service.approve(draft.id)
    second = content_service.regenerate(draft.id)
    content_service.approve(second.id)

    assert content_service.get(draft.id).status == "superseded"
    assert content_service.get(second.id).status == "approved"
```

Also test: inactive/missing product rejected, blank brief rejected, approved/superseded caption cannot be edited, rejected revision cannot be approved, rollback leaves previous approval unchanged when commit fails, and unknown draft raises `ContentNotFound`.

- [ ] **Step 2: Run tests and verify RED**

```powershell
& '.\.worktrees\phase-1-foundation\.venv\Scripts\python.exe' -m pytest tests/content/test_content_service.py -v
```

Expected: service and repository imports fail.

- [ ] **Step 3: Implement repository queries**

Provide exact operations: `get(id)`, `add(draft)`, `list_series(series_key)`, `latest_revision(series_key)`, `approved_in_series(series_key)`, `commit()`, `rollback()`, and `refresh(draft)`. Ordering is revision descending for history.

- [ ] **Step 4: Implement transactional service**

`generate()` creates a UUID4 `series_key`, revision 1, provider snapshot from `GeneratedContent.model_dump(mode="json")`, and composed caption. `regenerate()` copies the original brief/angle/product, keeps `series_key`, sets `parent_id`, and uses latest revision + 1. `edit_caption()` strips text and rejects fewer than 20 or more than 4,000 characters. `approve()` sets the current approved revision to `superseded` in the same transaction before marking the target approved with `datetime.now(UTC)`. Every mutation rolls back on exception.

- [ ] **Step 5: Run tests and commit**

```powershell
& '.\.worktrees\phase-1-foundation\.venv\Scripts\python.exe' -m pytest tests/content/test_content_service.py -v
git add app/content/repository.py app/content/service.py tests/content/test_content_service.py
git commit -m "feat: add versioned content approval service"
```

---

### Task 5: Byte-Preserving Private Voice Validation and Storage

**Files:**
- Create: `app/media/voice.py`
- Create: `app/media/voice_service.py`
- Test: `tests/media/test_voice.py`
- Test: `tests/media/test_voice_service.py`

**Interfaces:**
- Produces: `MAX_VOICE_BYTES`, `MAX_RECORDING_MS`, `ValidatedVoice`, `InvalidVoice`, `validate_voice()`, `save_voice()`, `VoiceRepository`, `VoiceService.attach_or_replace()`, and `VoiceService.delete()`.
- Consumes: `MediaAsset`, `ContentDraft`, and configured upload root.

- [ ] **Step 1: Write format/signature and preservation tests**

Use minimal real container headers:

```python
VOICE_CASES = [
    (b"ID3\x04\x00\x00\x00\x00\x00\x00payload", "voice.mp3", "audio/mpeg", ".mp3"),
    (b"OggS" + b"\x00" * 32, "voice.ogg", "audio/ogg", ".ogg"),
    (b"RIFF" + b"\x00" * 4 + b"WAVEfmt ", "voice.wav", "audio/wav", ".wav"),
    (b"\x1aE\xdf\xa3" + b"\x00" * 32, "voice.webm", "audio/webm", ".webm"),
    (b"\x00\x00\x00\x18ftypM4A " + b"\x00" * 24, "voice.m4a", "audio/mp4", ".m4a"),
]


@pytest.mark.parametrize("data,filename,mime,suffix", VOICE_CASES)
def test_supported_voice_is_saved_without_byte_changes(tmp_path, data, filename, mime, suffix):
    voice = validate_voice(data, filename, mime, duration_ms=1500)
    path = save_voice(tmp_path, 7, voice)

    assert path.suffix == suffix
    assert path.read_bytes() == data
    assert voice.sha256 == sha256(data).hexdigest()
```

Also test mismatched extension/MIME/signature, unsupported MIME, empty file, over 25 MiB, duration over 600,000 ms, absolute/traversal paths, cleanup on failed DB commit, successful replacement deleting the old file only after commit, and delete rollback preserving the file.

- [ ] **Step 2: Run tests and verify RED**

```powershell
& '.\.worktrees\phase-1-foundation\.venv\Scripts\python.exe' -m pytest tests/media/test_voice.py tests/media/test_voice_service.py -v
```

Expected: voice modules are absent.

- [ ] **Step 3: Implement validation and opaque private storage**

Match `.mp3`, `.ogg`, `.wav`, `.webm`, and `.m4a` to the declared MIME and signatures above. `save_voice(root, draft_id, voice)` writes to `root / "private" / "voices" / str(draft_id) / f"{uuid4().hex}{voice.suffix}"`, verifies the stored SHA-256, and returns the path. It must never use the supplied filename in the path.

- [ ] **Step 4: Implement transactional attach/replace/delete**

The repository owns SQLAlchemy operations; the service owns filesystem compensation. Store paths relative to `upload_dir`. On replacement, write the new file, update/insert metadata, commit, then unlink the old file. On failure before commit, rollback and unlink only the new file. On delete, commit record removal first, then unlink the old file.

- [ ] **Step 5: Run tests and commit**

```powershell
& '.\.worktrees\phase-1-foundation\.venv\Scripts\python.exe' -m pytest tests/media/test_voice.py tests/media/test_voice_service.py -v
git add app/media tests/media
git commit -m "feat: preserve and protect original voice uploads"
```

---

### Task 6: Brand and Content Studio Routes

**Files:**
- Create: `app/brand/routes.py`
- Create: `app/content/routes.py`
- Modify: `app/factory.py`
- Modify: `app/core/config.py`
- Modify: `tests/conftest.py`
- Test: `tests/admin/test_brand_routes.py`
- Test: `tests/admin/test_content_routes.py`

**Interfaces:**
- Produces authenticated endpoints `/admin/brand`, `/admin/content/new`, `/admin/content/{id}`, and POST actions `edit`, `regenerate`, `approve`, `reject`, `voice`, and `voice/delete`.
- Consumes all domain services from Tasks 2, 4, and 5.

- [ ] **Step 1: Write route integration tests**

Tests prove anonymous redirect, CSRF rejection, brand update, content generation from a real product, preview rendering, manual edit, regeneration, approval, rejection, and no Product mutation. The generation response redirects to `/admin/content/{id}` and the preview contains both `حالت آزمایشی — بدون OpenAI` and the normalized support handle.

Add this real-database fixture to `tests/conftest.py`:

```python
@pytest.fixture
def product(authenticated_client):
    from decimal import Decimal

    from app.catalog.models import Product

    session_factory = authenticated_client.app.state.session_factory
    with session_factory() as session:
        item = Product(
            name="درب ممبران مدل آریا",
            description="طراحی نئوکلاسیک با خطوط عمودی",
            price=Decimal("12500000"),
            availability="available",
            shipping_info="ارسال به سراسر ایران",
            attributes={"متریال": "MDF"},
            tags=["درب ممبران", "نئوکلاسیک"],
            active=True,
        )
        session.add(item)
        session.commit()
        session.refresh(item)
        return item
```

```python
def test_admin_generates_content_from_short_brief(
    authenticated_client, csrf_token, product
):
    response = authenticated_client.post(
        "/admin/content",
        data={
            "csrf_token": csrf_token,
            "product_id": str(product.id),
            "user_brief": "این مدل برای پروژه نئوکلاسیک معرفی شود.",
            "requested_angle": "product_intro",
        },
        follow_redirects=False,
    )

    assert response.status_code == 303
    preview = authenticated_client.get(response.headers["location"])
    assert "حالت آزمایشی — بدون OpenAI" in preview.text
    assert "#" in preview.text
```

- [ ] **Step 2: Run tests and verify RED**

```powershell
& '.\.worktrees\phase-1-foundation\.venv\Scripts\python.exe' -m pytest tests/admin/test_brand_routes.py tests/admin/test_content_routes.py -v
```

Expected: routes return 404.

- [ ] **Step 3: Register provider and routers in the app factory**

Add `content_provider: str = "template"` and `max_voice_bytes: int = 25 * 1024 * 1024` to Settings. In `create_app`, reject any value other than `template` for this phase, set `app.state.content_provider = TemplateContentProvider()`, create `upload_dir / "private" / "voices"`, and include both routers. Do not mount the private directory.

- [ ] **Step 4: Implement authenticated form routes**

Every POST calls `validate_csrf` before reading or mutating state. Convert Pydantic/domain exceptions into status 422 with Persian field feedback; use 404 for missing Product/Draft. Construct services per request from the existing DB session and app-state provider. Use 303 redirects after successful mutations.

- [ ] **Step 5: Add private range-capable voice response**

`GET /admin/content/{draft_id}/voice` requires `require_admin`, verifies asset ownership, resolves the path under `upload_dir/private/voices`, and returns `FileResponse` with the stored MIME, `Accept-Ranges: bytes`, and `Content-Disposition: inline`. Rely on current Starlette range handling and test both anonymous denial and authenticated byte equality.

- [ ] **Step 6: Run tests and commit**

```powershell
& '.\.worktrees\phase-1-foundation\.venv\Scripts\python.exe' -m pytest tests/admin/test_brand_routes.py tests/admin/test_content_routes.py -v
git add app/brand/routes.py app/content/routes.py app/factory.py app/core/config.py tests/conftest.py tests/admin
git commit -m "feat: expose protected content studio routes"
```

---

### Task 7: Persian Content Studio, Revision Preview, and Browser Recording UI

**Files:**
- Create: `app/templates/brand/form.html`
- Create: `app/templates/content/new.html`
- Create: `app/templates/content/detail.html`
- Create: `app/static/js/voice-recorder.js`
- Modify: `app/templates/base.html`
- Modify: `app/templates/products/detail.html`
- Modify: `app/static/css/app.css`
- Test: `tests/admin/test_content_ui.py`

**Interfaces:**
- Produces responsive RTL screens and browser hooks `data-voice-recorder`, `data-record-start`, `data-record-stop`, `data-record-preview`, `data-record-file`, and `data-record-duration`.
- Consumes route context from Task 6.

- [ ] **Step 1: Write rendered-UI tests**

Assert that navigation contains «استودیوی محتوا» and «تنظیمات برند», the product detail contains «ساخت محتوا», the preview contains product facts, final caption textarea, revision history, provider warning, and voice upload/record controls. Verify protected voice assets are never rendered as `/uploads/...` URLs.

- [ ] **Step 2: Run tests and verify RED**

```powershell
& '.\.worktrees\phase-1-foundation\.venv\Scripts\python.exe' -m pytest tests/admin/test_content_ui.py -v
```

Expected: missing links/templates/controls.

- [ ] **Step 3: Build templates using existing design tokens**

Use the current `panel`, `form-card`, `field`, `button`, `badge`, and responsive grid classes. Add a warning badge directly above every template-provider preview. The detail page must show original Product facts separately from editable Caption so users cannot confuse source data with generated copy.

Add a page-specific script block to `base.html`:

```html
{% block page_scripts %}{% endblock %}
```

and include `/static/js/voice-recorder.js` only from the content detail page.

- [ ] **Step 4: Implement MediaRecorder without automatic upload**

The script requests microphone permission only after the start button is clicked. Choose the first supported MIME from `audio/webm;codecs=opus`, `audio/ogg;codecs=opus`, then browser default. Stop automatically at 600,000 ms, create a Blob/File with an opaque local filename, assign it to the existing file input with `DataTransfer`, store elapsed milliseconds in the hidden duration field, and present an object-URL audio preview. Revoke old URLs on replacement and stop all media tracks after recording.

- [ ] **Step 5: Add focused responsive styles**

Create `.studio-grid`, `.source-facts`, `.caption-preview`, `.provider-warning`, `.revision-list`, `.voice-recorder`, `.recording-indicator`, and mobile rules. Keep the Vazirmatn font, existing color variables, keyboard focus styles, and reduced-motion behavior.

- [ ] **Step 6: Run route/UI tests and commit**

```powershell
& '.\.worktrees\phase-1-foundation\.venv\Scripts\python.exe' -m pytest tests/admin/test_content_ui.py tests/admin/test_content_routes.py -v
git add app/templates app/static tests/admin/test_content_ui.py
git commit -m "feat: add Persian content and voice studio UI"
```

---

### Task 8: Full Gate, Documentation, and Manual Handoff

**Files:**
- Modify: `.env.example`
- Modify: `README.md`
- Test: all existing and new tests.

**Interfaces:**
- Produces a reproducible setup, explicit experimental-provider limitation, voice privacy notes, and a manual acceptance checklist.
- Consumes all earlier tasks.

- [ ] **Step 1: Write documentation assertions**

Add a small test in `tests/test_documentation.py` that reads `.env.example` and README and asserts they mention `CONTENT_PROVIDER=template`, the experimental label, private unchanged Voice, the 25 MiB/10-minute limits, and the future OpenAI API requirement.

- [ ] **Step 2: Run the documentation test and verify RED**

```powershell
& '.\.worktrees\phase-1-foundation\.venv\Scripts\python.exe' -m pytest tests/test_documentation.py -v
```

Expected: missing documentation strings.

- [ ] **Step 3: Update configuration and runbook**

Add only non-secret values to `.env.example`:

```dotenv
CONTENT_PROVIDER=template
MAX_VOICE_BYTES=26214400
```

README must explain that template output validates workflow, not OpenAI quality; document brand setup, draft revisions, approval semantics, microphone HTTPS/localhost requirements, private Voice storage, backup inclusion of `uploads/private`, and the eight-step manual acceptance flow from the design.

- [ ] **Step 4: Run the complete automated gate**

```powershell
& '.\.worktrees\phase-1-foundation\.venv\Scripts\python.exe' -m ruff check app tests
& '.\.worktrees\phase-1-foundation\.venv\Scripts\python.exe' -m pytest -v --cov=app --cov-report=term-missing
$env:DATABASE_URL='sqlite:///./.tmp/phase2-gate.db'
& '.\.worktrees\phase-1-foundation\.venv\Scripts\python.exe' -m alembic upgrade head
& '.\.worktrees\phase-1-foundation\.venv\Scripts\python.exe' -m alembic downgrade base
& '.\.worktrees\phase-1-foundation\.venv\Scripts\python.exe' -m alembic upgrade head
Remove-Item Env:DATABASE_URL
git diff --check
```

Expected: Ruff clean, all tests pass, migration round-trip succeeds, and no whitespace errors.

- [ ] **Step 5: Run browser smoke test**

Start the app on a non-conflicting local port, sign in, update brand profile, generate from a short brief, edit, regenerate, approve, record a short Voice, upload it, replay it, replace it, and confirm the browser Network panel never requests a voice file under `/uploads`.

- [ ] **Step 6: Commit the completed phase**

```powershell
git add .env.example README.md tests/test_documentation.py
git commit -m "docs: add phase 2 content and voice runbook"
```

- [ ] **Step 7: Prepare user handoff**

Report exact test counts, Ruff result, migration result, browser-smoke result, branch/commit IDs, experimental-provider limitation, and the numbered manual test checklist. Do not call the OpenAI-dependent portion complete.

---

## Plan Self-Review Checklist

- Every requirement in the phase design maps to one of Tasks 1–8.
- Data names are consistent: `series_key`, `revision`, `provider_payload`, `final_caption`, `voice_original`.
- Provider output remains separate from edited caption.
- Voice original bytes are verified by SHA-256 and never publicly mounted.
- No task requires an OpenAI key, Telegram/Bale/Rubika token, FFmpeg, or network access.
- Real OpenAI text/image integration remains the next independent plan after credentials arrive.
