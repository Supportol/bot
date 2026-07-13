import html
import re
import shutil
from datetime import datetime
from pathlib import Path

from aiogram import Router, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from database.db import get_publications_by_ids, update_publication_text
from services.publication_id import parse_publication_ids
from services.rewrite_service import RewriteError, rewrite_text_via_text_ru
from services.text_extractor import extract_text_from_url

router = Router()
PROJECT_ROOT = Path(__file__).parent.parent
NEWS_DIR = PROJECT_ROOT / "news"
IMAGES_DIR = PROJECT_ROOT / "images"
DATE_FMT = "%d.%m.%Y"

class TextStates(StatesGroup):
    waiting_ids = State()

def _build_markdown(pub: dict, text: str) -> str:
    title = (pub.get("title") or "Без заголовка").strip()
    url = (pub.get("url") or "").strip()
    return f"# {title}\n\nИсточник: {url}\n\n---\n\n{text.strip()}\n"


def _extract_source_title(source_md: str) -> str:
    for line in (source_md or "").splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return ""


def _prepend_title_to_text(title: str, text: str) -> str:
    """Добавляет заголовок из source.md перед основным текстом для единого рерайта."""
    title = (title or "").strip()
    body = (text or "").strip()
    if not title:
        return body
    if not body:
        return title
    return f"{title}\n\n{body}"


def _extract_rewritten_title_and_body(rewritten: str) -> tuple[str, str]:
    """Извлекает переписанный заголовок из начала текста и возвращает (заголовок, тело)."""
    text = (rewritten or "").strip()
    if not text:
        return "", ""

    match = re.match(r"^(.+?[.!?])(\s+(.*))?$", text, re.DOTALL)
    if match:
        body = (match.group(3) or "").strip()
        if body:
            return match.group(1).strip(), body

    parts = [part.strip() for part in text.split("\n\n") if part.strip()]
    if len(parts) >= 2:
        return parts[0], "\n\n".join(parts[1:])

    if match:
        return match.group(1).strip(), ""

    return text, ""


def _build_news_md(rewritten_text: str, image_filename: str, title: str) -> str:
    text = (rewritten_text or "").strip()
    if not text:
        return ""

    title = (title or "").strip()
    title_escaped = html.escape(title, quote=True)
    image_tag = (
        f'<p><img src="/_upload/content/news/{image_filename}" '
        f'alt="{title_escaped}" /></p>'
    )
    paragraphs = [chunk.strip() for chunk in text.split("\n\n") if chunk.strip()]
    body = "\n".join(f"<p>{paragraph}</p>" for paragraph in paragraphs)

    return (
        f"1. Заголовок: {title}\n"
        f"2. Картинка: {image_tag}\n\n"
        f"{body}\n"
    )

def _find_processed_image(pub: dict) -> Path | None:
    """Ищет обработанное изображение в images/.../<id>/res/*.jpg."""
    candidates = []
    if pub.get("cover_path"):
        original = PROJECT_ROOT / pub["cover_path"]
        candidates.append(original.parent / "res")

    candidates.extend(sorted(IMAGES_DIR.glob(f"*/{pub['id']}/res"), reverse=True))

    for res_dir in candidates:
        if not res_dir.exists():
            continue
        files = sorted(res_dir.glob("*.jpg"))
        if files:
            return files[0]
    return None

async def _process_ids(message: types.Message, ids: list[str], state: FSMContext):
    await message.answer(f"⏳ Подготавливаю материалы и рерайт для {len(ids)} публикаций...")

    publications = await get_publications_by_ids(ids)
    found_ids = {pub["id"] for pub in publications}
    missing_ids = [pub_id for pub_id in ids if pub_id not in found_ids]

    date_dir = datetime.now().strftime(DATE_FMT)
    success_count = 0
    errors = []

    for pub in publications:
        try:
            source_text = await extract_text_from_url(pub["url"])
            await update_publication_text(pub["id"], source_text)

            source_md = _build_markdown(pub, source_text)
            source_title = _extract_source_title(source_md)
            if not source_title:
                raise RewriteError("Не удалось извлечь заголовок из source.md")

            text_for_rewrite = _prepend_title_to_text(source_title, source_text)
            rewritten_combined = await rewrite_text_via_text_ru(text_for_rewrite, creative=5)
            rewritten_title, rewritten_text = _extract_rewritten_title_and_body(rewritten_combined)
            if not rewritten_title:
                raise RewriteError("Не удалось извлечь заголовок из результата рерайта")

            processed_image = _find_processed_image(pub)
            if not processed_image:
                errors.append(f"{pub['id']}: не найдено обработанное изображение (res/*.jpg)")
                continue

            target_dir = NEWS_DIR / date_dir / pub["id"]
            target_dir.mkdir(parents=True, exist_ok=True)

            target_image = target_dir / processed_image.name
            shutil.copy2(processed_image, target_image)

            md_path = target_dir / "source.md"
            md_path.write_text(source_md, encoding="utf-8")

            news_md_path = target_dir / "news.md"
            news_md_path.write_text(
                _build_news_md(rewritten_text, processed_image.name, rewritten_title),
                encoding="utf-8",
            )
            success_count += 1
        except RewriteError as e:
            errors.append(f"{pub['id']}: ошибка рерайта: {str(e)[:120]}")
        except Exception as e:
            errors.append(f"{pub['id']}: {str(e)[:120]}")

    report = (
        "✅ Команда /text завершена.\n"
        f"📁 Папка: <code>news/{date_dir}</code>\n"
        f"📊 Успешно: {success_count}\n"
        "📝 Файлы: <code>source.md</code> + <code>news.md</code>"
    )
    if missing_ids:
        report += f"\n⚠️ ID не найдены в БД: {', '.join(missing_ids)}"
    if errors:
        report += "\n\n<b>Ошибки:</b>\n" + "\n".join(f"• {err}" for err in errors[:8])
        if len(errors) > 8:
            report += f"\n... и ещё {len(errors) - 8}"

    await message.answer(report, parse_mode="HTML")
    await state.clear()

@router.message(Command("text"))
async def cmd_text(message: types.Message, state: FSMContext):
    """Обработчик команды /text: формирует пакет news/DATE/ID."""
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await state.set_state(TextStates.waiting_ids)
        await message.answer(
            "📝 Укажите ID новости (один или через запятую).\n"
            "Пример: <code>/text IX_HON_1, MT_HON_3</code>\n"
            "Можно отправить ID следующим сообщением.",
            parse_mode="HTML",
        )
        return

    ids = parse_publication_ids(args[1])
    if not ids:
        await message.answer("⚠️ Не найдено ни одного валидного ID.")
        return

    await _process_ids(message, ids, state)

@router.message(TextStates.waiting_ids)
async def cmd_text_waiting_ids(message: types.Message, state: FSMContext):
    ids = parse_publication_ids(message.text or "")
    if not ids:
        await message.answer("⚠️ Не удалось распознать ID. Пример: <code>IX_HON_1, MT_HON_3</code>", parse_mode="HTML")
        return
    await _process_ids(message, ids, state)