import base64
import httpx
from typing import Optional
from app.core.config import settings
from app.utils.qr_generator import generate_qr_code
from app.services.qr_service import QRTokenService
from motor.motor_asyncio import AsyncIOMotorDatabase


class EmailService:
    """Service for sending emails via Resend"""
    
    def __init__(self, db: Optional[AsyncIOMotorDatabase] = None):
        self.db = db
        self.resend_api_key = settings.resend_api_key
        self.from_email = settings.resend_from_email
        self.from_name = settings.resend_from_name
        self.base_url = "https://api.resend.com"
    
    def _get_headers(self) -> dict:
        """Get headers for Resend API"""
        return {
            "Authorization": f"Bearer {self.resend_api_key}",
            "Content-Type": "application/json"
        }
    
    async def send_welcome_email_with_qr(
        self, 
        user_id: str,
        user_email: str, 
        user_name: str,
        matric_number: Optional[str] = None
    ) -> dict:
        """
        Send welcome email to user with QR code
        
        Args:
            user_id: User ID for QR token generation
            user_email: Email address to send to
            user_name: Full name of the user
            matric_number: Optional matric/student number
        
        Returns:
            Response from Resend API
        """
        try:
            if not self.resend_api_key:
                raise ValueError("Resend API key not configured in environment variables")
            
            # Generate QR token
            if self.db is not None:
                qr_service = QRTokenService(self.db)
                token = await qr_service.create_qr_token(user_id)  # Create QR token
                qr_bytes = generate_qr_code(token.id)
            else:
                # Fallback: use user_id directly if no DB
                qr_bytes = generate_qr_code(user_id)
            
            # Encode QR code to base64
            qr_base64 = base64.b64encode(qr_bytes).decode('utf-8')
            
            # Create HTML email content
            html_content = f"""
            <!DOCTYPE html>
            <html>
                <head>
                    <meta charset="UTF-8">
                    <title>Welcome to CSCATTENDANCE Entry System</title>
                    <style>
                        body {{
                            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Helvetica Neue', sans-serif;
                            line-height: 1.6;
                            color: #333;
                            max-width: 600px;
                            margin: 0 auto;
                            padding: 20px;
                        }}
                        .container {{
                            background-color: #f9fafb;
                            border-radius: 8px;
                            padding: 40px;
                            text-align: center;
                        }}
                        .header {{
                            color: #1f2937;
                            margin-bottom: 30px;
                        }}
                        .header h1 {{
                            margin: 0 0 10px 0;
                            font-size: 28px;
                        }}
                        .content {{
                            text-align: left;
                            margin: 30px 0;
                        }}
                        .qr-section {{
                            background-color: white;
                            padding: 30px;
                            border-radius: 8px;
                            margin: 30px 0;
                            text-align: center;
                        }}
                        .qr-section img {{
                            max-width: 250px;
                            height: auto;
                            margin: 20px 0;
                        }}
                        .user-details {{
                            background-color: #e5e7eb;
                            padding: 15px;
                            border-radius: 4px;
                            margin: 20px 0;
                            text-align: left;
                        }}
                        .user-details p {{
                            margin: 8px 0;
                        }}
                        .label {{
                            font-weight: 600;
                            color: #374151;
                        }}
                        .footer {{
                            margin-top: 40px;
                            font-size: 12px;
                            color: #6b7280;
                            border-top: 1px solid #e5e7eb;
                            padding-top: 20px;
                        }}
                        .cta-button {{
                            display: inline-block;
                            background-color: #3b82f6;
                            color: white;
                            padding: 12px 30px;
                            text-decoration: none;
                            border-radius: 4px;
                            margin-top: 20px;
                            font-weight: 600;
                        }}
                    </style>
                </head>
                <body>
                    <div class="container">
                        <div class="header">
                            <h1>Welcome to CSCATTENDANCE!</h1>
                            <p>Your entry system registration is complete</p>
                        </div>
                        
                        <div class="content">
                            <p>Hi {user_name},</p>
                            <p>You have been successfully registered in the <strong>CSCATTENDANCE Entry System</strong>. Below is your unique QR code that grants you access to the workspace.</p>
                            
                            <div class="user-details">
                                <p><span class="label">Name:</span> {user_name}</p>
                                <p><span class="label">Email:</span> {user_email}</p>
                                {f'<p><span class="label">Matric Number:</span> {matric_number}</p>' if matric_number else ''}
                            </div>
                            
                            <div class="qr-section">
                                <h2 style="margin-top: 0;">Your Access QR Code</h2>
                                <p>Present this QR code at any kiosk for instant access:</p>
                                <img src="data:image/png;base64,{qr_base64}" alt="Access QR Code">
                                <p style="font-size: 12px; color: #6b7280;">This QR code is valid for 30 days</p>
                            </div>
                            
                            <p><strong>How to use:</strong></p>
                            <ul>
                                <li>Take a screenshot or print this email</li>
                                <li>Present the QR code at any CSCATTENDANCE kiosk</li>
                                <li>Your access will be logged automatically</li>
                            </ul>
                            
                            <p>If you have any questions or need assistance, please contact the CSCATTENDANCE administration.</p>
                        </div>
                        
                        <div class="footer">
                            <p>This is an automated message from CSCATTENDANCE Entry System. Please do not reply to this email.</p>
                            <p>&copy; 2026 CSCATTENDANCE. All rights reserved.</p>
                        </div>
                    </div>
                </body>
            </html>
            """
            
            # Prepare payload for Resend API
            payload = {
                "from": f"{self.from_name} <{self.from_email}>",
                "to": user_email,
                "subject": f"Welcome to CSCATTENDANCE Entry System - Your Access QR Code",
                "html": html_content
            }
            
            # Send via Resend
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.base_url}/emails",
                    json=payload,
                    headers=self._get_headers(),
                    timeout=10.0
                )
                response.raise_for_status()
                return response.json()
        
        except httpx.HTTPError as e:
            print(f"HTTP Error sending email to {user_email}: {str(e)}")
            raise
        except Exception as e:
            print(f"Error sending welcome email to {user_email}: {str(e)}")
            raise
    
    async def send_email(
        self,
        to_email: str,
        subject: str,
        html_content: str,
        reply_to: Optional[str] = None
    ) -> dict:
        """
        Send a custom email
        
        Args:
            to_email: Recipient email address
            subject: Email subject
            html_content: HTML email content
            reply_to: Optional reply-to email address
        
        Returns:
            Response from Resend API
        """
        try:
            if not self.resend_api_key:
                raise ValueError("Resend API key not configured")
            
            payload = {
                "from": f"{self.from_name} <{self.from_email}>",
                "to": to_email,
                "subject": subject,
                "html": html_content
            }
            
            if reply_to:
                payload["reply_to"] = reply_to
            
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.base_url}/emails",
                    json=payload,
                    headers=self._get_headers(),
                    timeout=10.0
                )
                response.raise_for_status()
                return response.json()
        
        except Exception as e:
            print(f"Error sending email to {to_email}: {str(e)}")
            raise
