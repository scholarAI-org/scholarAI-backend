from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_user
from app.models import Scholarship
from app.models.admin_notification import AdminNotification
from app.models.profile import Profile
from app.models.user import User
from app.schemas.admin import (
    AdminDashboardStatistics,
    AdminNotificationUnreadCountResponse,
    AdminProfileResponse,
    AdminRecentPendingScholarship,
    AdminRecentPendingScholarshipsResponse,
)
from app.services.avatar import avatar_presigned_url
from app.services.s3 import StorageClient, get_s3_storage

router = APIRouter(prefix="/admin", tags=["Admin"])


@router.get(
    "/dashboard/recent-pending-scholarships",
    response_model=AdminRecentPendingScholarshipsResponse,
    summary="Get recent pending scholarships",
    description=(
        "Returns unreviewed pending listings from the for9a and ministry scrapers, "
        "newest scraped_at first (unknown dates last), then highest id first. "
        "Total counts all matching listings before the limit. Requires an authenticated admin."
    ),
    responses={
        401: {"description": "Missing or invalid authentication"},
        403: {"description": "Requires admin role"},
    },
)
def get_recent_pending_scholarships(
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    limit: Annotated[
        int, Query(ge=1, le=50, description="Maximum listings to return")
    ] = 10,
) -> AdminRecentPendingScholarshipsResponse:
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This operation is restricted to administrators.",
        )

    # The Scholarship model documents these two scraper origins. Review metadata
    # also excludes listings that were acted on but still have a pending status.
    pending = db.query(Scholarship).filter(
        Scholarship.source.in_(("for9a", "ministry")),
        Scholarship.status == "pending",
        Scholarship.reviewed_at.is_(None),
        Scholarship.reviewed_by.is_(None),
    )
    total = pending.with_entities(func.count(Scholarship.id)).scalar()
    rows = (
        pending.with_entities(
            Scholarship.id,
            Scholarship.title,
            Scholarship.organization_name,
            Scholarship.country,
            Scholarship.deadline,
            Scholarship.no_deadline,
            Scholarship.source,
            Scholarship.source_url,
            Scholarship.status,
            Scholarship.scraped_at,
        )
        .order_by(Scholarship.scraped_at.desc().nulls_last(), Scholarship.id.desc())
        .limit(limit)
        .all()
    )
    return AdminRecentPendingScholarshipsResponse(
        items=[AdminRecentPendingScholarship.model_validate(row) for row in rows],
        total=total,
    )


@router.get(
    "/dashboard/statistics",
    response_model=AdminDashboardStatistics,
    summary="Get admin dashboard statistics",
    description=(
        "Counts pending and approved (published) scholarships and all users, "
        "including administrators and inactive accounts. Requires an authenticated admin."
    ),
    responses={
        401: {"description": "Missing or invalid authentication"},
        403: {"description": "Requires admin role"},
    },
)
def get_dashboard_statistics(
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> AdminDashboardStatistics:
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This operation is restricted to administrators.",
        )

    # Independent scalar counts avoid joins multiplying scholarship/user totals.
    pending = (
        db.query(func.count(Scholarship.id))
        .filter(Scholarship.status == "pending")
        .scalar_subquery()
    )
    published = (
        db.query(func.count(Scholarship.id))
        .filter(Scholarship.status == "approved")
        .scalar_subquery()
    )
    users = db.query(func.count(User.id)).scalar_subquery()
    counts = db.query(
        pending.label("pending_scholarships"),
        published.label("published_scholarships"),
        users.label("users"),
    ).one()
    return AdminDashboardStatistics(
        pending_scholarships=counts.pending_scholarships,
        published_scholarships=counts.published_scholarships,
        users=counts.users,
    )


@router.get(
    "/notifications/unread-count",
    response_model=AdminNotificationUnreadCountResponse,
    summary="Get admin unread notifications count",
    description=(
        "Returns the count of unread notifications for the admin notification bell counter. "
        "Requires an authenticated admin."
    ),
    responses={
        401: {"description": "Missing or invalid authentication"},
        403: {"description": "Requires admin role"},
    },
)
def get_unread_notifications_count(
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> AdminNotificationUnreadCountResponse:
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This operation is restricted to administrators.",
        )

    unread_count = (
        db.query(func.count(AdminNotification.id))
        .filter(AdminNotification.is_read == False)  # noqa: E712
        .scalar()
    ) or 0

    return AdminNotificationUnreadCountResponse(unread_count=unread_count)


@router.get(
    "/profile",
    response_model=AdminProfileResponse,
    summary="Get current admin profile",
    description=(
        "Returns the authenticated administrator's profile information "
        "(id, full_name, email, role, avatar_url) to display in the dashboard header. "
        "Requires an authenticated admin."
    ),
    responses={
        401: {"description": "Missing or invalid authentication"},
        403: {"description": "Requires admin role"},
    },
)
@router.get(
    "/me",
    response_model=AdminProfileResponse,
    include_in_schema=False,
)
def get_current_admin_profile(
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    storage: Annotated[StorageClient, Depends(get_s3_storage)],
) -> AdminProfileResponse:
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This operation is restricted to administrators.",
        )

    profile = db.query(Profile).filter(Profile.user_id == current_user.id).first()
    avatar_url: Optional[str] = None
    if profile and profile.avatar_object_key:
        try:
            avatar_url = avatar_presigned_url(profile, storage)
        except Exception:
            avatar_url = None

    return AdminProfileResponse(
        id=current_user.id,
        full_name=current_user.full_name or "",
        email=current_user.email,
        role=current_user.role,
        avatar_url=avatar_url,
    )
