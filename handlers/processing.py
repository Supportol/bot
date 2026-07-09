from aiogram import Router, types
from aiogram.filters import Command
from database.db import get_publications_by_ids, update_publication_text
from services.text_extractor import extract_text_from_url
from services.publication_id import parse_publication_ids

router = Router()

@router.message(Command("processing"))
async def cmd_processing(message: types.Message):
    """Обработчик команды /processing"""
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.answer(
            "⚠️ Укажите ID через запятую. Пример: <code>/processing IX_HON_1, IX_AC_2</code>",
            parse_mode="HTML",
        )
        return

    ids = parse_publication_ids(args[1])

    if not ids:
        await message.answer("⚠️ Не найдено ни одного валидного ID.")
        return

    await message.answer(f"⏳ Начинаю обработку {len(ids)} публикаций...")

    publications = await get_publications_by_ids(ids)
    found_ids = {pub["id"] for pub in publications}
    missing_ids = [pub_id for pub_id in ids if pub_id not in found_ids]

    success_count = 0
    errors = []

    for pub in publications:
        try:
            text = await extract_text_from_url(pub["url"])
            await update_publication_text(pub["id"], text)
            success_count += 1
        except Exception as e:
            errors.append(f"ID {pub['id']}: {str(e)[:100]}")

    report = "✅ Обработка завершена!\n\n"
    report += f"📊 Успешно обработано: {success_count}\n"
    report += f"❌ Ошибок: {len(errors)}"

    if missing_ids:
        report += f"\n\n⚠️ ID не найдены в БД: {', '.join(missing_ids)}"

    if errors:
        report += "\n\n<b>Детали ошибок:</b>\n"
        for error in errors[:5]:
            report += f"• {error}\n"
        if len(errors) > 5:
            report += f"\n... и ещё {len(errors) - 5} ошибок"

    await message.answer(report, parse_mode="HTML")
