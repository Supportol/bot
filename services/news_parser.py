import aiohttp
import feedparser
import json
from typing import List, Dict
from bs4 import BeautifulSoup
import asyncio
from database.db import check_url_exists
from config import drom_sources_list, ixbt_sources_list, motor_sources_list, max_news_per_source
from services.datetime_utils import format_publication_datetime, drom_date_to_iso
from urllib.parse import urljoin, urlparse, parse_qs, urlencode, urlunparse
import re
from pathlib import Path

IXBT_BRAND_PATTERNS = {
    "ACURA": re.compile(r"\bAcura\b|\bАкура\b", re.IGNORECASE),
    "HONDA": re.compile(r"\bHonda\b|\bХонда\b", re.IGNORECASE),
}

def _get_ixbt_search_brand(api_url: str) -> str | None:
    """Извлекает бренд из параметра search в URL API iXBT."""
    params = parse_qs(urlparse(api_url).query)
    search = params.get("search", [None])[0]
    return search.strip().upper() if search else None

def _ixbt_publication_mentions_brand(pub: dict, brand: str) -> bool:
    """Проверяет прямое упоминание бренда в заголовке, подзаголовке и тегах."""
    pattern = IXBT_BRAND_PATTERNS.get(
        brand.upper(),
        re.compile(rf"\b{re.escape(brand)}\b", re.IGNORECASE),
    )
    text_parts = [
        pub.get("title", ""),
        pub.get("subtitle", ""),
        " ".join(tag.get("name", "") for tag in pub.get("tags", [])),
    ]
    return bool(pattern.search(" ".join(text_parts)))

def _ixbt_api_page_url(api_url: str, page: int) -> str:
    """Подставляет номер страницы в URL API iXBT."""
    parsed = urlparse(api_url)
    params = parse_qs(parsed.query)
    params["page"] = [str(page)]
    return urlunparse(parsed._replace(query=urlencode(params, doseq=True)))

def _ixbt_source_key(api_url: str) -> str:
    """Нормализует URL источника (всегда page=1) для хранения в БД."""
    return _ixbt_api_page_url(api_url, 1)

def _ixbt_publication_datetime(pub: dict) -> str | None:
    """Возвращает ISO-дату публикации (pubdatetime) из ответа API."""
    return pub.get("pubdatetime")

def _motor_source_key(api_url: str) -> str:
    """Нормализует URL источника Motor.ru (фиксирует offset=0)."""
    parsed = urlparse(api_url)
    params = parse_qs(parsed.query)
    params["offset"] = ["0"]
    return urlunparse(parsed._replace(query=urlencode(params, doseq=True)))

def _motor_publication_mentions_brand(topic: dict, brand: str) -> bool:
    attrs = topic.get("attributes", {})
    text = " ".join(
        [
            attrs.get("headline", ""),
            attrs.get("announce", ""),
            attrs.get("slug", ""),
        ]
    )
    pattern = IXBT_BRAND_PATTERNS.get(
        brand.upper(),
        re.compile(rf"\b{re.escape(brand)}\b", re.IGNORECASE),
    )
    return bool(pattern.search(text))

def _motor_cover_url(topic: dict, included_images: dict) -> str | None:
    rel_image = (topic.get("relationships", {}).get("image", {}) or {}).get("data")
    if not rel_image:
        return None
    image_obj = included_images.get(rel_image.get("id"))
    if not image_obj:
        return None
    versions = (image_obj.get("attributes", {}) or {}).get("versions", {})
    for preferred in ("list_large", "list_3/2", "list_16/9", "main", "thumbnail"):
        rel_url = ((versions.get(preferred) or {}).get("rel_url") or "").strip()
        if rel_url:
            return urljoin("https://motor.ru", rel_url)
    return None

