from datetime import datetime, timezone
from itertools import pairwise

from sqlalchemy import and_, case, func
from sqlalchemy.orm import Session
from sqlalchemy.sql.elements import ColumnElement

from app.models import Scholarship
from app.models.user import User
from app.schemas.admin import (
    AdminMonthlyActivityItem,
    AdminMonthlyActivityResponse,
    ScholarshipReviewStatus,
)

MONTH_NAMES = (
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
)


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
