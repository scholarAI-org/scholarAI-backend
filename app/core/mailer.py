import logging
import resend
from app.core.config import settings

logger = logging.getLogger("uvicorn.error")

# ضبط مفتاح الـ API الخاص بـ Resend
resend.api_key = settings.RESEND_API_KEY

def send_reset_password_email(email_to: str, token: str) -> bool:
    """
    إرسال بريد إعادة تعيين كلمة المرور.
    يُرجع True عند النجاح، False عند الفشل.
    """
    reset_link = f"{settings.FRONTEND_URL}/reset-password?token={token}"

    html_content = f"""
    <div style="font-family: Arial, sans-serif; direction: rtl; text-align: right; padding: 20px;">
        <h2>طلب إعادة تعيين كلمة المرور - Scholar AI</h2>
        <p>مرحباً، لقد تلقينا طلباً لإعادة تعيين كلمة المرور الخاصة بحسابك.</p>
        <p>اضغط/ي على الزر أدناه لتغيير كلمة المرور (الرابط صالح لمدة 15 دقيقة فقط):</p>
        <a href="{reset_link}" style="background-color: #4CAF50; color: white; padding: 10px 20px; text-decoration: none; display: inline-block; border-radius: 5px; margin: 10px 0;">تغيير كلمة المرور</a>
        <br><br>
        <p>إذا لم تطلبي ذلك، يمكنكِ إهمال هذا البريد وسيظل حسابكِ آمناً.</p>
    </div>
    """

    params = {
        "from": "Scholar AI <onboarding@resend.dev>",
        "to": [email_to],
        "subject": "إعادة تعيين كلمة المرور - Scholar AI",
        "html": html_content,
    }

    try:
        resend.Emails.send(params)
        return True
    except Exception as exc:
        logger.error("فشل إرسال بريد إعادة التعيين إلى %s: %s", email_to, exc)
        return False