from datetime import UTC, datetime
from uuid import uuid4

from pydantic import ValidationError

from app.brand.models import BrandProfile
from app.brand.repository import BrandRepository
from app.catalog.models import Product
from app.catalog.repository import ProductRepository
from app.content.models import ContentDraft, DraftStatus
from app.content.providers import (
    ContentProvider,
    compose_caption,
    compose_manual_caption,
)
from app.content.repository import ContentRepository
from app.content.schemas import (
    BrandFacts,
    ContentAngle,
    ContentGenerationRequest,
    ProductFacts,
)


class ContentNotFound(LookupError):
    def __init__(self, draft_id: int) -> None:
        super().__init__(f"Content draft {draft_id} was not found")
        self.draft_id = draft_id


class ContentInputError(ValueError):
    pass


class ContentStateError(ValueError):
    pass


class ContentService:
    def __init__(
        self,
        content_repository: ContentRepository,
        product_repository: ProductRepository,
        brand_repository: BrandRepository,
        provider: ContentProvider,
    ) -> None:
        self.repository = content_repository
        self.product_repository = product_repository
        self.brand_repository = brand_repository
        self.provider = provider

    def get(self, draft_id: int) -> ContentDraft:
        draft = self.repository.get(draft_id)
        if draft is None:
            raise ContentNotFound(draft_id)
        return draft

    def history(self, draft_id: int) -> list[ContentDraft]:
        draft = self.get(draft_id)
        return self.repository.list_series(draft.series_key)

    def generate(
        self,
        product_id: int,
        *,
        user_brief: str,
        requested_angle: ContentAngle,
        content_mode: str = "ai",
    ) -> ContentDraft:
        normalized_mode = content_mode.strip().lower()
        normalized_text = user_brief.strip()
        if normalized_mode not in {"ai", "manual"}:
            raise ContentInputError("روش آماده‌سازی متن معتبر نیست")
        if normalized_mode == "ai" and not normalized_text:
            raise ContentInputError("برای تولید با هوش مصنوعی، توضیح کوتاه را وارد کنید")
        if (
            normalized_mode == "manual"
            and normalized_text
            and not 20 <= len(normalized_text) <= 3500
        ):
            raise ContentInputError("متن کامل باید بین ۲۰ تا ۳۵۰۰ نویسه باشد")

        request = self._generation_request(
            product_id, normalized_text, requested_angle
        )
        if normalized_mode == "manual":
            provider_name = "manual"
            provider_payload = {"content_mode": "manual"}
            final_caption = (
                compose_manual_caption(normalized_text, request)
                if normalized_text
                else ""
            )
        else:
            generated = self.provider.generate(request)
            provider_name = self.provider.name
            provider_payload = generated.model_dump(mode="json")
            final_caption = compose_caption(generated, request)
        draft = ContentDraft(
            product_id=product_id,
            parent_id=None,
            series_key=str(uuid4()),
            revision=1,
            user_brief=request.user_brief,
            requested_angle=request.requested_angle,
            provider_name=provider_name,
            provider_payload=provider_payload,
            final_caption=final_caption,
            status=DraftStatus.WAITING_APPROVAL.value,
        )
        return self._persist_new(draft)

    def regenerate(self, draft_id: int) -> ContentDraft:
        previous = self.get(draft_id)
        if previous.provider_name == "manual":
            raise ContentStateError("متن دستی بازتولید نمی‌شود؛ همان متن را ویرایش کنید")
        request = self._generation_request(
            previous.product_id,
            previous.user_brief,
            previous.requested_angle,
            exclude_series_key=previous.series_key,
        )
        generated = self.provider.generate(request)
        latest = self.repository.latest_revision(previous.series_key)
        revision = 1 if latest is None else latest.revision + 1
        draft = ContentDraft(
            product_id=previous.product_id,
            parent_id=previous.id,
            series_key=previous.series_key,
            revision=revision,
            user_brief=request.user_brief,
            requested_angle=request.requested_angle,
            provider_name=self.provider.name,
            provider_payload=generated.model_dump(mode="json"),
            final_caption=compose_caption(generated, request),
            status=DraftStatus.WAITING_APPROVAL.value,
        )
        return self._persist_new(draft)

    def edit_caption(self, draft_id: int, caption: str) -> ContentDraft:
        draft = self.get(draft_id)
        if draft.status in {
            DraftStatus.APPROVED.value,
            DraftStatus.SUPERSEDED.value,
        }:
            raise ContentStateError("نسخه تأییدشده یا منقضی قابل ویرایش نیست")
        normalized = caption.strip()
        if normalized and not 20 <= len(normalized) <= 4000:
            raise ContentInputError("کپشن باید بین ۲۰ تا ۴۰۰۰ نویسه باشد")
        try:
            draft.final_caption = normalized
            self.repository.commit()
            self.repository.refresh(draft)
        except Exception:
            self.repository.rollback()
            raise
        return draft

    def approve(self, draft_id: int) -> ContentDraft:
        draft = self.get(draft_id)
        if draft.status not in {
            DraftStatus.DRAFT.value,
            DraftStatus.WAITING_APPROVAL.value,
        }:
            raise ContentStateError("این نسخه آماده تأیید نیست")
        try:
            current = self.repository.approved_in_series(draft.series_key)
            if current is not None and current.id != draft.id:
                current.status = DraftStatus.SUPERSEDED.value
            draft.status = DraftStatus.APPROVED.value
            draft.approved_at = datetime.now(UTC)
            self.repository.commit()
            self.repository.refresh(draft)
        except Exception:
            self.repository.rollback()
            raise
        return draft

    def reject(self, draft_id: int) -> ContentDraft:
        draft = self.get(draft_id)
        if draft.status not in {
            DraftStatus.DRAFT.value,
            DraftStatus.WAITING_APPROVAL.value,
        }:
            raise ContentStateError("این نسخه قابل رد نیست")
        try:
            draft.status = DraftStatus.REJECTED.value
            draft.approved_at = None
            self.repository.commit()
            self.repository.refresh(draft)
        except Exception:
            self.repository.rollback()
            raise
        return draft

    def _generation_request(
        self,
        product_id: int,
        user_brief: str,
        requested_angle: str,
        *,
        exclude_series_key: str | None = None,
    ) -> ContentGenerationRequest:
        product = self.product_repository.get(product_id)
        if product is None or not product.active:
            raise ContentInputError("محصول فعال پیدا نشد")
        brand = self.brand_repository.get()
        if brand is None:
            raise ContentInputError("پروفایل برند هنوز تنظیم نشده است")
        try:
            style_examples: list[str] = []
            if (
                self.repository.approved_caption_count(
                    exclude_series_key=exclude_series_key
                )
                >= 20
            ):
                style_examples = self.repository.recent_approved_captions(
                    product_id,
                    exclude_series_key=exclude_series_key,
                    limit=3,
                )
            return ContentGenerationRequest(
                product=self._product_facts(product),
                brand=self._brand_facts(brand),
                user_brief=user_brief,
                requested_angle=requested_angle,
                style_examples=style_examples,
            )
        except ValidationError as exc:
            raise ContentInputError("اطلاعات تولید محتوا کامل یا معتبر نیست") from exc

    @staticmethod
    def _product_facts(product: Product) -> ProductFacts:
        return ProductFacts(
            name=product.name,
            description=product.description,
            availability=product.availability,
            shipping_info=product.shipping_info,
            attributes=product.attributes,
            tags=product.tags,
        )

    @staticmethod
    def _brand_facts(brand: BrandProfile) -> BrandFacts:
        return BrandFacts(
            business_name=brand.business_name,
            tagline=brand.tagline,
            audience=brand.audience,
            tone_guidelines=brand.tone_guidelines,
            support_handle=brand.support_handle,
            default_cta=brand.default_cta,
            approved_claims=brand.approved_claims,
            default_hashtags=brand.default_hashtags,
        )

    def _persist_new(self, draft: ContentDraft) -> ContentDraft:
        try:
            self.repository.add(draft)
            self.repository.commit()
            self.repository.refresh(draft)
        except Exception:
            self.repository.rollback()
            raise
        return draft