def _parse_motor_topic(topic: dict, source_key: str, search_brand: str | None, included_images: dict) -> Dict | None:
    attrs = topic.get("attributes", {})
    title = (attrs.get("headline") or "").strip()
    rel_link = (attrs.get("link") or "").strip()
    if not title or not rel_link:
        return None

    if search_brand and not _motor_publication_mentions_brand(topic, search_brand):
        print(f"[MOTOR-API] ⚠️ Пропущено (нет упоминания {search_brand}): {title[:50]}...")
        return None

    return {
        "title": title,
        "url": urljoin("https://motor.ru", rel_link),
        "source": source_key,
        "cover_url": _motor_cover_url(topic, included_images),
        "published_at": attrs.get("published_at"),
    }

def _parse_ixbt_publication(pub: dict, source_key: str, search_brand: str | None) -> Dict | None:
    url = pub.get("url") or (pub.get("urls") or {}).get("ru")
    title = (pub.get("title") or "").strip()
    if not title or not url:
        return None

    if search_brand and not _ixbt_publication_mentions_brand(pub, search_brand):
        print(f"[IXBT-API] ⚠️ Пропущено (нет упоминания {search_brand}): {title[:50]}...")
        return None

    return {
        "title": title,
        "url": url,
        "source": source_key,
        "cover_url": pub.get("cover_url"),
        "published_at": _ixbt_publication_datetime(pub),
    }

async def parse_rss_feed(feed_url: str) -> List[Dict]:
    """Парсит RSS фид"""
    print(f"[RSS] Пытаюсь загрузить: {feed_url}")
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(feed_url, timeout=15) as response:
                print(f"[RSS] Статус ответа: {response.status}")
                if response.status == 200:
                    content = await response.text()
                    print(f"[RSS] Получено байт: {len(content)}")
                    feed = feedparser.parse(content)
                    print(f"[RSS] Найдено записей: {len(feed.entries)}")
                    
                    items = []
                    for entry in feed.entries[:max_news_per_source]:
                        items.append({
                            'title': entry.title,
                            'url': entry.link,
                            'source': feed_url
                        })
                    return items
    except Exception as e:
        print(f"[RSS] ❌ Ошибка при парсинге {feed_url}: {e}")
        return []
    
    return []

DROM_HTTP_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
    "Referer": "https://www.drom.ru/",
}

_DROM_IMAGE_EXTENSIONS = (".jpg", ".jpeg", ".png", ".webp")
_DROM_THUMBNAIL_RE = re.compile(r"(?:^|/)(?:gen\d+_|tn_)", re.IGNORECASE)


def _is_drom_raster_image_url(url: str) -> bool:
    if not url:
        return False
    path = urlparse(url).path.lower()
    return path.endswith(_DROM_IMAGE_EXTENSIONS)


def _is_drom_thumbnail_image_url(url: str) -> bool:
    if not url:
        return True
    return bool(_DROM_THUMBNAIL_RE.search(urlparse(url).path))


def _extract_drom_main_cover_url(soup: BeautifulSoup, article_url: str) -> str | None:
    """Главная обложка статьи: og:image или первое изображение в .b-media-cont."""
    og_image = soup.find("meta", property="og:image")
    if og_image and og_image.get("content"):
        return urljoin(article_url, og_image["content"])

    media_cont = soup.select_one(".b-media-cont")
    if media_cont:
        for img in media_cont.select("img"):
            src = (img.get("src") or img.get("data-src") or "").strip()
            if src and not src.lower().endswith(".svg"):
                return urljoin(article_url, src)

    return None


