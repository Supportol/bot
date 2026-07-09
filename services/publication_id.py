import re
from urllib.parse import parse_qs, urlparse

PUBLICATION_ID_PATTERN = re.compile(r"\b([A-Z]{2}_[A-Z]{2,3}_\d+)\b")

def get_source_id_prefix(source: str) -> str:
    """Возвращает префикс ID для источника публикации."""
    parsed = urlparse(source)
    host = (parsed.netloc or "").lower()
    query = parse_qs(parsed.query)

    if "ixbt.com" in host:
        search = (query.get("search", [""])[0] or "").strip().upper()
        if search == "HONDA":
            return "IX_HON"
        if search == "ACURA":
            return "IX_AC"

    if "drom.ru" in host or "drom.ru" in source:
        return "DR_HON"

    return "GEN"

def parse_publication_ids(text: str) -> list[str]:
    """Извлекает ID публикаций из текста команды."""
    return PUBLICATION_ID_PATTERN.findall(text.upper())

def next_publication_id(prefix: str, existing_ids: list[str]) -> str:
    """Выделяет следующий ID для префикса."""
    max_num = 0
    prefix_with_sep = f"{prefix}_"

    for pub_id in existing_ids:
        if not pub_id.startswith(prefix_with_sep):
            continue
        try:
            max_num = max(max_num, int(pub_id[len(prefix_with_sep):]))
        except ValueError:
            continue

    return f"{prefix}_{max_num + 1}"
