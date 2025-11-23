from fastapi import Request, HTTPException, status
from typing import Optional
from fastapi.responses import HTMLResponse

def get_current_user(request: Request) -> dict:
    user = request.session.get("user")
    if not user:
        # رجّعه للogin فورًا لو مفيش يوزر
        raise HTTPException(
            status_code=status.HTTP_303_SEE_OTHER,
            headers={"Location": "/auth/login"}
        )
    return user


def set_cache_headers(response: HTMLResponse):
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, proxy-revalidate'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response