def _extract_drom_clickable_cover_url(soup: BeautifulSoup, article_url: str) -> str | None:
    """Первая кликабельная картинка статьи в нормальном разрешении (href ссылки, не превью)."""
    scopes = []
    for selector in (".b-left-side", ".b-media-cont", "div.news_img"):
        scopes.extend(soup.select(selector))

    seen_scopes = set()
    unique_scopes = []
    for scope in scopes:
        scope_id = id(scope)
        if scope_id in seen_scopes:
            continue
        seen_scopes.add(scope_id)
        unique_scopes.append(scope)

    if not unique_scopes:
        unique_scopes = [soup]

    for scope in unique_scopes:
        for link in scope.select("a[href]"):
            href = (link.get("href") or "").strip()
            if not _is_drom_raster_image_url(href):
                continue
            if _is_drom_thumbnail_image_url(href):
                continue
            if "/com/" in urlparse(href).path:
                continue

            img = link.select_one("img")
            if not img:
                continue

            src = (img.get("src") or img.get("data-src") or "").strip()
            if src.lower().endswith(".svg"):
                continue

            return urljoin(article_url, href)

    return None


def extract_drom_cover_url(
    html: str,
    article_url: str,
    fallback_url: str | None = None,
) -> str | None:
    """Выбирает обложку Drom: кликабельное фото -> главная -> fallback с ленты."""
    soup = BeautifulSoup(html, "lxml")

    clickable_cover = _extract_drom_clickable_cover_url(soup, article_url)
    if clickable_cover:
        return clickable_cover

    main_cover = _extract_drom_main_cover_url(soup, article_url)
    if main_cover:
        return main_cover

    return fallback_url


async def fetch_drom_cover_url(
    session: aiohttp.ClientSession,
    article_url: str,
    fallback_url: str | None = None,
) -> str | None:
    """Загружает страницу статьи Drom и возвращает URL обложки."""
    try:
        async with session.get(article_url, headers=DROM_HTTP_HEADERS, timeout=15) as response:
            if response.status != 200:
                print(f"[DROM] ⚠️ Не удалось загрузить статью {article_url}: HTTP {response.status}")
                return fallback_url
            html = await response.text()
    except Exception as e:
        print(f"[DROM] ⚠️ Ошибка загрузки статьи {article_url}: {e}")
        return fallback_url

    cover_url = extract_drom_cover_url(html, article_url, fallback_url=fallback_url)
    if cover_url and cover_url != fallback_url:
        print(f"[DROM] Cover from article: {cover_url}")
    return cover_url


async def parse_drom_honda(source_url: str) -> List[Dict]:
    """Парсер раздела Honda на news.drom.ru — карточки b-info-block на HTML-странице."""
    print(f"[DROM] Пытаюсь загрузить: {source_url}")

    try:
        headers = DROM_HTTP_HEADERS

        async with aiohttp.ClientSession() as session:
            async with session.get(source_url, headers=headers, timeout=15) as response:
                print(f"[DROM] Статус ответа: {response.status}")
                if response.status != 200:
                    return []

                html = await response.text()
                print(f"[DROM] Получено байт: {len(html)}")

            soup = BeautifulSoup(html, "lxml")
            items = []
            seen_urls = set()

            cards = soup.select(".b-info-block.b-info-block_like-text a.b-info-block__cont[href]")
            print(f"[DROM] Карточек на странице: {len(cards)}, лимит: {max_news_per_source}")

            for card in cards:
                if len(items) >= max_news_per_source:
                    break

                href = urljoin(source_url, card["href"])
                if href in seen_urls:
                    continue

                if "news.drom.ru" not in href or not href.endswith(".html"):
                    continue

                title_el = card.select_one(".b-info-block__title")
                title = title_el.get_text(strip=True) if title_el else ""
                if len(title) < 10:
                    continue

                date_el = card.select_one(".b-info-block__text_type_news-date")
                date_str = date_el.get_text(strip=True) if date_el else None
                published_at = drom_date_to_iso(date_str)

                img_el = card.select_one("img")
                listing_cover_url = img_el.get("src") if img_el and img_el.get("src") else None
                cover_url = await fetch_drom_cover_url(session, href, fallback_url=listing_cover_url)

                seen_urls.add(href)
                item = {
                    "title": title,
                    "url": href,
                    "source": source_url,
                    "published_at": published_at,
                    "cover_url": cover_url,
                }
                items.append(item)

                date_suffix = ""
                if published_at:
                    date_suffix = f" | {format_publication_datetime(published_at)}"
                print(f"[DROM] ✅ {title[:60]}...{date_suffix} | {href}")

            print(f"\n[DROM] ИТОГО взято новостей: {len(items)}")
            return items

    except Exception as e:
        print(f"[DROM] ❌ Ошибка при парсинге {source_url}: {e}")
        import traceback
        traceback.print_exc()
        return []

