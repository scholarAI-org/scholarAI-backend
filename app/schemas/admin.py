from datetime import date, datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class AdminRecentPendingScholarship(BaseModel):
    id: int
    title: str
    organization_name: str | None
    country: str | None
    deadline: date | None
    no_deadline: bool | None
    source: str
    source_url: str | None
    status: str
    scraped_at: datetime | None

    model_config = ConfigDict(from_attributes=True)


class AdminRecentPendingScholarshipsResponse(BaseModel):
    items: list[AdminRecentPendingScholarship]
    total: int = Field(
        ge=0, description="All matching scholarships before applying limit"
    )


class ScholarshipReviewStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class AdminScholarshipReview(AdminRecentPendingScholarship):
    """Table fields for the full review page, filtered by stored status."""

    status: ScholarshipReviewStatus


class AdminScholarshipsReviewResponse(BaseModel):
    items: list[AdminScholarshipReview]
    total: int = Field(ge=0, description="Matching listings before pagination")
    page: int = Field(ge=1)
    page_size: int = Field(ge=1, le=100)
    total_pages: int = Field(ge=0)


class AdminDashboardStatistics(BaseModel):
    pending_scholarships: int = Field(ge=0)
    published_scholarships: int = Field(ge=0)
    users: int = Field(ge=0)


class AdminMonthlyActivityItem(BaseModel):
    year: int
    month: int = Field(ge=1, le=12)
    month_name: str
    approved_scholarships: int = Field(ge=0)
    users: int = Field(ge=0)


class AdminMonthlyActivityResponse(BaseModel):
    items: list[AdminMonthlyActivityItem] = Field(min_length=12, max_length=12)


class AdminNotificationUnreadCountResponse(BaseModel):
    unread_count: int = Field(ge=0, description="عدد الإشعارات غير المقروءة")


class AdminProfileResponse(BaseModel):
    id: int = Field(..., description="معرف المستخدم للأدمن")
    full_name: str = Field(..., description="الاسم الكامل للأدمن")
    email: str = Field(..., description="البريد الإلكتروني للأدمن")
    role: str = Field(..., description="دور المستخدم (admin)")
    avatar_url: Optional[str] = Field(
        None, description="رابط الصورة الشخصية أو null في حال عدم وجودها"
    )


class AuditLogItem(BaseModel):
    id: int = Field(..., description="معرف سجل التدقيق")
    admin_id: Optional[int] = Field(None, description="معرف الأدمن الذي قام بالعملية")
    admin_name: str = Field(..., description="اسم الأدمن الذي قام بالعملية")
    action: str = Field(..., description="نوع العملية (publish, edit, delete)")
    action_display: str = Field(..., description="اسم العملية المعروض (اعتماد ونشر، تعديل، حذف)")
    entity_type: str = Field("scholarship", description="نوع الكيان المعني")
    entity_id: Optional[int] = Field(None, description="معرف الكيان المعني")
    entity_name: str = Field(..., description="اسم الكيان أو المنحة")
    details: Optional[dict] = Field(None, description="تفاصيل إضافية عن العملية")
    created_at: datetime = Field(..., description="تاريخ ووقت تنفيذ العملية")

    model_config = ConfigDict(from_attributes=True)


class DashboardAuditLogsResponse(BaseModel):
    items: list[AuditLogItem] = Field(..., description="قائمة سجلات التدقيق")
    total: int = Field(ge=0, description="إجمالي عدد السجلات المطابقة")


class DuplicateCandidateItem(BaseModel):
    id: int = Field(..., description="معرف المنحة المشتبه بها")
    title: str = Field(..., description="عنوان المنحة المشتبه بها")
    source: str = Field(..., description="مصدر المنحة")
    status: str = Field(..., description="حالة المنحة الحالية (pending, approved, rejected)")
    country: Optional[str] = Field(None, description="دولة المنحة")
    organization_name: Optional[str] = Field(None, description="الجهة المانحة")
    similarity_score: float = Field(..., ge=0.0, le=1.0, description="نسبة التشابه المقاسة (0.0 إلى 1.0)")
    reasons: list[str] = Field(default_factory=list, description="أسباب ترجيح التكرار بالتفصيل")

    model_config = ConfigDict(from_attributes=True)


class ScholarshipDuplicateCheckResponse(BaseModel):
    is_suspected_duplicate: bool = Field(..., description="هل توجد منحة محتمل أنها مكررة بناءً على المعايير")
    highest_similarity_score: float = Field(..., ge=0.0, le=1.0, description="أعلى نسبة تشابه تم العثور عليها")
    candidates: list[DuplicateCandidateItem] = Field(default_factory=list, description="قائمة المنح المشابهة مرتبة بالأعلى تشابهاً")


class ScholarshipDuplicateCheckRequest(BaseModel):
    title: str = Field(..., min_length=2, description="عنوان المنحة المراد فحصها")
    organization_name: Optional[str] = Field(None, description="اسم المؤسسة أو الجامعة المانحة")
    country: Optional[str] = Field(None, description="دولة المنحة")
    apply_link: Optional[str] = Field(None, description="رابط التقديم المباشر إن وجد")
    deadline: Optional[date] = Field(None, description="الموعد النهائي للتقديم إن وجد")
    exclude_id: Optional[int] = Field(None, description="معرف منحة لاستثنائها من المقارنة (تستخدم عند فحص منحة قائمة)")

