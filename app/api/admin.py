from typing import Annotated, Optional, cast

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_user
from app.models import Scholarship
from app.models.admin_notification import AdminNotification, NotificationType
from app.models.audit_log import AuditLog
from app.models.profile import Profile
from app.models.user import User
from app.schemas.admin import (
    AdminDashboardStatistics,
    AdminMonthlyActivityResponse,
    AdminNotificationItem,
    AdminNotificationReadResponse,
    AdminNotificationsResponse,
    AdminNotificationUnreadCountResponse,
    AdminProfileResponse,
    AdminRecentPendingScholarship,
    AdminRecentPendingScholarshipsResponse,
    AdminScholarshipReview,
    AdminScholarshipsReviewResponse,
    AuditLogItem,
    DashboardAuditLogsResponse,
    ScholarshipReviewStatus,
)
from app.services.admin_notifications import (
    filtered_notifications,
    mark_notification_read,
)
from app.services.admin_statistics import get_monthly_activity_statistics
from app.services.avatar import avatar_presigned_url
from app.services.s3 import StorageClient, get_s3_storage

router = APIRouter(prefix="/admin", tags=["Admin"])


@router.get(
    "/scholarships/review",
    response_model=AdminScholarshipsReviewResponse,
    summary="List aggregated scholarships for review by status",
    description=(
        "Paginated listings from for9a and ministry, filtered by status (pending by default). "
        "Accepted statuses are pending, approved and rejected. Ordered by scraped_at "
        "descending (unknown dates last), then id descending. Requires an admin."
    ),
    responses={
        401: {"description": "Missing or invalid authentication"},
        403: {"description": "Requires admin role"},
    },
)
def get_scholarships_review(
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    page: Annotated[int, Query(ge=1, description="Page number, starting at 1")] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
    scholarship_status: Annotated[
        ScholarshipReviewStatus,
        Query(alias="status", description="Stored scholarship review status"),
    ] = ScholarshipReviewStatus.PENDING,
) -> AdminScholarshipsReviewResponse:
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This operation is restricted to administrators.",
        )

    listings = db.query(Scholarship).filter(
        Scholarship.source.in_(("for9a", "ministry")),
        Scholarship.status == scholarship_status.value,
    )
    total = listings.with_entities(func.count(Scholarship.id)).scalar() or 0
    total_pages = (total + page_size - 1) // page_size
    rows = []
    # An out-of-range page is empty; avoid sending arbitrary-size offsets to SQL.
    if page <= total_pages:
        rows = (
            listings.with_entities(
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
            .offset((page - 1) * page_size)
            .limit(page_size)
            .all()
        )
    return AdminScholarshipsReviewResponse(
        items=[AdminScholarshipReview.model_validate(row) for row in rows],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )


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
    "/dashboard/monthly-activity",
    response_model=AdminMonthlyActivityResponse,
    summary="Get monthly platform activity",
    description=(
        "Returns the last 12 UTC calendar months, oldest first, including the current "
        "month and zero-activity months. Counts currently approved scholarships by "
        "reviewed_at, falling back to scraped_at when review dates are missing, and "
        "all users by created_at. Undated records are excluded. Requires an admin."
    ),
    responses={
        401: {"description": "Missing or invalid authentication"},
        403: {"description": "Requires admin role"},
    },
)
def get_dashboard_monthly_activity(
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> AdminMonthlyActivityResponse:
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This operation is restricted to administrators.",
        )

    return get_monthly_activity_statistics(db)


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

    unread_count = filtered_notifications(
        db, cast(int, current_user.id), is_read=False
    ).count()

    return AdminNotificationUnreadCountResponse(unread_count=unread_count)


@router.get(
    "/notifications",
    response_model=AdminNotificationsResponse,
    summary="List notifications visible to the current admin",
    responses={
        401: {"description": "Missing or invalid authentication"},
        403: {"description": "Requires admin role"},
    },
)
def get_admin_notifications(
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
    is_read: bool | None = None,
    notification_type: Annotated[NotificationType | None, Query(alias="type")] = None,
) -> AdminNotificationsResponse:
    if current_user.role != "admin":
        raise HTTPException(
            status_code=403, detail="This operation is restricted to administrators."
        )
    query = filtered_notifications(
        db,
        cast(int, current_user.id),
        is_read=is_read,
        notification_type=notification_type,
    )
    total = query.count()
    rows = (
        query.order_by(AdminNotification.created_at.desc(), AdminNotification.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return AdminNotificationsResponse(
        items=[AdminNotificationItem.model_validate(row) for row in rows],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=(total + page_size - 1) // page_size,
    )


@router.patch(
    "/notifications/{notification_id}/read",
    response_model=AdminNotificationReadResponse,
    summary="Mark one notification as read for the current admin",
    responses={
        401: {"description": "Missing or invalid authentication"},
        403: {"description": "Requires admin role"},
        404: {"description": "Notification not found"},
    },
)
def read_admin_notification(
    notification_id: int,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> AdminNotificationReadResponse:
    if current_user.role != "admin":
        raise HTTPException(
            status_code=403, detail="This operation is restricted to administrators."
        )
    try:
        result = mark_notification_read(db, cast(int, current_user.id), notification_id)
        if result is None:
            raise HTTPException(status_code=404, detail="Notification not found")
        response = AdminNotificationReadResponse(id=result.id, read_at=result.read_at)
        db.commit()
        return response
    except Exception:
        db.rollback()
        raise


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


@router.get(
    "/dashboard/audit-logs",
    response_model=DashboardAuditLogsResponse,
    summary="Get dashboard audit logs",
    description=(
        "Returns recent administrative audit logs (publish, edit, delete operations) "
        "ordered by newest first. Supports pagination and action filtering. "
        "Requires an authenticated admin."
    ),
    responses={
        401: {"description": "Missing or invalid authentication"},
        403: {"description": "Requires admin role"},
    },
)
@router.get(
    "/audit-logs",
    response_model=DashboardAuditLogsResponse,
    include_in_schema=False,
)
def get_dashboard_audit_logs(
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    limit: Annotated[
        int, Query(ge=1, le=100, description="Maximum number of audit logs to return")
    ] = 10,
    offset: Annotated[
        int, Query(ge=0, description="Number of audit logs to skip")
    ] = 0,
    action: Annotated[
        Optional[str],
        Query(description="Filter by action type (publish, edit, delete)"),
    ] = None,
) -> DashboardAuditLogsResponse:
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This operation is restricted to administrators.",
        )

    query = db.query(AuditLog)
    if action:
        query = query.filter(AuditLog.action == action.lower())

    total = query.with_entities(func.count(AuditLog.id)).scalar() or 0
    logs = (
        query.order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )

    return DashboardAuditLogsResponse(
        items=[AuditLogItem.model_validate(log) for log in logs],
        total=total,
    )
