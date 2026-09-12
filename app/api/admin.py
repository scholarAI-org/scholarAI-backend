from datetime import datetime, timezone
from typing import Annotated, Any, Optional, cast

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
    DuplicateCandidateItem,
    ScholarshipActionResponse,
    ScholarshipApproveRequest,
    ScholarshipApproveResponse,
    ScholarshipDetailResponse,
    ScholarshipDuplicateCheckRequest,
    ScholarshipDuplicateCheckResponse,
    ScholarshipRejectRequest,
    ScholarshipRejectResponse,
    ScholarshipReviewStatus,
    ScholarshipStatusUpdateRequest,
)
from app.schemas.Scholarship import ScholarshipResponse, ScholarshipUpdate
from app.services.admin_notifications import (
    filtered_notifications,
    mark_notification_read,
)
from app.services.admin_statistics import get_monthly_activity_statistics
from app.services.audit import create_audit_log
from app.services.avatar import avatar_presigned_url
from app.services.duplicate_detection import find_duplicate_candidates
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


@router.get(
    "/scholarships/{scholarship_id}/duplicates",
    response_model=ScholarshipDuplicateCheckResponse,
    summary="Check duplicate scholarship candidates for an existing scholarship",
    description=(
        "Analyzes the specified scholarship against other listings using fuzzy "
        "and heuristic matching (title, apply link, country, organization) and "
        "returns potential duplicate candidates with similarity scores and reasons."
    ),
    responses={
        401: {"description": "Missing or invalid authentication"},
        403: {"description": "Requires admin role"},
        404: {"description": "Scholarship not found"},
    },
)
def get_scholarship_duplicates(
    scholarship_id: int,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    threshold: Annotated[
        float,
        Query(ge=0.1, le=1.0, description="Minimum similarity score threshold"),
    ] = 0.75,
    limit: Annotated[
        int,
        Query(ge=1, le=20, description="Maximum number of candidates to return"),
    ] = 5,
) -> ScholarshipDuplicateCheckResponse:
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This operation is restricted to administrators.",
        )

    scholarship = db.query(Scholarship).filter(Scholarship.id == scholarship_id).first()
    if not scholarship:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Scholarship not found.",
        )

    candidates = find_duplicate_candidates(
        db=db,
        target=scholarship,
        threshold=threshold,
        limit=limit,
        exclude_id=scholarship.id,
    )

    highest_score = candidates[0]["similarity_score"] if candidates else 0.0
    return ScholarshipDuplicateCheckResponse(
        is_suspected_duplicate=len(candidates) > 0,
        highest_similarity_score=highest_score,
        candidates=[DuplicateCandidateItem.model_validate(c) for c in candidates],
    )


@router.post(
    "/scholarships/check-duplicate",
    response_model=ScholarshipDuplicateCheckResponse,
    summary="Check potential duplicate candidates for new scholarship payload",
    description=(
        "Evaluates a scholarship payload (title, country, apply_link, organization_name) "
        "against stored listings and returns potential duplicate matches."
    ),
    responses={
        401: {"description": "Missing or invalid authentication"},
        403: {"description": "Requires admin role"},
    },
)
def check_scholarship_duplicate(
    payload: ScholarshipDuplicateCheckRequest,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    threshold: Annotated[
        float,
        Query(ge=0.1, le=1.0, description="Minimum similarity score threshold"),
    ] = 0.75,
    limit: Annotated[
        int,
        Query(ge=1, le=20, description="Maximum number of candidates to return"),
    ] = 5,
) -> ScholarshipDuplicateCheckResponse:
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This operation is restricted to administrators.",
        )

    candidates = find_duplicate_candidates(
        db=db,
        target=payload.model_dump(),
        threshold=threshold,
        limit=limit,
        exclude_id=payload.exclude_id,
    )

    highest_score = candidates[0]["similarity_score"] if candidates else 0.0
    return ScholarshipDuplicateCheckResponse(
        is_suspected_duplicate=len(candidates) > 0,
        highest_similarity_score=highest_score,
        candidates=[DuplicateCandidateItem.model_validate(c) for c in candidates],
    )


