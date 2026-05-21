import qrcode
import uuid
from io import BytesIO
from typing import Optional


def generate_qr_code(token_id: str) -> bytes:
    """Generate QR code for a token"""
    qr_data = f"workspace://access?token={token_id}"
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=10,
        border=4,
    )
    qr.add_data(qr_data)
    qr.make(fit=True)
    
    img = qr.make_image(fill_color="black", back_color="white")
    img_byte_arr = BytesIO()
    img.save(img_byte_arr, format='PNG')
    img_byte_arr.seek(0)
    return img_byte_arr.getvalue()


def generate_uuid() -> str:
    """Generate a UUID"""
    return str(uuid.uuid4())
