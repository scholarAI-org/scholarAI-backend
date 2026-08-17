import resend
from app.core.config import settings

# ضبط مفتاح الـ API الخاص بـ Resend
resend.api_key = settings.RESEND_API_KEY

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