@router.get(
    "/scholarships/{scholarship_id}",
    response_model=ScholarshipDetailResponse,
    summary="Get scholarship review details for modal",
    description="Returns full scholarship details including overview cards and input fields for the review modal.",
    responses={
        401: {"description": "Missing or invalid authentication"},
        403: {"description": "Requires admin role"},
        404: {"description": "Scholarship not found"},
    },
)
def get_scholarship_review_detail(
    scholarship_id: int,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> ScholarshipDetailResponse:
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This operation is restricted to administrators.",
        )

    scholarship = db.query(Scholarship).filter(Scholarship.id == scholarship_id).first()
    if not scholarship:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Scholarship not found.",
        )

    return ScholarshipDetailResponse.model_validate(scholarship)


def validate_scholarship_for_publication(scholarship: Scholarship) -> list[str]:
    """
    Validate mandatory fields for approving & publishing a scholarship.
    Checks required publication inputs (source_url, apply_link, image_url)
    and core scholarship information.
    """
    missing_or_invalid: list[str] = []

    def is_valid_url(url: Optional[str]) -> bool:
        if not url or not url.strip():
            return False
        u = url.strip().lower()
        return u.startswith("http://") or u.startswith("https://")

    # 1. Essential inputs from modal (red asterisks)
    if not is_valid_url(scholarship.source_url):
        missing_or_invalid.append("رابط المصدر الأصلي (source_url) مطلوب ويجب أن يكون رابطاً صالحاً (http/https).")
    if not is_valid_url(scholarship.apply_link):
        missing_or_invalid.append("رابط التقديم (apply_link) مطلوب ويجب أن يكون رابطاً صالحاً (http/https).")
    if not is_valid_url(scholarship.image_url):
        missing_or_invalid.append("رابط الصورة (image_url) مطلوب ويجب أن يكون رابطاً صالحاً (http/https).")

    # 2. Core metadata
    if not scholarship.title or not scholarship.title.strip():
        missing_or_invalid.append("عنوان المنحة (title) مطلوب.")
    if not scholarship.country or not scholarship.country.strip():
        missing_or_invalid.append("دولة الدراسة (country) مطلوبة.")
    if not scholarship.organization_name or not scholarship.organization_name.strip():
        missing_or_invalid.append("الجهة المقدمة / المانحة (organization_name) مطلوبة.")
    if not scholarship.deadline and not scholarship.no_deadline:
        missing_or_invalid.append("الموعد النهائي (deadline) مطلوب ما لم يتم تحديد خيار بدون موعد نهائي.")

    return missing_or_invalid


@router.post(
    "/scholarships/{scholarship_id}/approve",
    response_model=ScholarshipApproveResponse,
    summary="Approve & publish scholarship",
    description=(
        "Approves and publishes a pending scholarship. Validates essential publication fields "
        "(source_url, apply_link, image_url, title, country, organization, deadline). "
        "Records reviewed_by, reviewed_at, updated_at, and creates an audit log entry. "
        "Rejects already approved (409 Conflict) or non-pending scholarships (400 Bad Request)."
    ),
    responses={
        400: {"description": "Scholarship is not in pending status"},
        401: {"description": "Missing or invalid authentication"},
        403: {"description": "Requires admin role"},
        404: {"description": "Scholarship not found"},
        409: {"description": "Scholarship is already approved/published"},
        422: {"description": "Mandatory publication fields missing or invalid"},
    },
)
@router.post(
    "/scholarships/{scholarship_id}/publish",
    response_model=ScholarshipApproveResponse,
    include_in_schema=False,
)
def approve_and_publish_scholarship(
    scholarship_id: int,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    payload: Optional[ScholarshipApproveRequest] = None,
) -> ScholarshipApproveResponse:
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This operation is restricted to administrators.",
        )

    scholarship = db.query(Scholarship).filter(Scholarship.id == scholarship_id).first()
    if not scholarship:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Scholarship not found.",
        )

    # Status checks:
    # 1. Prevent re-approving an already published/approved scholarship
    if scholarship.status == "approved":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="المنحة معتمدة ومنشورة بالفعل ولا يمكن إعادة اعتمادها.",
        )

    # 2. Must be in pending status
    if scholarship.status != "pending":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"لا يمكن اعتماد المنحة لأن حالتها الحالية ليست قيد المراجعة (الحالة الحالية: {scholarship.status}).",
        )

    # Apply any updated values sent from modal inputs
    if payload:
        data = payload.model_dump(exclude_unset=True)
        for key, val in data.items():
            if val is not None and hasattr(scholarship, key):
                setattr(scholarship, key, val)

    # Validate essential publication fields
    errors = validate_scholarship_for_publication(scholarship)
    if errors:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "message": "لا يمكن اعتماد ونشر المنحة بسبب نقص أو عدم صلاحية الحقول الإلزامية للنشر.",
                "errors": errors,
            },
        )

    now = datetime.now(timezone.utc)
    reviewer_email = current_user.email or current_user.full_name or "admin"

    scholarship.status = "approved"
    scholarship.reviewed_by = reviewer_email
    scholarship.reviewed_at = now
    scholarship.updated_at = now

    audit_details: dict[str, Any] = {
        "source": scholarship.source,
        "country": scholarship.country,
        "reviewed_by": reviewer_email,
        "study_level": scholarship.study_level,
        "funding_type": scholarship.funding_type,
    }
    if payload and payload.notes:
        audit_details["notes"] = payload.notes

    log_entry = create_audit_log(
        db=db,
        admin=current_user,
        action="publish",
        action_display="اعتماد ونشر",
        entity_name=scholarship.title,
        entity_id=scholarship.id,
        details=audit_details,
    )

    return ScholarshipApproveResponse(
        id=scholarship.id,
        title=scholarship.title,
        status=scholarship.status,
        is_published=True,
        reviewed_at=scholarship.reviewed_at,
        reviewed_by=scholarship.reviewed_by,
        updated_at=scholarship.updated_at,
        audit_log_id=log_entry.id,
        message="تم اعتماد ونشر المنحة بنجاح.",
    )


