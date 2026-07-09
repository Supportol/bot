from pathlib import Path
import tempfile
from datetime import datetime

from aiogram import Router, types, F
from aiogram.filters import Command
from services.image_processor import process_image
from services.cover_storage import get_publication_cover_path, PROJECT_ROOT
from services.publication_id import parse_publication_ids
from database.db import get_publications_by_ids
from aiogram.types import FSInputFile

router = Router()

CURRENT_DATE_FMT = "%d.%m.%Y"
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}


async def process_publication_covers(publications: list[dict]) -> tuple[int, list[str]]:
    """
    Обрабатывает обложки публикаций и сохраняет в images/.../<ID>/res/*.jpg.
    Возвращает: (успешно обработано, список ошибок).
    """
    success_count = 0
    errors: list[str] = []

    for pub in publications:
        cover_path = None
        if pub.get("cover_path"):
            candidate = PROJECT_ROOT / pub["cover_path"]
            if candidate.exists():
                cover_path = candidate

        if cover_path is None:
            cover_path = get_publication_cover_path(pub["id"])

        if not cover_path or not cover_path.exists():
            errors.append(f"ID {pub['id']}: обложка не найдена")
            continue

        try:
            processed_bytes = await process_image(cover_path.read_bytes())
            source_dir = cover_path.parent
            res_dir = source_dir / "res"
            res_dir.mkdir(parents=True, exist_ok=True)
            output_path = res_dir / f"{cover_path.stem}.jpg"
            output_path.write_bytes(processed_bytes)
            success_count += 1
        except Exception as e:
            errors.append(f"ID {pub['id']}: {str(e)[:100]}")

    return success_count, errors

def _find_original_cover(pub_dir: Path) -> Path | None:
    """Ищет оригинал обложки в директории публикации (без res)."""
    if not pub_dir.exists() or not pub_dir.is_dir():
        return None
    for file_path in sorted(pub_dir.iterdir()):
        if not file_path.is_file():
            continue
        if file_path.suffix.lower() not in IMAGE_EXTENSIONS:
            continue
        return file_path
    return None

@router.message(Command("images"))
async def cmd_images_start(message: types.Message):
    """Обработчик команды /images"""
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        today_dir = PROJECT_ROOT / "images" / datetime.now().strftime(CURRENT_DATE_FMT)
        if not today_dir.exists():
            await message.answer(
                "⚠️ Не переданы ID, и в папке текущей даты нет изображений для автообработки.\n"
                "Пример: <code>/images IX_HON_1, IX_AC_2</code>",
                parse_mode="HTML",
            )
            return

        await message.answer("⏳ Запускаю автообработку обложек за текущую дату...")

        processed_count = 0
        skipped_count = 0
        errors: list[str] = []

        for pub_dir in sorted(today_dir.iterdir()):
            if not pub_dir.is_dir():
                continue
            if pub_dir.name == "res":
                continue

            res_dir = pub_dir / "res"
            if res_dir.exists():
                skipped_count += 1
                continue

            cover_path = _find_original_cover(pub_dir)
            if not cover_path:
                continue

            try:
                processed_bytes = await process_image(cover_path.read_bytes())
                res_dir.mkdir(parents=True, exist_ok=True)
                output_path = res_dir / f"{cover_path.stem}.jpg"
                output_path.write_bytes(processed_bytes)
                processed_count += 1
            except Exception as e:
                errors.append(f"{pub_dir.name}: {str(e)[:100]}")

        report = (
            "✅ Автообработка завершена.\n"
            f"📊 Обработано: {processed_count}\n"
            f"⏭ Пропущено (уже есть res): {skipped_count}"
        )
        if errors:
            report += "\n\n<b>Ошибки:</b>\n" + "\n".join(f"• {err}" for err in errors[:5])
            if len(errors) > 5:
                report += f"\n... и ещё {len(errors) - 5}"

        await message.answer(report, parse_mode="HTML")
        return

    ids = parse_publication_ids(args[1])

    if not ids:
        await message.answer("⚠️ Не найдено ни одного валидного ID.")
        return

    await message.answer(f"⏳ Обрабатываю обложки для {len(ids)} публикаций...")

    publications = await get_publications_by_ids(ids)
    found_ids = {pub["id"] for pub in publications}
    missing_ids = [pub_id for pub_id in ids if pub_id not in found_ids]

    success_count, errors = await process_publication_covers(publications)

    for pub in publications:
        cover_path = None
        if pub.get("cover_path"):
            candidate = PROJECT_ROOT / pub["cover_path"]
            if candidate.exists():
                cover_path = candidate
        if cover_path is None:
            cover_path = get_publication_cover_path(pub["id"])
        if not cover_path or not cover_path.exists():
            continue
        output_path = cover_path.parent / "res" / f"{cover_path.stem}.jpg"
        if output_path.exists():
            processed_photo = FSInputFile(output_path)
            caption = f"✅ ID {pub['id']}: {pub['title'][:120]}"
            await message.answer_photo(processed_photo, caption=caption)

    report = f"✅ Обработано изображений: {success_count}"
    if missing_ids:
        report += f"\n⚠️ ID не найдены в БД: {', '.join(missing_ids)}"
    if errors:
        report += "\n\n<b>Ошибки:</b>\n" + "\n".join(f"• {error}" for error in errors[:5])
        if len(errors) > 5:
            report += f"\n... и ещё {len(errors) - 5}"

    await message.answer(report, parse_mode="HTML")

@router.message(F.photo)
async def handle_photo(message: types.Message):
    """Обработчик получения фото"""
    photo = message.photo[-1]

    await message.answer("⏳ Обрабатываю изображение...")

    try:
        file = await message.bot.get_file(photo.file_id)
        file_bytes = await message.bot.download_file(file.file_path)
        image_bytes = file_bytes.read()

        processed_bytes = await process_image(image_bytes)

        with tempfile.NamedTemporaryFile(delete=False, suffix='.jpg') as temp_file:
            temp_file.write(processed_bytes)
            temp_path = temp_file.name

        processed_photo = FSInputFile(temp_path)
        await message.answer_photo(processed_photo, caption="✅ Обработанное изображение")

        Path(temp_path).unlink()

    except Exception as e:
        await message.answer(f"❌ Ошибка при обработке изображения: {str(e)}")

@router.message(F.document)
async def handle_document(message: types.Message):
    """Обработчик получения документа (изображения как файл)"""
    document = message.document

    if not document.mime_type.startswith('image/'):
        await message.answer("⚠️ Пожалуйста, отправьте изображение.")
        return

    await message.answer("⏳ Обрабатываю изображение...")

    try:
        file = await message.bot.get_file(document.file_id)
        file_bytes = await message.bot.download_file(file.file_path)
        image_bytes = file_bytes.read()

        processed_bytes = await process_image(image_bytes)

        with tempfile.NamedTemporaryFile(delete=False, suffix='.jpg') as temp_file:
            temp_file.write(processed_bytes)
            temp_path = temp_file.name

        processed_doc = FSInputFile(temp_path, filename=f"processed_{document.file_name}")
        await message.answer_document(processed_doc, caption="✅ Обработанное изображение")

        Path(temp_path).unlink()

    except Exception as e:
        await message.answer(f"❌ Ошибка при обработке изображения: {str(e)}")