async def parse_ixbt_api(api_url: str) -> List[Dict]:
    """Парсер API iXBT: /api/publications/search с пагинацией."""
    print(f"[IXBT-API] Пытаюсь загрузить: {api_url}")

    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "application/json",
            "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
            "Referer": "https://www.ixbt.com/",
        }

        search_brand = _get_ixbt_search_brand(api_url)
        source_key = _ixbt_source_key(api_url)
        items = []
        page = 1
        last_page = 1
        max_pages = 30

        async with aiohttp.ClientSession() as session:
            while len(items) < max_news_per_source and page <= last_page and page <= max_pages:
                page_url = _ixbt_api_page_url(api_url, page)
                print(f"[IXBT-API] Страница {page}: {page_url}")

                async with session.get(page_url, headers=headers, timeout=15) as response:
                    print(f"[IXBT-API] Статус ответа: {response.status}")
                    if response.status != 200:
                        break

                    data = await response.json()

                meta = data.get("meta", {})
                last_page = meta.get("last_page", page)

                for pub in data.get("data", []):
                    if len(items) >= max_news_per_source:
                        break

                    item = _parse_ixbt_publication(pub, source_key, search_brand)
                    if not item:
                        continue

                    items.append(item)
                    date_suffix = ""
                    if item.get("published_at"):
                        date_suffix = f" | {format_publication_datetime(item['published_at'])}"
                    print(f"[IXBT-API] ✅ {item['title'][:50]}...{date_suffix}")

                if not data.get("data"):
                    break

                page += 1

        print(f"[IXBT-API] ИТОГО найдено новостей: {len(items)}")
        return items

    except (json.JSONDecodeError, aiohttp.ClientError, KeyError) as e:
        print(f"[IXBT-API] ❌ Ошибка при парсинге {api_url}: {e}")
        return []

async def parse_ixbt_sources() -> List[Dict]:
    """Парсит все источники из IXBT_SOURCES"""
    print(f"\n[IXBT] === Начало парсинга ===")
    print(f"[IXBT] Источников для обработки: {len(ixbt_sources_list)}")

    if not ixbt_sources_list:
        print("[IXBT] ⚠️ Список источников IXBT_SOURCES пустой!")
        return []

    results = await asyncio.gather(
        *[parse_ixbt_api(source_url) for source_url in ixbt_sources_list],
        return_exceptions=True,
    )

    seen_urls = set()
    items = []
    for i, result in enumerate(results):
        if isinstance(result, Exception):
            print(f"[IXBT] ❌ Исключение от источника {i}: {result}")
            continue
        for item in result:
            if item["url"] in seen_urls:
                continue
            seen_urls.add(item["url"])
            items.append(item)

    print(f"[IXBT] Всего уникальных публикаций: {len(items)}")
    print(f"[IXBT] === Конец парсинга ===\n")
    return items

