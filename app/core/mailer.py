import resend
from app.core.config import settings

# ضبط مفتاح الـ API الخاص بـ Resend
resend.api_key = settings.RESEND_API_KEY


def send_verification_otp_email(email_to: str, otp: str) -> None:
    """Send an email verification code without exposing it in logs or API responses."""
    html_content = f"""
    <div style="font-family: Arial, sans-serif; padding: 20px;">
        <h2>Verify your Scholar AI email</h2>
        <p>Your email verification code is:</p>
        <p style="font-size: 28px; font-weight: bold; letter-spacing: 6px;">{otp}</p>
        <p>This code will expire in {settings.EMAIL_VERIFICATION_OTP_EXPIRE_MINUTES} minutes.</p>
        <p>If you did not create this account, you can ignore this email.</p>
    </div>
    """
    from_email = settings.MAIL_FROM or "onboarding@resend.dev"
    from_name = settings.MAIL_FROM_NAME or "Scholar AI"
    resend.Emails.send(
        {
            "from": f"{from_name} <{from_email}>",
            "to": [email_to],
            "subject": "Verify your email - Scholar AI",
            "html": html_content,
        }
    )

def send_reset_password_email(email_to: str, token: str):
    # رابط إعادة التعيين الذي سيصل في الإيميل
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
        "from": "Scholar AI <onboarding@resend.dev>",  # الدومين المجاني التجريبي الموفر من Resend
        "to": [email_to],
        "subject": "إعادة تعيين كلمة المرور - Scholar AI",
        "html": html_content,
    }

    # إرسال البريد
    resend.Emails.send(params)
