from datetime import datetime

DISPLAY_FORMAT = "%d.%m.%Y %H:%M"

def format_publication_datetime(value: str | None) -> str:
    """Форматирует ISO pubdatetime в ДД.ММ.ГГГГ чч:мм."""
    if not value:
        return "—"

    try:
        return datetime.fromisoformat(value).strftime(DISPLAY_FORMAT)
    except (ValueError, TypeError):
        return "—"

def publication_sort_key(pub: dict) -> tuple:
    """Ключ сортировки: новые публикации сверху."""
    return (pub.get("published_at") or "", pub.get("created_at") or "")
