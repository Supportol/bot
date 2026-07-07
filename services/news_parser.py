import aiohttp
import feedparser
from typing import List, Dict
from bs4 import BeautifulSoup
import asyncio
from database.db import check_url_exists
from config import news_sources_list, max_news_per_source
from urllib.parse import urljoin, urlparse
import re
from pathlib import Path

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

async def parse_drom_honda(source_url: str) -> List[Dict]:
    """Специализированный парсер для Drom.ru раздел Honda"""
    print(f"[DROM] Пытаюсь загрузить: {source_url}")
    
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
            "Referer": "https://www.drom.ru/",
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.get(source_url, headers=headers, timeout=15) as response:
                print(f"[DROM] Статус ответа: {response.status}")
                if response.status != 200:
                    return []
                
                html = await response.text()
                print(f"[DROM] Получено байт: {len(html)}")
                soup = BeautifulSoup(html, 'lxml')
                
                items = []
                seen_urls = set()
                
                # СТРАТЕГИЯ 1: Ищем блоки b-info-block (основная структура Drom)
                print("[DROM] Стратегия 1: Поиск блоков b-info-block")
                info_blocks = soup.find_all(class_=lambda x: x and 'b-info-block' in str(x))
                print(f"[DROM] Найдено блоков b-info-block: {len(info_blocks)}")
                
                for block in info_blocks:
                    # Ищем ссылку-заголовок внутри блока
                    # Обычно это <a> с классом содержащим "link" или просто первая длинная ссылка
                    link = block.find('a', href=True)
                    
                    if not link:
                        continue
                    
                    href = link.get('href', '')
                    title = link.get_text(strip=True)
                    
                    # Если заголовок пустой или слишком короткий, ищем другой <a>
                    if len(title) < 15:
                        # Пробуем найти заголовок в h1-h4 внутри блока
                        header = block.find(['h1', 'h2', 'h3', 'h4'])
                        if header:
                            title = header.get_text(strip=True)
                            inner_link = header.find('a', href=True)
                            if inner_link:
                                href = inner_link.get('href', '')
                    
                    # Фильтруем по длине заголовка
                    if len(title) < 15:
                        continue
                    
                    # Убираем служебные слова
                    if title in ['Читать далее', 'Подробнее', 'Все новости', 'Комментарии']:
                        continue
                    
                    # Преобразуем относительный URL в абсолютный
                    if not href.startswith('http'):
                        href = urljoin(source_url, href)
                    
                    # Проверяем, что это Drom
                    if 'drom.ru' not in href:
                        continue
                    
                    # Фильтруем служебные ссылки
                    if any(path in href for path in ['/users/', '/profile', '/login', '/register', '/search', '/tags/', '/all/', '/top/', '/forum/', '/feedback', '/about', '/contacts', '/advert', '/rss', '/sitemap', '/my_region']):
                        continue
                    
                    # Убираем дубликаты
                    if href in seen_urls:
                        continue
                    
                    seen_urls.add(href)
                    items.append({
                        'title': title,
                        'url': href,
                        'source': source_url
                    })
                    
                    print(f"[DROM] ✅ {title[:60]}... | {href}")
                
                # СТРАТЕГИЯ 2: Если не нашли, ищем все длинные ссылки с /info/ или /honda/
                if len(items) == 0:
                    print("[DROM] Стратегия 1 не сработала, пробую стратегию 2")
                    all_links = soup.find_all('a', href=True)
                    
                    for link in all_links:
                        href = link.get('href', '')
                        title = link.get_text(strip=True)
                        
                        if len(title) < 15:
                            continue
                        
                        if not href.startswith('http'):
                            href = urljoin(source_url, href)
                        
                        if 'drom.ru' not in href:
                            continue
                        
                        # Новости Drom обычно имеют /info/ или числовой ID
                        is_news = False
                        if '/info/' in href:
                            is_news = True
                        elif re.search(r'/\d{7,}\.html', href):
                            is_news = True
                        elif '/honda/' in href and re.search(r'/\d+', href):
                            is_news = True
                        
                        if not is_news:
                            continue
                        
                        if href in seen_urls:
                            continue
                        
                        seen_urls.add(href)
                        items.append({
                            'title': title,
                            'url': href,
                            'source': source_url
                        })
                        
                        print(f"[DROM] ✅ (страт.2) {title[:60]}... | {href}")
                
                # СТРАТЕГИЯ 3: Если всё ещё ничего, ищем по датам
                if len(items) == 0:
                    print("[DROM] Стратегия 2 не сработала, пробую стратегию 3 (по датам)")
                    # Ищем блоки с датами вида DD.MM.YYYY
                    date_pattern = re.compile(r'\d{2}\.\d{2}\.\d{4}')
                    date_elements = soup.find_all(string=date_pattern)
                    
                    for elem in date_elements:
                        parent = elem.parent
                        # Поднимаемся на 3-5 уровней вверх, чтобы найти контейнер новости
                        for _ in range(5):
                            if parent is None:
                                break
                            parent = parent.parent
                            
                            link = parent.find('a', href=True)
                            if link:
                                href = link.get('href', '')
                                title = link.get_text(strip=True)
                                
                                if len(title) >= 15 and 'drom.ru' in href:
                                    if not href.startswith('http'):
                                        href = urljoin(source_url, href)
                                    
                                    if href not in seen_urls and '/my_region' not in href:
                                        seen_urls.add(href)
                                        items.append({
                                            'title': title,
                                            'url': href,
                                            'source': source_url
                                        })
                                        print(f"[DROM] ✅ (страт.3) {title[:60]}... | {href}")
                                        break
                
                print(f"\n[DROM] ИТОГО найдено новостей: {len(items)}")
                return items[:max_news_per_source]
                    
    except Exception as e:
        print(f"[DROM] ❌ Ошибка при парсинге {source_url}: {e}")
        import traceback
        traceback.print_exc()
        return []
    
    return []

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
                    
                    # 5. ПРОСТАЯ ФИЛЬТРАЦИЯ: новости имеют /news/ в URL
                    if '/car/' not in href:
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
    print(f"[PARSER] Источников для обработки: {len(news_sources_list)}")
    print(f"[PARSER] Лимит новостей с источника: {max_news_per_source}")
    
    if not news_sources_list:
        print("[PARSER] ⚠️ Список источников ПУСТОЙ!")
        return []
    
    all_items = []
    tasks = []
    
    for source in news_sources_list:
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