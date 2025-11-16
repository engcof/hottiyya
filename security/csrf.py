import secrets
from fastapi import Request, HTTPException

def generate_csrf_token():
    return secrets.token_urlsafe(32)

def verify_csrf_token(request: Request, csrf_token: str):
    session_token = request.session.get("csrf_token")
    if not csrf_token or csrf_token != session_token:
        raise HTTPException(status_code=403, detail="رمز CSRF غير صالح أو مفقود")