async def parse_motor_api(api_url: str) -> List[Dict]:
    """Парсер API Motor.ru /api/bebop/v2/search."""
    print(f"[MOTOR-API] Пытаюсь загрузить: {api_url}")
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "application/json",
            "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
            "Referer": "https://motor.ru/",
        }
        search_brand = (parse_qs(urlparse(api_url).query).get("query", [None])[0] or "").strip().upper() or None
        source_key = _motor_source_key(api_url)
        items = []
        offset = 0
        page_size = min(max_news_per_source, 50)

        async with aiohttp.ClientSession() as session:
            while len(items) < max_news_per_source:
                parsed = urlparse(api_url)
                params = parse_qs(parsed.query)
                params["offset"] = [str(offset)]
                params["limit"] = [str(page_size)]
                page_url = urlunparse(parsed._replace(query=urlencode(params, doseq=True)))
                print(f"[MOTOR-API] Смещение {offset}: {page_url}")

                async with session.get(page_url, headers=headers, timeout=15) as response:
                    print(f"[MOTOR-API] Статус ответа: {response.status}")
                    if response.status != 200:
                        break
                    payload = await response.json()

                data = payload.get("data", [])
                included = payload.get("included", [])
                if not data:
                    break

                included_images = {
                    obj.get("id"): obj
                    for obj in included
                    if obj.get("type") == "image" and obj.get("id")
                }

                for topic in data:
                    if len(items) >= max_news_per_source:
                        break
                    item = _parse_motor_topic(topic, source_key, search_brand, included_images)
                    if not item:
                        continue
                    items.append(item)
                    date_suffix = ""
                    if item.get("published_at"):
                        date_suffix = f" | {format_publication_datetime(item['published_at'])}"
                    print(f"[MOTOR-API] ✅ {item['title'][:50]}...{date_suffix}")

                if len(data) < page_size:
                    break
                offset += page_size

        print(f"[MOTOR-API] ИТОГО найдено новостей: {len(items)}")
        return items
    except (json.JSONDecodeError, aiohttp.ClientError, KeyError) as e:
        print(f"[MOTOR-API] ❌ Ошибка при парсинге {api_url}: {e}")
        return []

async def parse_motor_sources() -> List[Dict]:
    """Парсит все API-источники Motor.ru (Honda/Acura)."""
    print(f"\n[MOTOR] === Начало парсинга ===")
    print(f"[MOTOR] Источников для обработки: {len(motor_sources_list)}")

    if not motor_sources_list:
        print("[MOTOR] ⚠️ Список источников MOTOR_* пустой!")
        return []

    results = await asyncio.gather(
        *[parse_motor_api(source_url) for source_url in motor_sources_list],
        return_exceptions=True,
    )

    seen_urls = set()
    items = []
    for i, result in enumerate(results):
        if isinstance(result, Exception):
            print(f"[MOTOR] ❌ Исключение от источника {i}: {result}")
            continue
        for item in result:
            if item["url"] in seen_urls:
                continue
            seen_urls.add(item["url"])
            items.append(item)

    print(f"[MOTOR] Всего уникальных публикаций: {len(items)}")
    print(f"[MOTOR] === Конец парсинга ===\n")
    return items

