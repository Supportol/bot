import aiosqlite
from pathlib import Path
from typing import List, Dict, Optional

DB_PATH = Path(__file__).parent.parent / "bot_database.db"

async def _ensure_publication_columns(db: aiosqlite.Connection):
    """Добавляет новые колонки в существующую БД."""
    cursor = await db.execute("PRAGMA table_info(publications)")
    columns = {row[1] for row in await cursor.fetchall()}

    if "published_at" not in columns:
        await db.execute("ALTER TABLE publications ADD COLUMN published_at TEXT")
    if "cover_path" not in columns:
        await db.execute("ALTER TABLE publications ADD COLUMN cover_path TEXT")

async def init_db():
    """Инициализация базы данных"""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS publications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                url TEXT NOT NULL UNIQUE,
                source TEXT NOT NULL,
                full_text TEXT,
                status TEXT DEFAULT 'new',
                published_at TEXT,
                cover_path TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await _ensure_publication_columns(db)
        await db.commit()

async def save_publication(
    title: str,
    url: str,
    source: str,
    published_at: str | None = None,
    cover_path: str | None = None,
) -> Optional[int]:
    """Сохраняет новость и возвращает её ID. Возвращает None если уже существует."""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT id FROM publications WHERE url = ?",
            (url,)
        )
        row = await cursor.fetchone()

        if row:
            return None

        cursor = await db.execute(
            "INSERT INTO publications (title, url, source, published_at, cover_path) VALUES (?, ?, ?, ?, ?)",
            (title, url, source, published_at, cover_path)
        )
        await db.commit()
        return cursor.lastrowid

async def update_publication_cover_path(pub_id: int, cover_path: str):
    """Сохраняет путь к локальной обложке публикации."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE publications SET cover_path = ? WHERE id = ?",
            (cover_path, pub_id)
        )
        await db.commit()

async def get_publications_by_ids(ids: List[int]) -> List[Dict]:
    """Получает данные публикаций по списку ID"""
    if not ids:
        return []
    
    placeholders = ','.join('?' * len(ids))
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            f"SELECT id, title, url, full_text, status, published_at, cover_path FROM publications WHERE id IN ({placeholders})",
            ids
        )
        rows = await cursor.fetchall()
        return [
            {
                "id": r[0],
                "title": r[1],
                "url": r[2],
                "full_text": r[3],
                "status": r[4],
                "published_at": r[5],
                "cover_path": r[6],
            }
            for r in rows
        ]

async def update_publication_text(pub_id: int, text: str):
    """Обновляет текст и статус публикации"""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE publications SET full_text = ?, status = 'text_fetched' WHERE id = ?",
            (text, pub_id)
        )
        await db.commit()

async def check_url_exists(url: str) -> bool:
    """Проверяет, существует ли уже такая ссылка в БД"""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT id FROM publications WHERE url = ?", 
            (url,)
        )
        row = await cursor.fetchone()
        return row is not None
    
async def get_latest_publications(limit: int = 5, source: str = None) -> list[dict]:
    """Получает последние N публикаций из БД"""
    async with aiosqlite.connect(DB_PATH) as db:
        if source:
            cursor = await db.execute(
                "SELECT id, title, url, status, published_at FROM publications WHERE source = ? ORDER BY created_at DESC LIMIT ?",
                (source, limit)
            )
        else:
            cursor = await db.execute(
                "SELECT id, title, url, status, published_at FROM publications ORDER BY created_at DESC LIMIT ?",
                (limit,)
            )

        rows = await cursor.fetchall()
        return [
            {
                "id": r[0],
                "title": r[1],
                "url": r[2],
                "status": r[3],
                "published_at": r[4],
            }
            for r in rows
        ]

async def get_publications_by_sources(sources: List[str], limit: int = None) -> list[dict]:
    """Получает публикации из БД по нескольким источникам"""
    if not sources:
        return []

    placeholders = ",".join("?" * len(sources))
    query = (
        f"SELECT id, title, url, status, published_at, created_at FROM publications "
        f"WHERE source IN ({placeholders}) ORDER BY created_at DESC"
    )
    params = list(sources)

    if limit:
        query += " LIMIT ?"
        params.append(limit)

    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(query, params)
        rows = await cursor.fetchall()
        return [
            {
                "id": r[0],
                "title": r[1],
                "url": r[2],
                "status": r[3],
                "published_at": r[4],
                "created_at": r[5],
            }
            for r in rows
        ]

async def get_latest_publications_by_sources(sources: List[str], limit: int = 5) -> list[dict]:
    """Получает последние N публикаций из БД по списку источников"""
    return await get_publications_by_sources(sources, limit=limit)

async def get_publications_by_source(source: str, limit: int = None) -> list[dict]:
    """Получает все публикации из БД по источнику, отсортированные по дате (новые сверху)"""
    async with aiosqlite.connect(DB_PATH) as db:
        if limit:
            cursor = await db.execute(
                "SELECT id, title, url, status, published_at, created_at FROM publications WHERE source = ? ORDER BY created_at DESC LIMIT ?",
                (source, limit)
            )
        else:
            cursor = await db.execute(
                "SELECT id, title, url, status, published_at, created_at FROM publications WHERE source = ? ORDER BY created_at DESC",
                (source,)
            )

        rows = await cursor.fetchall()
        return [
            {
                "id": r[0],
                "title": r[1],
                "url": r[2],
                "status": r[3],
                "published_at": r[4],
                "created_at": r[5],
            }
            for r in rows
        ]