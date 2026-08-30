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
    assert profile.created_at.tzinfo is not None

