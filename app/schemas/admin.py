from datetime import date, datetime
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


class AdminDashboardStatistics(BaseModel):
    pending_scholarships: int = Field(ge=0)
    published_scholarships: int = Field(ge=0)
    users: int = Field(ge=0)


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