async def parse_ixbt_car(source_url: str) -> List[Dict]:
    """Специализированный парсер для iXBT.com раздел Автомобили"""
    print(f"[IXBT-CAR] Пытаюсь загрузить: {source_url}")
    
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
            "Referer": "https://www.ixbt.com/",
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.get(source_url, headers=headers, timeout=15) as response:
                print(f"[IXBT-CAR] Статус ответа: {response.status}")
                if response.status != 200:
                    return []
                
                html = await response.text()
                print(f"[IXBT-CAR] Получено байт: {len(html)}")
                soup = BeautifulSoup(html, 'lxml')
                
                items = []
                seen_urls = set()
                
                # Ищем ВСЕ ссылки на странице
                all_links = soup.find_all('a', href=True)
                print(f"[IXBT-CAR] Всего ссылок: {len(all_links)}")
                
                for link in all_links:
                    href = link.get('href', '')
                    title = link.get_text(strip=True)
                    
                    # 1. Минимальная длина заголовка - 25 символов
                    if len(title) < 25:
                        continue
                    
                    # 2. Убираем служебные слова
                    if title in ['Читать далее', 'Подробнее', 'Все новости', 'Комментарии']:
                        continue
                    
                    # 3. Преобразуем относительный URL в абсолютный
                    if not href.startswith('http'):
                        href = urljoin(source_url, href)
                    
                    # 4. Проверяем, что это iXBT
                    if 'ixbt.com' not in href:
                        continue
                    
                    # 5. ФИЛЬТРАЦИЯ: только автомобильные новости
                    if '/car/' not in href:
                        continue

                    # Исключаем категории (URL с только числами)
                    # /car/3855/ — это категория (НЕ НУЖНА)
                    # /car/deepal-g318-review.html — это статья (НУЖНА)
                    if re.search(r'/car/\d+/$', href):
                        print(f"[IXBT-CAR] ⚠️ Пропущена категория: {href}")
                        continue

                    # Исключаем главную страницу раздела
                    if href == 'https://www.ixbt.com/car/' or href == 'https://www.ixbt.com/car':
                        continue
                    
                    # 6. Убираем дубликаты
                    if href in seen_urls:
                        continue
                    
                    seen_urls.add(href)
                    items.append({
                        'title': title,
                        'url': href,
                        'source': source_url
                    })
                    
                    print(f"[IXBT-CAR] ✅ {title[:50]}... | {href}")
                
                print(f"[IXBT-CAR] ИТОГО найдено новостей: {len(items)}")
                return items[:max_news_per_source]
                    
    except Exception as e:
        print(f"[IXBT-CAR] ❌ Ошибка при парсинге {source_url}: {e}")
        import traceback
        traceback.print_exc()
        return []
    
    return []

async def parse_motor_search(source_url: str) -> List[Dict]:
    """Специализированный парсер для Motor.ru поиск"""
    print(f"[MOTOR] Пытаюсь загрузить: {source_url}")
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.get(source_url, headers=headers, timeout=15) as response:
                print(f"[MOTOR] Статус ответа: {response.status}")
                if response.status == 200:
                    html = await response.text()
                    print(f"[MOTOR] Получено байт: {len(html)}")
                    soup = BeautifulSoup(html, 'lxml')
                    
                    items = []
                    all_links = soup.find_all('a', href=True)
                    
                    for link in all_links:
                        href = link.get('href', '')
                        title = link.get_text(strip=True)
                        
                        if '/news/' in href or '/articles/' in href or '/test-drives/' in href:
                            if len(title) >= 10 and title not in ['Читать далее', 'Подробнее']:
                                if not href.startswith('http'):
                                    href = urljoin(source_url, href)
                                
                                items.append({
                                    'title': title,
                                    'url': href,
                                    'source': source_url
                                })
                    
                    seen_urls = set()
                    unique_items = []
                    for item in items:
                        if item['url'] not in seen_urls:
                            seen_urls.add(item['url'])
                            unique_items.append(item)
                    
                    print(f"[MOTOR] Найдено новостей: {len(unique_items)}")
                    return unique_items[:max_news_per_source]
                    
    except Exception as e:
        print(f"[MOTOR] ❌ Ошибка при парсинге {source_url}: {e}")
        return []
    
    return []

