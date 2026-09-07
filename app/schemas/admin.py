from pydantic import BaseModel, Field


class AdminDashboardStatistics(BaseModel):
    pending_scholarships: int = Field(ge=0)
    published_scholarships: int = Field(ge=0)
    users: int = Field(ge=0)


class AdminNotificationUnreadCountResponse(BaseModel):
    unread_count: int = Field(ge=0, description="عدد الإشعارات غير المقروءة")
