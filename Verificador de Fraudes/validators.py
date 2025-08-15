import re

ALLOWED_EXTS = {".png",".jpg",".jpeg",".webp",".bmp",".eml"}

def is_allowed_file(filename: str) -> bool:
    fn = (filename or "").lower().strip()
    return any(fn.endswith(ext) for ext in ALLOWED_EXTS)

def is_url(url: str) -> bool:
    return bool(re.match(r"^https?://", url or "", re.I))
