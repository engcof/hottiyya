from fastapi import Request
from typing import Optional
from fastapi.responses import HTMLResponse

def get_current_user(request: Request) -> Optional[dict]:
    return request.session.get("user")


def set_cache_headers(response: HTMLResponse):
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, proxy-revalidate'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response