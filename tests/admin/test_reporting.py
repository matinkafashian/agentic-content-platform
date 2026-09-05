from datetime import UTC, datetime, timedelta

from app.admin.reporting import DashboardReportingService
from app.content.models import ContentDraft, DraftStatus
from app.publishing.models import Publication, PublicationStatus
from app.support.models import SupportInteraction


def test_dashboard_report_aggregates_delivery_and_support_metrics(db_session):
    now = datetime(2026, 9, 5, 12, tzinfo=UTC)
    db_session.add_all(
        [
            Publication(
                bundle_id=1,
                platform="telegram",
                destination="@test",
                status=PublicationStatus.SUCCEEDED.value,
                scheduled_for=now - timedelta(days=1),
                idempotency_key="publication-success",
                created_at=now - timedelta(days=1),
                updated_at=now - timedelta(days=1),
                published_at=now - timedelta(days=1),
            ),
            Publication(
                bundle_id=1,
                platform="telegram",
                destination="@test",
                status=PublicationStatus.FAILED.value,
                scheduled_for=now - timedelta(days=1),
                idempotency_key="publication-failure",
                safe_error_message="توکن کانال معتبر نیست.",
                created_at=now - timedelta(days=1),
                updated_at=now - timedelta(days=1),
            ),
            Publication(
                bundle_id=1,
                platform="bale",
                destination="@test",
                status=PublicationStatus.SCHEDULED.value,
                scheduled_for=now + timedelta(hours=1),
                idempotency_key="publication-pending",
                created_at=now,
                updated_at=now,
            ),
            SupportInteraction(
                platform="telegram",
                external_update_id="support-1",
                external_message_id="message-1",
                chat_id="chat-1",
                user_id="user-1",
                question="زمان تولید چقدر است؟",
                decision="grounded",
                reply_text="پاسخ تست",
                status="answered",
                created_at=now - timedelta(seconds=3),
                updated_at=now,
            ),
            SupportInteraction(
                platform="telegram",
                external_update_id="support-start",
                external_message_id="message-start",
                chat_id="chat-start",
                user_id="user-start",
                question="/start",
                decision="general_guidance",
                reply_text="خوش آمدید",
                status="answered",
                created_at=now,
                updated_at=now,
            ),
            SupportInteraction(
                platform="rubika",
                external_update_id="support-2",
                external_message_id="message-2",
                chat_id="chat-2",
                user_id="user-2",
                question="نیاز به مشاور دارم",
                decision="handoff",
                reply_text="با ادمین تماس بگیرید",
                status="answered",
                needs_admin=True,
                created_at=now - timedelta(seconds=1),
                updated_at=now,
            ),
            ContentDraft(
                product_id=1,
                series_key="draft-series",
                revision=1,
                user_brief="توضیح تست",
                requested_angle="introduction",
                provider_name="template",
                provider_payload={},
                final_caption="متن تست",
                status=DraftStatus.APPROVED.value,
                created_at=now,
                updated_at=now,
            ),
        ]
    )
    db_session.commit()

    report = DashboardReportingService(db_session).build(days=7, now=now)

    assert report.successful_publications == 1
    assert report.failed_publications == 1
    assert report.pending_publications == 1
    assert report.publication_success_rate == 50
    assert report.support_questions == 2
    assert report.admin_handoffs == 1
    assert report.average_response_seconds == 2.0
    assert report.created_drafts == 1
    assert report.approved_drafts == 1
    assert report.latest_failures[0].message == "توکن کانال معتبر نیست."
    assert report.platforms[0].label == "تلگرام"
    assert report.platforms[0].success_rate == 50
    assert report.daily[-1].label == "امروز"


def test_dashboard_report_normalizes_unsupported_range(db_session):
    report = DashboardReportingService(db_session).build(days=365)

    assert report.range_days == 30
    assert len(report.daily) == 30
