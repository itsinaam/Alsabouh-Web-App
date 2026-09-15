import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import List, Union
from app.config.settings import settings


class EmailService:
    """
    Unified Email notification service using Gmail SMTP / standard SMTP server.
    Configured via .env credentials using python-decouple.
    """

    def __init__(self):
        self.host = settings.SMTP_HOST
        self.port = settings.SMTP_PORT
        self.user = settings.SMTP_USER
        self.password = settings.SMTP_PASSWORD
        self.from_name = settings.EMAILS_FROM_NAME

    def send_email(
        self,
        to_email: Union[str, List[str]],
        subject: str,
        html_content: str,
        text_content: str = "",
    ) -> bool:
        """
        Sends an email with HTML and fallback plain text content.
        """
        if not self.user or not self.password:
            print("[EmailService] SMTP credentials not fully configured. Email skipped.")
            return False

        recipients = [to_email] if isinstance(to_email, str) else to_email

        message = MIMEMultipart("alternative")
        message["Subject"] = subject
        message["From"] = f"{self.from_name} <{self.user}>"
        message["To"] = ", ".join(recipients)

        if text_content:
            message.attach(MIMEText(text_content, "plain"))
        message.attach(MIMEText(html_content, "html"))

        try:
            with smtplib.SMTP(self.host, self.port) as server:
                server.starttls()
                server.login(self.user, self.password)
                server.sendmail(self.user, recipients, message.as_string())
            print(f"[EmailService] Email successfully sent to {recipients} | Subject: {subject}")
            return True
        except Exception as e:
            print(f"[EmailService] Failed to send email: {e}")
            return False

    def send_welcome_credentials_email(
        self,
        to_email: str,
        full_name: str,
        generated_password: str,
        role: str = "User",
    ) -> bool:
        """
        Single unified modern welcome email template for ALL users (Driver, Store Manager, Admin).
        Dispatches login credentials (email & auto-generated password).
        """
        formatted_role = role.replace("_", " ").title()
        subject = f"Your {self.from_name} Account Credentials ({formatted_role})"
        
        html = f"""
        <div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; max-width: 580px; margin: 0 auto; padding: 30px; border: 1px solid #e2e8f0; border-radius: 12px; background-color: #ffffff; color: #1e293b;">
            <div style="text-align: center; margin-bottom: 24px;">
                <h1 style="color: #0f172a; margin: 0; font-size: 26px; font-weight: 700; letter-spacing: -0.5px;">{self.from_name}</h1>
                <p style="color: #64748b; margin-top: 4px; font-size: 14px;">Fleet & Logistics Management Portal</p>
            </div>
            
            <p style="font-size: 16px; margin-bottom: 16px;">Hello <strong>{full_name}</strong>,</p>
            <p style="font-size: 14px; line-height: 1.6; color: #334155; margin-bottom: 20px;">
                Welcome to <strong>{self.from_name}</strong>! Your account has been registered with the role of <strong>{formatted_role}</strong>. You can now access the system using your login credentials below:
            </p>
            
            <div style="background-color: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px; padding: 18px 22px; margin: 24px 0;">
                <div style="margin-bottom: 12px;">
                    <span style="font-size: 12px; font-weight: 600; text-transform: uppercase; color: #64748b; display: block; margin-bottom: 2px;">Assigned Role</span>
                    <span style="font-size: 15px; font-weight: 600; color: #2563eb;">{formatted_role}</span>
                </div>
                <div style="margin-bottom: 12px;">
                    <span style="font-size: 12px; font-weight: 600; text-transform: uppercase; color: #64748b; display: block; margin-bottom: 2px;">Login Email</span>
                    <span style="font-size: 15px; font-weight: 500; color: #0f172a;">{to_email}</span>
                </div>
                <div>
                    <span style="font-size: 12px; font-weight: 600; text-transform: uppercase; color: #64748b; display: block; margin-bottom: 2px;">Temporary Password</span>
                    <code style="background-color: #e2e8f0; padding: 4px 10px; border-radius: 6px; font-size: 15px; font-weight: 700; color: #0f172a; display: inline-block;">{generated_password}</code>
                </div>
            </div>
            
            <div style="background-color: #fffbeb; border-left: 4px solid #f59e0b; padding: 10px 14px; border-radius: 4px; margin-bottom: 24px;">
                <p style="font-size: 13px; color: #b45309; margin: 0; line-height: 1.5;">
                    <strong>Security Notice:</strong> Please change your password after logging in for the first time.
                </p>
            </div>
            
            <hr style="border: none; border-top: 1px solid #e2e8f0; margin: 24px 0;" />
            <p style="font-size: 12px; color: #94a3b8; text-align: center; margin: 0;">
                This is an automated message from {self.from_name}. If you did not expect this, please contact your administrator.
            </p>
        </div>
        """
        text = (
            f"Welcome to {self.from_name}, {full_name}!\n\n"
            f"Your account credentials:\n"
            f"Role: {formatted_role}\n"
            f"Email: {to_email}\n"
            f"Password: {generated_password}\n\n"
            f"Please change your password upon initial login."
        )
        return self.send_email(to_email=to_email, subject=subject, html_content=html, text_content=text)

    # Backward-compatible alias so existing driver registration code calls the unified template
    send_driver_credentials_email = send_welcome_credentials_email


email_service = EmailService()
