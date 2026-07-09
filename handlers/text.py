import shutil
from datetime import datetime
from pathlib import Path

from aiogram import Router, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from database.db import get_publications_by_ids, update_publication_text
from services.publication_id import parse_publication_ids
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
    await message.answer(f"⏳ Подготавливаю материалы для {len(ids)} публикаций...")

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

            processed_image = _find_processed_image(pub)
            if not processed_image:
                errors.append(f"{pub['id']}: не найдено обработанное изображение (res/*.jpg)")
                continue

            target_dir = NEWS_DIR / date_dir / pub["id"]
            target_dir.mkdir(parents=True, exist_ok=True)

            target_image = target_dir / processed_image.name
            shutil.copy2(processed_image, target_image)

            md_path = target_dir / "source.md"
            md_path.write_text(_build_markdown(pub, source_text), encoding="utf-8")
            success_count += 1
        except Exception as e:
            errors.append(f"{pub['id']}: {str(e)[:120]}")

    report = (
        "✅ Команда /text завершена.\n"
        f"📁 Папка: <code>news/{date_dir}</code>\n"
        f"📊 Успешно: {success_count}"
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