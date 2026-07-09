import aiohttp
from pathlib import Path
from urllib.parse import urlparse
from typing import Optional

PROJECT_ROOT = Path(__file__).parent.parent
IMAGES_DIR = PROJECT_ROOT / "images"

HTTP_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
    "Referer": "https://www.ixbt.com/",
}

def _cover_extension(cover_url: str, content_type: str | None = None) -> str:
    path_ext = Path(urlparse(cover_url).path).suffix.lower()
    allowed = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
    if path_ext in allowed:
        return path_ext

    if content_type:
        mapping = {
            "image/jpeg": ".jpg",
            "image/png": ".png",
            "image/webp": ".webp",
            "image/gif": ".gif",
        }
        return mapping.get(content_type.split(";")[0].strip().lower(), ".jpg")

    return ".jpg"

async def save_publication_cover(pub_id: str, cover_url: str) -> Optional[str]:
    """Скачивает обложку и сохраняет в images/<pub_id>/cover.<ext> (напр. images/IX_HON_1/)."""
    if not cover_url:
        return None

    pub_dir = IMAGES_DIR / str(pub_id)
    pub_dir.mkdir(parents=True, exist_ok=True)

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(cover_url, headers=HTTP_HEADERS, timeout=15) as response:
                if response.status != 200:
                    print(f"[COVER] ❌ HTTP {response.status} для ID {pub_id}: {cover_url}")
                    return None
                image_bytes = await response.read()
                content_type = response.headers.get("Content-Type")

        ext = _cover_extension(cover_url, content_type)
        cover_path = pub_dir / f"cover{ext}"
        cover_path.write_bytes(image_bytes)

        relative_path = cover_path.relative_to(PROJECT_ROOT).as_posix()
        print(f"[COVER] ✅ Сохранено ID {pub_id}: {relative_path}")
        return relative_path

    except (aiohttp.ClientError, OSError) as e:
        print(f"[COVER] ❌ Ошибка сохранения ID {pub_id}: {e}")
        return None

def get_publication_cover_path(pub_id: str) -> Optional[Path]:
    """Возвращает путь к сохранённой обложке публикации, если она есть."""
    pub_dir = IMAGES_DIR / str(pub_id)
    if not pub_dir.exists():
        return None

    for pattern in ("cover.*", "original.*"):
        matches = sorted(pub_dir.glob(pattern))
        if matches:
            return matches[0]

    return None
