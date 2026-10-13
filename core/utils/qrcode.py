from io import BytesIO

import qrcode


def make_qrcode_png(data: str) -> bytes:
    """PNG bytes of a QR code. Reusable for responses, e-mail attachments, uploads."""
    buffer = BytesIO()
    qrcode.make(data).save(buffer, format="PNG")
    return buffer.getvalue()
