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
DATE_FMT = "%d.%m.%Y"


class RewriteStates(StatesGroup):
    waiting_ids = State()


def _build_news_md(rewritten_text: str) -> str:
    text = (rewritten_text or "").strip()
    if not text:
        return ""

    paragraphs = [chunk.strip() for chunk in text.split("\n\n") if chunk.strip()]
    return "\n".join(f"<p>{paragraph}</p>" for paragraph in paragraphs) + "\n"


def _find_news_dir_for_pub(pub_id: str) -> Path:
    candidates = sorted(NEWS_DIR.glob(f"*/{pub_id}"), reverse=True)
    if candidates:
        return candidates[0]
    date_dir = datetime.now().strftime(DATE_FMT)
    return NEWS_DIR / date_dir / pub_id


async def _get_source_text(pub: dict) -> str:
    current = (pub.get("full_text") or "").strip()
    if current:
        return current
    extracted = await extract_text_from_url(pub["url"])
    await update_publication_text(pub["id"], extracted)
    return extracted


async def _process_ids(message: types.Message, ids: list[str], state: FSMContext):
    await message.answer(f"⏳ Запускаю рерайт для {len(ids)} публикаций...")

    publications = await get_publications_by_ids(ids)
    found_ids = {pub["id"] for pub in publications}
    missing_ids = [pub_id for pub_id in ids if pub_id not in found_ids]

    success_count = 0
    errors: list[str] = []

    for pub in publications:
        try:
            source_text = await _get_source_text(pub)
            rewritten = await rewrite_text_via_text_ru(source_text, creative=5)

            target_dir = _find_news_dir_for_pub(pub["id"])
            target_dir.mkdir(parents=True, exist_ok=True)
            news_md = target_dir / "news.md"
            news_md.write_text(_build_news_md(rewritten), encoding="utf-8")
            success_count += 1
        except RewriteError as e:
            errors.append(f"{pub['id']}: {str(e)[:140]}")
        except Exception as e:
            errors.append(f"{pub['id']}: {str(e)[:140]}")

    report = (
        "✅ Команда /rewrite завершена.\n"
        f"📊 Успешно: {success_count}\n"
        "📝 Файл: <code>news/ДД.ММ.ГГГГ/&lt;ID&gt;/news.md</code>"
    )
    if missing_ids:
        report += f"\n⚠️ ID не найдены в БД: {', '.join(missing_ids)}"
    if errors:
        report += "\n\n<b>Ошибки:</b>\n" + "\n".join(f"• {err}" for err in errors[:8])
        if len(errors) > 8:
            report += f"\n... и ещё {len(errors) - 8}"

    await message.answer(report, parse_mode="HTML")
    await state.clear()


@router.message(Command("rewrite"))
async def cmd_rewrite(message: types.Message, state: FSMContext):
    args = (message.text or "").split(maxsplit=1)
    if len(args) < 2:
        await state.set_state(RewriteStates.waiting_ids)
        await message.answer(
            "✍️ Укажите ID новости для рерайта (один или через запятую).\n"
            "Пример: <code>/rewrite IX_HON_1, DR_HON_1</code>\n"
            "Можно отправить ID следующим сообщением.",
            parse_mode="HTML",
        )
        return

    ids = parse_publication_ids(args[1])
    if not ids:
        await message.answer("⚠️ Не найдено ни одного валидного ID.")
        return
    await _process_ids(message, ids, state)


@router.message(RewriteStates.waiting_ids)
async def cmd_rewrite_waiting_ids(message: types.Message, state: FSMContext):
    ids = parse_publication_ids(message.text or "")
    if not ids:
        await message.answer("⚠️ Не удалось распознать ID. Пример: <code>IX_HON_1, MT_HON_3</code>", parse_mode="HTML")
        return
    await _process_ids(message, ids, state)
