import aiosqlite
from pathlib import Path
from typing import List, Dict, Optional

DB_PATH = Path(__file__).parent.parent / "bot_database.db"

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
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.commit()

async def save_publication(title: str, url: str, source: str) -> Optional[int]:
    """Сохраняет новость и возвращает её ID. Возвращает None если уже существует."""
    async with aiosqlite.connect(DB_PATH) as db:
        # Сначала проверяем, существует ли уже такая ссылка
        cursor = await db.execute(
            "SELECT id FROM publications WHERE url = ?", 
            (url,)
        )
        row = await cursor.fetchone()
        
        if row:
            # Уже есть в БД
            return None
        
        # Сохраняем новую запись
        cursor = await db.execute(
            "INSERT INTO publications (title, url, source) VALUES (?, ?, ?)",
            (title, url, source)
        )
        await db.commit()
        return cursor.lastrowid

async def get_publications_by_ids(ids: List[int]) -> List[Dict]:
    """Получает данные публикаций по списку ID"""
    if not ids:
        return []
    
    placeholders = ','.join('?' * len(ids))
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            f"SELECT id, title, url, full_text, status FROM publications WHERE id IN ({placeholders})", 
            ids
        )
        rows = await cursor.fetchall()
        return [
            {
                "id": r[0], 
                "title": r[1], 
                "url": r[2], 
                "full_text": r[3],
                "status": r[4]
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
                "SELECT id, title, url, status FROM publications WHERE source = ? ORDER BY created_at DESC LIMIT ?",
                (source, limit)
            )
        else:
            cursor = await db.execute(
                "SELECT id, title, url, status FROM publications ORDER BY created_at DESC LIMIT ?",
                (limit,)
            )
        
        rows = await cursor.fetchall()
        return [
            {
                "id": r[0],
                "title": r[1],
                "url": r[2],
                "status": r[3]
            }
            for r in rows
        ]