@router.post(
    "/scholarships/{scholarship_id}/reject",
    response_model=ScholarshipRejectResponse,
    summary="Reject & soft-delete scholarship",
    description=(
        "Rejects/archives a scholarship with a mandatory reason. Saves rejection reason, "
        "admin ID, rejection timestamp, and generates an administrative audit log. "
        "Prevents re-rejecting already rejected scholarships (409 Conflict)."
    ),
    responses={
        400: {"description": "Invalid operation"},
        401: {"description": "Missing or invalid authentication"},
        403: {"description": "Requires admin role"},
        404: {"description": "Scholarship not found"},
        409: {"description": "Scholarship is already rejected"},
        422: {"description": "Rejection reason is mandatory"},
    },
)
@router.post(
    "/scholarships/{scholarship_id}/soft-delete",
    response_model=ScholarshipRejectResponse,
    include_in_schema=False,
)
def reject_scholarship(
    scholarship_id: int,
    payload: ScholarshipRejectRequest,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> ScholarshipRejectResponse:
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This operation is restricted to administrators.",
        )

    scholarship = db.query(Scholarship).filter(Scholarship.id == scholarship_id).first()
    if not scholarship:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Scholarship not found.",
        )

    # Prevent re-rejecting already rejected scholarships
    if scholarship.status == "rejected":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="المنحة مرفوضة بالفعل ولا يمكن إعادة رفضها.",
        )

    # Validate mandatory rejection reason
    cleaned_reason = payload.reason.strip() if payload.reason else ""
    if len(cleaned_reason) < 3:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "message": "سبب الرفض إلزامي ويجب ألا يقل عن 3 أحرف.",
                "field": "reason",
            },
        )

    old_status = scholarship.status
    now = datetime.now(timezone.utc)
    reviewer_identity = current_user.email or current_user.full_name or "admin"

    scholarship.status = "rejected"
    scholarship.rejection_reason = cleaned_reason
    scholarship.admin_id = current_user.id
    scholarship.reviewed_by = reviewer_identity
    scholarship.rejected_at = now
    scholarship.reviewed_at = now
    scholarship.updated_at = now

    db.commit()
    db.refresh(scholarship)

    log_entry = create_audit_log(
        db=db,
        admin=current_user,
        action="reject",
        action_display="رفض",
        entity_name=scholarship.title,
        entity_id=scholarship.id,
        details={
            "reason": cleaned_reason,
            "old_status": old_status,
            "new_status": "rejected",
            "admin_id": current_user.id,
            "reviewed_by": reviewer_identity,
            "rejected_at": now.isoformat(),
        },
    )

    return ScholarshipRejectResponse(
        id=scholarship.id,
        title=scholarship.title,
        status=scholarship.status,
        rejection_reason=scholarship.rejection_reason,
        admin_id=scholarship.admin_id,
        reviewed_by=scholarship.reviewed_by,
        rejected_at=scholarship.rejected_at,
        updated_at=scholarship.updated_at,
        audit_log_id=log_entry.id,
        message="تم رفض وأرشفة المنحة بنجاح وتوثيق العملية في سجل التدقيق.",
    )