async def parse_generic_html(source_url: str) -> List[Dict]:
    """Универсальный HTML парсер для других сайтов"""
    print(f"[HTML] Пытаюсь загрузить: {source_url}")
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.get(source_url, headers=headers, timeout=15) as response:
                print(f"[HTML] Статус ответа: {response.status}")
                if response.status == 200:
                    html = await response.text()
                    print(f"[HTML] Получено байт: {len(html)}")
                    soup = BeautifulSoup(html, 'lxml')
                    
                    items = []
                    
                    articles = soup.find_all('article')
                    for article in articles[:max_news_per_source]:
                        link = article.find('a', href=True)
                        title_elem = article.find(['h1', 'h2', 'h3', 'h4'])
                        
                        if link and title_elem:
                            href = link.get('href', '')
                            title = title_elem.get_text(strip=True)
                            
                            if len(title) >= 10:
                                if not href.startswith('http'):
                                    href = urljoin(source_url, href)
                                
                                items.append({
                                    'title': title,
                                    'url': href,
                                    'source': source_url
                                })
                    
                    if not items:
                        news_classes = ['news', 'article', 'post', 'item', 'story', 'entry']
                        for class_name in news_classes:
                            containers = soup.find_all(class_=lambda x: x and class_name in x.lower())
                            for container in containers[:max_news_per_source]:
                                link = container.find('a', href=True)
                                title_elem = container.find(['h1', 'h2', 'h3', 'h4'])
                                
                                if link and title_elem:
                                    href = link.get('href', '')
                                    title = title_elem.get_text(strip=True)
                                    
                                    if len(title) >= 10:
                                        if not href.startswith('http'):
                                            href = urljoin(source_url, href)
                                        
                                        items.append({
                                            'title': title,
                                            'url': href,
                                            'source': source_url
                                        })
                    
                    seen_urls = set()
                    unique_items = []
                    for item in items:
                        if item['url'] not in seen_urls:
                            seen_urls.add(item['url'])
                            unique_items.append(item)
                    
                    print(f"[HTML] Найдено новостей: {len(unique_items)}")
                    return unique_items[:max_news_per_source]
                    
    except Exception as e:
        print(f"[HTML] ❌ Ошибка при парсинге {source_url}: {e}")
        return []
    
    return []

async def parse_new_sources() -> List[Dict]:
    """Парсит все источники и возвращает только новые публикации"""
    print(f"\n[PARSER] === Начало парсинга ===")
    print(f"[PARSER] Источников для обработки: {len(drom_sources_list)}")
    print(f"[PARSER] Лимит новостей с источника: {max_news_per_source}")
    
    if not drom_sources_list:
        print("[PARSER] ⚠️ Список источников ПУСТОЙ!")
        return []
    
    all_items = []
    tasks = []
    
    for source in drom_sources_list:
        source = source.strip()
        if not source:
            continue
        
        domain = urlparse(source).netloc.lower()
        
        if any(keyword in source.lower() for keyword in ['rss', 'feed', 'xml', 'atom']):
            print(f"[PARSER] Источник определён как RSS: {source}")
            tasks.append(parse_rss_feed(source))
        elif 'drom.ru' in domain:
            print(f"[PARSER] Источник определён как Drom.ru: {source}")
            tasks.append(parse_drom_honda(source))
        elif 'ixbt.com' in domain:
            print(f"[PARSER] Источник определён как iXBT.com: {source}")
            tasks.append(parse_ixbt_car(source))
        elif 'motor.ru' in domain:
            print(f"[PARSER] Источник определён как Motor.ru: {source}")
            tasks.append(parse_motor_search(source))
        else:
            print(f"[PARSER] Источник определён как HTML: {source}")
            tasks.append(parse_generic_html(source))
    
    if not tasks:
        print("[PARSER] ⚠️ Нет задач для выполнения!")
        return []
    
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    for i, result in enumerate(results):
        if isinstance(result, Exception):
            print(f"[PARSER] ❌ Исключение от источника {i}: {result}")
        elif isinstance(result, list):
            print(f"[PARSER] ✅ От источника {i} получено {len(result)} элементов")
            all_items.extend(result)
    
    print(f"[PARSER] Всего собрано элементов: {len(all_items)}")
    
    new_items = []
    for item in all_items:
        exists = await check_url_exists(item['url'])
        if not exists:
            new_items.append(item)
        else:
            print(f"[PARSER] Пропущено (уже в БД): {item['url'][:50]}...")
    
    print(f"[PARSER] Новых элементов: {len(new_items)}")
    print(f"[PARSER] === Конец парсинга ===\n")
    
    return new_items