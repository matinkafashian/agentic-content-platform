import pytest

from app.content.workflow import build_content_workflow


def workflow(**overrides):
    values = {
        "draft_status": "waiting_approval",
        "publishing_mode": "manual_approval",
        "has_original_image": True,
        "has_edited_image": False,
        "image_editor_available": True,
        "has_voice": False,
        "has_bundle": False,
    }
    values.update(overrides)
    return build_content_workflow(**values)


@pytest.mark.parametrize(
    ("overrides", "current_key", "action_label", "action_href"),
    [
        ({}, "caption", "بررسی و تأیید متن", "#caption-studio"),
        (
            {"draft_status": "approved"},
            "bundle",
            "ساخت بسته نهایی",
            "#publishing-bundle",
        ),
        (
            {"publishing_mode": "automatic"},
            "bundle",
            "ساخت بسته نهایی",
            "#publishing-bundle",
        ),
        (
            {
                "draft_status": "approved",
                "has_original_image": False,
            },
            "bundle",
            "ساخت بسته نهایی",
            "#publishing-bundle",
        ),
        (
            {"draft_status": "rejected"},
            "caption",
            "ساخت نسخه جدید برای ویرایش",
            "#caption-studio",
        ),
        (
            {
                "draft_status": "approved",
                "has_edited_image": True,
                "has_bundle": True,
            },
            "bundle",
            "تنظیم مقصد و زمان انتشار",
            "#publishing-bundle",
        ),
    ],
)
def test_workflow_selects_one_current_step_and_one_next_action(
    overrides, current_key, action_label, action_href
):
    state = workflow(**overrides)

    assert state.current_key == current_key
    assert state.next_action.label == action_label
    assert state.next_action.href == action_href
    assert sum(step.status == "current" for step in state.steps) == 1


def test_voice_is_complete_when_saved_and_optional_when_absent():
    saved = workflow(has_voice=True)
    absent = workflow(has_voice=False)

    assert saved.by_key["voice"].status == "complete"
    assert saved.by_key["voice"].status_label == "پیوست شده"
    assert absent.by_key["voice"].status == "optional"
    assert absent.by_key["voice"].status_label == "اختیاری"


def test_automatic_mode_explains_deferred_approval_and_optional_image_editing():
    state = workflow(publishing_mode="automatic")

    assert state.by_key["caption"].status_label == "تأیید خودکار"
    assert state.by_key["image"].status_label == "ویرایش اختیاری"
    assert state.by_key["bundle"].status == "current"


def test_original_image_is_enough_when_image_editor_is_unavailable():
    state = workflow(draft_status="approved", image_editor_available=False)

    assert state.current_key == "bundle"
    assert state.by_key["image"].status == "complete"
    assert state.by_key["image"].status_label == "تصویر اصلی آماده"