@router.put(
    "/scholarships/{scholarship_id}",
    response_model=ScholarshipResponse,
    summary="Update scholarship details with audit logging",
    description="Updates scholarship fields and records an administrative audit log entry.",
    responses={
        401: {"description": "Missing or invalid authentication"},
        403: {"description": "Requires admin role"},
        404: {"description": "Scholarship not found"},
    },
)
def update_scholarship(
    scholarship_id: int,
    payload: ScholarshipUpdate,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> ScholarshipResponse:
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This operation is restricted to administrators.",
        )

    scholarship = db.query(Scholarship).filter(Scholarship.id == scholarship_id).first()
    if not scholarship:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Scholarship not found.",
        )

    update_data = payload.model_dump(exclude_unset=True)
    changes: dict[str, Any] = {}
    for field, new_val in update_data.items():
        old_val = getattr(scholarship, field)
        if old_val != new_val:
            changes[field] = {
                "old": str(old_val) if old_val is not None else None,
                "new": str(new_val) if new_val is not None else None,
            }
            setattr(scholarship, field, new_val)

    scholarship.updated_at = datetime.now(timezone.utc)
    create_audit_log(
        db=db,
        admin=current_user,
        action="edit",
        action_display="تعديل",
        entity_name=scholarship.title,
        entity_id=scholarship.id,
        details={"changes": changes} if changes else None,
    )

    return ScholarshipResponse.model_validate(scholarship)


@router.patch(
    "/scholarships/{scholarship_id}/status",
    response_model=ScholarshipActionResponse,
    summary="Update scholarship status with audit logging",
    description="Updates scholarship status (pending, approved, rejected) and records an audit log.",
    responses={
        401: {"description": "Missing or invalid authentication"},
        403: {"description": "Requires admin role"},
        404: {"description": "Scholarship not found"},
    },
)
def update_scholarship_status(
    scholarship_id: int,
    payload: ScholarshipStatusUpdateRequest,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> ScholarshipActionResponse:
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This operation is restricted to administrators.",
        )

    scholarship = db.query(Scholarship).filter(Scholarship.id == scholarship_id).first()
    if not scholarship:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Scholarship not found.",
        )

    old_status = scholarship.status
    new_status = payload.status.value
    now = datetime.now(timezone.utc)

    scholarship.status = new_status
    scholarship.reviewed_at = now
    scholarship.reviewed_by = current_user.email or current_user.full_name
    scholarship.updated_at = now

    if new_status == "approved":
        action = "publish"
        action_display = "اعتماد ونشر"
    elif new_status == "rejected":
        action = "reject"
        action_display = "رفض"
        if payload.reason:
            scholarship.rejection_reason = payload.reason.strip()
        scholarship.admin_id = current_user.id
        scholarship.rejected_at = now
    else:
        action = "status_change"
        action_display = "تغيير حالة"

    log_entry = create_audit_log(
        db=db,
        admin=current_user,
        action=action,
        action_display=action_display,
        entity_name=scholarship.title,
        entity_id=scholarship.id,
        details={
            "old_status": old_status,
            "new_status": new_status,
            "reason": payload.reason,
        },
    )

    return ScholarshipActionResponse(
        message=f"تم تغيير حالة المنحة بنجاح إلى: {action_display}",
        scholarship_id=scholarship.id,
        status=scholarship.status,
        audit_log_id=log_entry.id,
    )


@router.delete(
    "/scholarships/{scholarship_id}",
    response_model=ScholarshipActionResponse,
    summary="Delete scholarship with audit logging",
    description="Deletes a scholarship and records an administrative audit log entry.",
    responses={
        401: {"description": "Missing or invalid authentication"},
        403: {"description": "Requires admin role"},
        404: {"description": "Scholarship not found"},
    },
)
def delete_scholarship(
    scholarship_id: int,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> ScholarshipActionResponse:
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This operation is restricted to administrators.",
        )

    scholarship = db.query(Scholarship).filter(Scholarship.id == scholarship_id).first()
    if not scholarship:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Scholarship not found.",
        )

    title = scholarship.title

    db.delete(scholarship)

    log_entry = create_audit_log(
        db=db,
        admin=current_user,
        action="delete",
        action_display="حذف",
        entity_name=title,
        entity_id=scholarship_id,
    )

    return ScholarshipActionResponse(
        message=f"تم حذف المنحة '{title}' بنجاح وتوثيق العملية في سجل التدقيق.",
        scholarship_id=scholarship_id,
        status="deleted",
        audit_log_id=log_entry.id,
    )
