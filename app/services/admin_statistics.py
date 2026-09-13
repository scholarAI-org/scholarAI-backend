from datetime import datetime, timedelta, timezone
from itertools import pairwise

from sqlalchemy import and_, case, func, or_
from sqlalchemy.orm import Session
from sqlalchemy.sql.elements import ColumnElement

from app.models import Scholarship
from app.models.audit_log import AuditLog
from app.models.user import User
from app.schemas.admin import (
    AdminMonthlyActivityItem,
    AdminMonthlyActivityResponse,
    PendingScholarshipReviewStatisticsResponse,
    ScholarshipReviewStatus,
)

MONTH_NAMES = (
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
)


def get_pending_review_statistics(
    db: Session,
) -> PendingScholarshipReviewStatisticsResponse:
    """Count existing scholarships across all sources, from Monday UTC to now."""
    now = datetime.now(timezone.utc)
    week_start = (now - timedelta(days=now.weekday())).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    # Both approval routes log publish; approve is also a supported audit action.
    # One row per scholarship prevents repeat approvals multiplying the counts.
    approvals = (
        db.query(
            AuditLog.entity_id.label("scholarship_id"),
            func.max(AuditLog.created_at).label("approved_at"),
        )
        .filter(
            AuditLog.entity_type == "scholarship",
            AuditLog.action.in_(("publish", "approve")),
        )
        .group_by(AuditLog.entity_id)
        .subquery()
    )
    # Legacy approvals may predate audit logging. Never use updated_at or scraped_at.
    approval_date = func.coalesce(approvals.c.approved_at, Scholarship.reviewed_at)
    pending = Scholarship.status == ScholarshipReviewStatus.PENDING.value
    approved_this_week = and_(
        Scholarship.status == ScholarshipReviewStatus.APPROVED.value,
        approval_date >= week_start,
        approval_date <= now,
    )
    reviewed_this_week = and_(
        Scholarship.status.in_((
            ScholarshipReviewStatus.APPROVED.value,
            ScholarshipReviewStatus.REJECTED.value,
        )),
        Scholarship.reviewed_at >= week_start,
        Scholarship.reviewed_at <= now,
    )
    missing_source_url = or_(
        Scholarship.source_url.is_(None),
        func.trim(Scholarship.source_url, " \t\n\r\f\v") == "",
    )
    counts = (
        db.query(
            func.count(case((pending, 1))).label("pending_count"),
            func.count(case((approved_this_week, 1))).label("approved_this_week"),
            func.count(case((reviewed_this_week, 1))).label("reviewed_this_week"),
            func.count(case((missing_source_url, 1))).label("missing_source_url_count"),
        )
        .select_from(Scholarship)
        .outerjoin(approvals, approvals.c.scholarship_id == Scholarship.id)
        .one()
    )
    return PendingScholarshipReviewStatisticsResponse(**counts._mapping)


def _monthly_counts(
    db: Session,
    timestamp: ColumnElement[datetime],
    boundaries: list[datetime],
    *filters: ColumnElement[bool],
) -> tuple[int, ...]:
    # Fixed-size conditional aggregates work on PostgreSQL and SQLite and avoid
    # session-timezone-dependent date extraction. Only 12 counts reach Python.
    counts = db.query(
        *[
            func.count(case((and_(timestamp >= start, timestamp < end), 1)))
            for start, end in pairwise(boundaries)
        ]
    ).filter(timestamp >= boundaries[0], timestamp < boundaries[-1], *filters).one()
    return tuple(counts)


def get_monthly_activity_statistics(db: Session) -> AdminMonthlyActivityResponse:
    """Count the last 12 UTC calendar months, including the current month."""
    now = datetime.now(timezone.utc)
    first_month = now.year * 12 + now.month - 1 - 11
    boundaries = [
        datetime(index // 12, index % 12 + 1, 1, tzinfo=timezone.utc)
        for index in range(first_month, first_month + 13)
    ]

    # There is no dedicated approval timestamp or recorded approval history.
    # reviewed_at is the best available date; scraped_at approximates legacy
    # approvals without review metadata. Undated records cannot be assigned.
    scholarship_counts = _monthly_counts(
        db,
        func.coalesce(Scholarship.reviewed_at, Scholarship.scraped_at),
        boundaries,
        Scholarship.status == ScholarshipReviewStatus.APPROVED.value,
    )
    # User.created_at stores naive UTC, unlike the scholarship timestamps.
    user_counts = _monthly_counts(
        db, User.created_at, [boundary.replace(tzinfo=None) for boundary in boundaries]
    )
    return AdminMonthlyActivityResponse(
        items=[
            AdminMonthlyActivityItem(
                year=month.year,
                month=month.month,
                month_name=MONTH_NAMES[month.month - 1],
                approved_scholarships=scholarship_counts[index],
                users=user_counts[index],
            )
            for index, month in enumerate(boundaries[:-1])
        ]
    )
