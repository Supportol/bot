import aiohttp
import trafilatura
from typing import Optional
from urllib.parse import quote, urlparse
import re
import json
from bs4 import BeautifulSoup

MOTOR_TOPICS_API = "https://motor.ru/api/bebop/v2/topics"

async def _extract_motor_text_via_api(url: str) -> str | None:
    """Fallback для Motor.ru: получает полный текст из content widgets API."""
    target_path = urlparse(url).path

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "application/json",
    }

    async with aiohttp.ClientSession() as session:
        # 1) Прямой запрос конкретной публикации по path.
        encoded_path = quote(target_path, safe="")
        direct_url = f"{MOTOR_TOPICS_API}/{encoded_path}"
        async with session.get(
            direct_url,
            headers=headers,
            params={"include": "all"},
            timeout=aiohttp.ClientTimeout(total=15),
        ) as response:
            if response.status == 200:
                payload = await response.json()
                data = payload.get("data", {})
                attrs = data.get("attributes", {})
                headline = (attrs.get("headline") or "").strip()

                body_parts = []
                for obj in payload.get("included", []):
                    if obj.get("type") != "content":
                        continue
                    widgets = (obj.get("attributes", {}) or {}).get("widgets", [])
                    for widget in widgets:
                        body = ((widget.get("attributes") or {}).get("body") or "").strip()
                        if body:
                            body_parts.append(body)

                if body_parts:
                    full_body = "\n\n".join(body_parts)
                    full_body = re.split(r"\n\*\*Читайте также:?\s*\*\*", full_body, maxsplit=1)[0].strip()
                    parts = [p for p in (headline, full_body) if p]
                    if parts:
                        return "\n\n".join(parts)

        # 2) Фолбэк на старую стратегию (headline + announce) через ленту topics.
        page_size = 100
        max_pages = 10
        for page in range(max_pages):
            params = {"offset": page * page_size, "limit": page_size, "include": "image,rubric"}
            async with session.get(MOTOR_TOPICS_API, headers=headers, params=params, timeout=aiohttp.ClientTimeout(total=15)) as response:
                if response.status != 200:
                    continue
                payload = await response.json()
            data = payload.get("data", [])
            if not data:
                break
            for item in data:
                attrs = item.get("attributes", {})
                if attrs.get("link") != target_path:
                    continue
                headline = (attrs.get("headline") or "").strip()
                announce = (attrs.get("announce") or "").strip()
                parts = [p for p in (headline, announce) if p]
                if parts:
                    return "\n\n".join(parts)
            if len(data) < page_size:
                break
    return None

def _extract_ixbt_text_from_html(html: str) -> str | None:
    """Fallback для iXBT: берёт полный текст из embedded Publication JSON."""
    soup = BeautifulSoup(html, "lxml")

    # 1) Основной вариант: embedded JSON с полным набором блоков статьи.
    for script in soup.find_all("script"):
        raw = (script.string or script.get_text() or "").strip()
        if not raw.startswith('{"component":"Publication"'):
            continue
        try:
            obj = json.loads(raw)
        except json.JSONDecodeError:
            continue

        blocks = (
            obj.get("props", {})
            .get("publication", {})
            .get("blocks", [])
        )
        parts = []
        for block in blocks:
            block_html = (block.get("html") or "").strip()
            if not block_html:
                continue
            text = BeautifulSoup(block_html, "lxml").get_text(" ", strip=True)
            if text:
                parts.append(text)

        if parts:
            return "\n\n".join(parts)

    # 2) Фолбэк: JSON-LD summary.
    for script in soup.select('script[type="application/ld+json"]'):
        raw = (script.string or "").strip()
        if not raw:
            continue
        try:
            obj = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if obj.get("@type") != "NewsArticle":
            continue
        headline = (obj.get("headline") or "").strip()
        description = (obj.get("description") or "").strip()
        parts = [p for p in (headline, description) if p]
        if parts:
            return "\n\n".join(parts)
    return None

async def extract_text_from_url(url: str) -> str:
    """Скачивает страницу и извлекает чистый текст"""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
    }
    
    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=15)) as response:
            response.raise_for_status()
            html = await response.text()
    
    # Извлекаем основной текст страницы
    extracted_text = trafilatura.extract(
        html,
        include_comments=False,
        include_tables=True,
        favor_precision=True,
        include_images=False,
        include_links=False
    )
    
    # Нормализуем неинформативные результаты trafilatura.
    if extracted_text:
        extracted_text = extracted_text.strip()
        if extracted_text.lower() in {"перейти к содержимому", "skip to content"}:
            extracted_text = ""

    if not extracted_text:
        host = urlparse(url).netloc.lower()

        # Motor.ru часто отдаёт auth-controller вместо HTML статьи.
        if "motor.ru" in host:
            api_text = await _extract_motor_text_via_api(url)
            if api_text:
                return api_text

        # На iXBT часть новостей рендерится скриптами, в HTML остаётся JSON-LD.
        if "ixbt.com" in host:
            ixbt_text = _extract_ixbt_text_from_html(html)
            if ixbt_text:
                return ixbt_text

        raise ValueError("Не удалось извлечь текст из страницы")
    
    return extracted_text.strip()