from collections import Counter
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.content.models import ContentDraft, DraftStatus
from app.publishing.models import Publication, PublicationStatus
from app.support.models import SupportInteraction

PLATFORM_LABELS = {
    "telegram": "تلگرام",
    "bale": "بله",
    "rubika": "روبیکا",
    "whatsapp": "واتساپ",
}

DECISION_LABELS = {
    "grounded": "پاسخ از اطلاعات کسب‌وکار",
    "general_guidance": "راهنمایی عمومی مرتبط",
    "clarification": "درخواست توضیح بیشتر",
    "handoff": "ارجاع به ادمین",
    "irrelevant": "سؤال نامرتبط",
    "unsupported": "پیام غیرمتنی",
    "ignored": "نادیده گرفته‌شده",
    "": "بدون تصمیم",
}


@dataclass(frozen=True, slots=True)
class PlatformMetric:
    key: str
    label: str
    succeeded: int
    failed: int
    pending: int
    success_rate: int

    @property
    def total(self) -> int:
        return self.succeeded + self.failed + self.pending


@dataclass(frozen=True, slots=True)
class DecisionMetric:
    key: str
    label: str
    count: int
    share: int


@dataclass(frozen=True, slots=True)
class DailyMetric:
    label: str
    publications: int
    questions: int
    publication_height: int
    question_height: int


@dataclass(frozen=True, slots=True)
class FailureMetric:
    publication_id: int
    platform_label: str
    message: str
    created_at: datetime


@dataclass(frozen=True, slots=True)
class DashboardReport:
    range_days: int
    range_label: str
    successful_publications: int
    failed_publications: int
    pending_publications: int
    publication_success_rate: int
    support_questions: int
    support_failures: int
    admin_handoffs: int
    average_response_seconds: float | None
    created_drafts: int
    approved_drafts: int
    platforms: tuple[PlatformMetric, ...]
    decisions: tuple[DecisionMetric, ...]
    daily: tuple[DailyMetric, ...]
    latest_failures: tuple[FailureMetric, ...]


