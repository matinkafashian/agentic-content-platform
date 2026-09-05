from app.brand.models import BrandProfile
from app.brand.repository import BrandRepository
from app.brand.schemas import BrandProfileInput

DEFAULT_BRAND = BrandProfileInput(
    business_name="هایکا",
    tagline="تفاوت در جزئیات",
    audience="کابینت‌سازان حرفه‌ای",
    tone_guidelines="تخصصی، حرفه‌ای، مطمئن و روان",
    support_handle="@hayka_poshtibani",
    support_phone="+989183962948",
    default_cta="برای دریافت مشاوره و ثبت سفارش پیام دهید.",
    approved_claims=[],
    default_hashtags=["هایکا", "درب_ممبران", "نئوکلاسیک"],
)


class BrandService:
    def __init__(self, repository: BrandRepository) -> None:
        self.repository = repository

    def get_or_create(self) -> BrandProfile:
        existing = self.repository.get()
        if existing is not None:
            return existing

        profile = BrandProfile(**DEFAULT_BRAND.model_dump())
        try:
            self.repository.add(profile)
            self.repository.commit()
            self.repository.refresh(profile)
        except Exception:
            self.repository.rollback()
            raise
        return profile

    def update(self, data: BrandProfileInput) -> BrandProfile:
        profile = self.get_or_create()
        try:
            for field, value in data.model_dump().items():
                setattr(profile, field, value)
            self.repository.commit()
            self.repository.refresh(profile)
        except Exception:
            self.repository.rollback()
            raise
        return profile
