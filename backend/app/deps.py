import re

from fastapi import Header, HTTPException

_DEVICE_RE = re.compile(r"^[A-Za-z0-9_-]{43,128}$")


def require_device_id(x_device_id: str = Header(default="")) -> str:
    value = x_device_id.strip()
    if not _DEVICE_RE.fullmatch(value):
        raise HTTPException(status_code=401, detail="Missing or invalid X-Device-Id")
    return value
