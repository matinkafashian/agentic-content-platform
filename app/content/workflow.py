from collections.abc import Mapping
from dataclasses import dataclass


@dataclass(frozen=True)
class WorkflowStep:
    key: str
    label: str
    status: str
    status_label: str
    description: str
    anchor: str


@dataclass(frozen=True)
class WorkflowAction:
    label: str
    href: str
    description: str


@dataclass(frozen=True)
class ContentWorkflowState:
    steps: tuple[WorkflowStep, ...]
    current_key: str
    next_action: WorkflowAction

    @property
    def by_key(self) -> Mapping[str, WorkflowStep]:
        return {step.key: step for step in self.steps}


def build_content_workflow(
    *,
    draft_status: str,
    publishing_mode: str,
    has_original_image: bool,
    has_edited_image: bool,
    image_editor_available: bool,
    has_voice: bool,
    has_bundle: bool,
    product_edit_url: str,
) -> ContentWorkflowState:
    """Map persisted content state to one current UI step and next action."""
    automatic = publishing_mode == "automatic"
    terminal = draft_status in {"rejected", "superseded"}

    if terminal:
        current_key = "caption"
        action = WorkflowAction(
            "ساخت نسخه جدید برای ویرایش",
            "#caption-studio",
            "این نسخه دیگر قابل تغییر یا انتشار نیست؛ یک نسخه تازه بسازید.",
        )
    elif has_bundle:
        current_key = "bundle"
        if publishing_mode == "paused":
            action = WorkflowAction(
                "فعال‌کردن انتشار",
                "/admin/publishing",
                "بسته آماده است، اما ارسال‌ها در تنظیمات انتشار متوقف شده‌اند.",
            )
        else:
            action = WorkflowAction(
                "تنظیم مقصد و زمان انتشار",
                "#publishing-bundle",
                "پلتفرم، کانال مقصد و زمان ارسال این بسته را مشخص کنید.",
            )
    elif not automatic and draft_status != "approved":
        current_key = "caption"
        action = WorkflowAction(
            "بررسی و تأیید متن",
            "#caption-studio",
            "کپشن را بررسی کنید و پس از اطمینان، تأیید نهایی را بزنید.",
        )
    elif not has_original_image:
        current_key = "image"
        action = WorkflowAction(
            "ثبت تصویر اصلی محصول",
            product_edit_url,
            "ساخت بسته بدون تصویر اصلی محصول امکان‌پذیر نیست.",
        )
    elif image_editor_available and not has_edited_image and not automatic:
        current_key = "image"
        action = WorkflowAction(
            "ساخت نسخه استودیویی",
            "#image-studio",
            "نسخه استودیویی را بسازید و با تصویر اصلی مقایسه کنید.",
        )
    else:
        current_key = "bundle"
        action = WorkflowAction(
            "ساخت بسته نهایی",
            "#publishing-bundle",
            "متن، تصویر و وویس اختیاری را در یک نسخه ثابت آماده انتشار کنید.",
        )

    caption_step = _caption_step(draft_status, automatic, current_key)
    image_step = _image_step(
        has_original_image=has_original_image,
        has_edited_image=has_edited_image,
        image_editor_available=image_editor_available,
        automatic=automatic,
        current_key=current_key,
    )
    voice_step = WorkflowStep(
        key="voice",
        label="وویس",
        status="complete" if has_voice else "optional",
        status_label="پیوست شده" if has_voice else "اختیاری",
        description=(
            "صدای ضبط‌شده همراه همین محتوا ارسال می‌شود."
            if has_voice
            else "در صورت نیاز صدای اصلی کارفرما را ضبط کنید؛ نبود آن مانع انتشار نیست."
        ),
        anchor="#voice-studio",
    )
    bundle_step = _bundle_step(
        has_bundle=has_bundle,
        publishing_mode=publishing_mode,
        current_key=current_key,
    )

    return ContentWorkflowState(
        steps=(caption_step, image_step, voice_step, bundle_step),
        current_key=current_key,
        next_action=action,
    )


def _caption_step(
    draft_status: str, automatic: bool, current_key: str
) -> WorkflowStep:
    if current_key == "caption":
        status = "current"
        status_label = (
            "نیازمند نسخه جدید"
            if draft_status in {"rejected", "superseded"}
            else "نیازمند بررسی"
        )
    elif draft_status == "approved":
        status = "complete"
        status_label = "تأیید شده"
    elif automatic:
        status = "pending"
        status_label = "تأیید خودکار"
    else:
        status = "pending"
        status_label = "در انتظار"
    return WorkflowStep(
        key="caption",
        label="متن",
        status=status,
        status_label=status_label,
        description=(
            "کپشن نهایی، ایموجی‌ها و هشتگ‌ها را بررسی کنید."
            if not automatic or draft_status == "approved"
            else "هنگام ساخت بسته، متن به‌صورت خودکار تأیید می‌شود."
        ),
        anchor="#caption-studio",
    )


def _image_step(
    *,
    has_original_image: bool,
    has_edited_image: bool,
    image_editor_available: bool,
    automatic: bool,
    current_key: str,
) -> WorkflowStep:
    if not has_original_image:
        status = "current" if current_key == "image" else "blocked"
        status_label = "تصویر اصلی لازم است"
        description = "ابتدا یک تصویر معتبر برای محصول ثبت کنید."
    elif has_edited_image:
        status = "complete"
        status_label = "نسخه استودیویی آماده"
        description = "نسخه ویرایش‌شده ذخیره شده و قابل بررسی است."
    elif not image_editor_available:
        status = "complete"
        status_label = "تصویر اصلی آماده"
        description = "در محیط فعلی، تصویر اصلی محصول در بسته استفاده می‌شود."
    elif automatic:
        status = "pending"
        status_label = "تولید خودکار"
        description = "نسخه استودیویی هنگام ساخت بسته تولید می‌شود."
    else:
        status = "current" if current_key == "image" else "pending"
        status_label = "نیازمند ساخت" if current_key == "image" else "در انتظار"
        description = "نسخه استودیویی را بسازید و با تصویر اصلی مقایسه کنید."
    return WorkflowStep(
        key="image",
        label="تصویر",
        status=status,
        status_label=status_label,
        description=description,
        anchor="#image-studio",
    )


def _bundle_step(
    *, has_bundle: bool, publishing_mode: str, current_key: str
) -> WorkflowStep:
    if has_bundle:
        status = "current"
        status_label = (
            "انتشار متوقف است"
            if publishing_mode == "paused"
            else "آماده انتشار"
        )
        description = "نسخه ثابت ساخته شده؛ اکنون مقصد و زمان ارسال را تعیین کنید."
    elif current_key == "bundle":
        status = "current"
        status_label = "آماده بسته‌بندی"
        description = "از متن، تصویر و وویس اختیاری یک بسته ثابت بسازید."
    else:
        status = "blocked"
        status_label = "پس از تکمیل مراحل قبل"
        description = "پس از آماده‌شدن متن و تصویر فعال می‌شود."
    return WorkflowStep(
        key="bundle",
        label="بسته و انتشار",
        status=status,
        status_label=status_label,
        description=description,
        anchor="#publishing-bundle",
    )