class DashboardReportingService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def build(self, *, days: int = 30, now: datetime | None = None) -> DashboardReport:
        if days not in {7, 30}:
            days = 30
        current = now or datetime.now(UTC)
        since = current - timedelta(days=days)

        publication_counts = self._publication_counts(since)
        platforms = self._platform_metrics(publication_counts)
        successful = sum(item.succeeded for item in platforms)
        failed = sum(item.failed for item in platforms)
        pending = sum(item.pending for item in platforms)
        terminal = successful + failed

        support_counts = self._support_counts(since)
        support_questions = sum(support_counts.values())
        decisions = self._decision_metrics(support_counts, support_questions)
        support_failures = self._scalar_count(
            SupportInteraction.id,
            SupportInteraction.created_at >= since,
            SupportInteraction.question.not_like("/start%"),
            SupportInteraction.status == "failed",
        )
        admin_handoffs = self._scalar_count(
            SupportInteraction.id,
            SupportInteraction.created_at >= since,
            SupportInteraction.question.not_like("/start%"),
            SupportInteraction.needs_admin.is_(True),
        )

        return DashboardReport(
            range_days=days,
            range_label=f"{days} روز گذشته",
            successful_publications=successful,
            failed_publications=failed,
            pending_publications=pending,
            publication_success_rate=round((successful / terminal) * 100) if terminal else 0,
            support_questions=support_questions,
            support_failures=support_failures,
            admin_handoffs=admin_handoffs,
            average_response_seconds=self._average_response_seconds(since),
            created_drafts=self._scalar_count(
                ContentDraft.id,
                ContentDraft.created_at >= since,
            ),
            approved_drafts=self._scalar_count(
                ContentDraft.id,
                ContentDraft.created_at >= since,
                ContentDraft.status == DraftStatus.APPROVED.value,
            ),
            platforms=platforms,
            decisions=decisions,
            daily=self._daily_metrics(since, current, days),
            latest_failures=self._latest_failures(since),
        )

    def _publication_counts(self, since: datetime) -> Counter[tuple[str, str]]:
        rows = self.session.execute(
            select(Publication.platform, Publication.status, func.count(Publication.id))
            .where(Publication.created_at >= since)
            .group_by(Publication.platform, Publication.status)
        )
        return Counter({(platform, status): count for platform, status, count in rows})

    @staticmethod
    def _platform_metrics(
        counts: Counter[tuple[str, str]],
    ) -> tuple[PlatformMetric, ...]:
        metrics: list[PlatformMetric] = []
        for key, label in PLATFORM_LABELS.items():
            succeeded = counts[(key, PublicationStatus.SUCCEEDED.value)]
            failed = counts[(key, PublicationStatus.FAILED.value)]
            pending = sum(
                counts[(key, status.value)]
                for status in (
                    PublicationStatus.SCHEDULED,
                    PublicationStatus.PUBLISHING,
                    PublicationStatus.RETRY_SCHEDULED,
                )
            )
            terminal = succeeded + failed
            metrics.append(
                PlatformMetric(
                    key=key,
                    label=label,
                    succeeded=succeeded,
                    failed=failed,
                    pending=pending,
                    success_rate=round((succeeded / terminal) * 100) if terminal else 0,
                )
            )
        return tuple(metrics)

    def _support_counts(self, since: datetime) -> Counter[str]:
        rows = self.session.execute(
            select(SupportInteraction.decision, func.count(SupportInteraction.id))
            .where(
                SupportInteraction.created_at >= since,
                SupportInteraction.question.not_like("/start%"),
            )
            .group_by(SupportInteraction.decision)
        )
        return Counter({decision or "": count for decision, count in rows})

    @staticmethod
    def _decision_metrics(counts: Counter[str], total: int) -> tuple[DecisionMetric, ...]:
        metrics = [
            DecisionMetric(
                key=key or "unknown",
                label=DECISION_LABELS.get(key, key or DECISION_LABELS[""]),
                count=count,
                share=round((count / total) * 100) if total else 0,
            )
            for key, count in counts.most_common()
            if count
        ]
        return tuple(metrics)

    def _average_response_seconds(self, since: datetime) -> float | None:
        rows = self.session.execute(
            select(SupportInteraction.created_at, SupportInteraction.updated_at)
            .where(
                SupportInteraction.created_at >= since,
                SupportInteraction.question.not_like("/start%"),
                SupportInteraction.status == "answered",
            )
            .order_by(SupportInteraction.created_at.desc())
            .limit(500)
        )
        durations = [
            max(0.0, (updated_at - created_at).total_seconds())
            for created_at, updated_at in rows
        ]
        if not durations:
            return None
        return round(sum(durations) / len(durations), 1)

    def _daily_metrics(
        self,
        since: datetime,
        current: datetime,
        days: int,
    ) -> tuple[DailyMetric, ...]:
        publication_dates = self.session.scalars(
            select(Publication.created_at).where(Publication.created_at >= since)
        )
        question_dates = self.session.scalars(
            select(SupportInteraction.created_at).where(
                SupportInteraction.created_at >= since,
                SupportInteraction.question.not_like("/start%"),
            )
        )
        publication_daily = Counter(value.date() for value in publication_dates)
        question_daily = Counter(value.date() for value in question_dates)
        dates = [current.date() - timedelta(days=offset) for offset in reversed(range(days))]
        maximum = max(
            [1]
            + [publication_daily[item] for item in dates]
            + [question_daily[item] for item in dates]
        )
        return tuple(
            DailyMetric(
                label=self._day_label(day, current.date()),
                publications=publication_daily[day],
                questions=question_daily[day],
                publication_height=round((publication_daily[day] / maximum) * 100),
                question_height=round((question_daily[day] / maximum) * 100),
            )
            for day in dates
        )

    def _latest_failures(self, since: datetime) -> tuple[FailureMetric, ...]:
        rows = self.session.scalars(
            select(Publication)
            .where(
                Publication.created_at >= since,
                Publication.status == PublicationStatus.FAILED.value,
            )
            .order_by(Publication.updated_at.desc())
            .limit(5)
        )
        return tuple(
            FailureMetric(
                publication_id=item.id,
                platform_label=PLATFORM_LABELS.get(item.platform, item.platform),
                message=item.safe_error_message or "ارسال ناموفق بود؛ تنظیمات کانال را بررسی کنید.",
                created_at=item.updated_at,
            )
            for item in rows
        )

    def _scalar_count(self, column: object, *conditions: object) -> int:
        statement = select(func.count(column))
        if conditions:
            statement = statement.where(*conditions)
        return int(self.session.scalar(statement) or 0)

    @staticmethod
    def _day_label(value: date, today: date) -> str:
        if value == today:
            return "امروز"
        if value == today - timedelta(days=1):
            return "دیروز"
        return value.strftime("%m/%d")
