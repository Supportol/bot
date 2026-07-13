import aiohttp
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse
from typing import Optional
import re
import unicodedata

PROJECT_ROOT = Path(__file__).parent.parent
IMAGES_DIR = PROJECT_ROOT / "images"

HTTP_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
    "Referer": "https://www.ixbt.com/",
}

CYRILLIC_MAP = str.maketrans(
    {
        "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "e",
        "ж": "zh", "з": "z", "и": "i", "й": "y", "к": "k", "л": "l", "м": "m",
        "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t", "у": "u",
        "ф": "f", "х": "h", "ц": "ts", "ч": "ch", "ш": "sh", "щ": "sch",
        "ъ": "", "ы": "y", "ь": "", "э": "e", "ю": "yu", "я": "ya",
    }
)

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

def _seo_alias(title: str, pub_id: str, max_length: int = 72) -> str:
    """Формирует короткий seo-friendly алиас файла из заголовка."""
    normalized = (title or "").strip().lower().translate(CYRILLIC_MAP)
    normalized = unicodedata.normalize("NFKD", normalized)
    normalized = normalized.encode("ascii", "ignore").decode("ascii")
    normalized = re.sub(r"[^a-z0-9]+", "-", normalized).strip("-")
    if not normalized:
        normalized = f"image-{pub_id.lower()}"
    return normalized[:max_length].strip("-")

async def save_publication_cover(pub_id: str, title: str, cover_url: str) -> Optional[str]:
    """Скачивает обложку и сохраняет в images/ДД.ММ.ГГГГ/<pub_id>/<seo-alias>.<ext>."""
    if not cover_url:
        return None

    date_dir = datetime.now().strftime("%d.%m.%Y")
    pub_dir = IMAGES_DIR / date_dir / str(pub_id)
    pub_dir.mkdir(parents=True, exist_ok=True)

    headers = dict(HTTP_HEADERS)
    if "drom.ru" in urlparse(cover_url).netloc:
        headers["Referer"] = "https://www.drom.ru/"

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(cover_url, headers=headers, timeout=15) as response:
                if response.status != 200:
                    print(f"[COVER] ❌ HTTP {response.status} для ID {pub_id}: {cover_url}")
                    return None
                image_bytes = await response.read()
                content_type = response.headers.get("Content-Type")

        ext = _cover_extension(cover_url, content_type)
        alias = _seo_alias(title, pub_id)
        cover_path = pub_dir / f"{alias}{ext}"
        cover_path.write_bytes(image_bytes)

        relative_path = cover_path.relative_to(PROJECT_ROOT).as_posix()
        print(f"[COVER] ✅ Сохранено ID {pub_id}: {relative_path}")
        return relative_path

    except (aiohttp.ClientError, OSError) as e:
        print(f"[COVER] ❌ Ошибка сохранения ID {pub_id}: {e}")
        return None

def get_publication_cover_path(pub_id: str) -> Optional[Path]:
    """Возвращает путь к сохранённой обложке публикации, если она есть."""
    candidate_dirs = [
        IMAGES_DIR / datetime.now().strftime("%d.%m.%Y") / str(pub_id),  # текущая структура
        IMAGES_DIR / str(pub_id),  # обратная совместимость со старой структурой
    ]

    # Если в ожидаемых директориях не нашли, пробуем поиск по всем папкам дат.
    if all(not d.exists() for d in candidate_dirs):
        candidate_dirs.extend(sorted(IMAGES_DIR.glob(f"*/{pub_id}"), reverse=True))

    for pub_dir in candidate_dirs:
        if not pub_dir.exists():
            continue
        for pattern in ("*.jpg", "*.jpeg", "*.png", "*.webp", "*.gif", "cover.*", "original.*"):
            matches = sorted(pub_dir.glob(pattern))
            if matches:
                return matches[0]

    return None
