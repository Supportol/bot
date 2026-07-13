from PIL import Image, ImageFilter
from pathlib import Path
from io import BytesIO
from config import image_config

PROJECT_ROOT = Path(__file__).parent.parent
WATERMARK_PATH = PROJECT_ROOT / "watermark.png"
WATERMARK_MARGIN = 20

async def process_image(image_bytes: bytes) -> bytes:
    """
    Обрабатывает изображение до точных размеров width x height.
    Использует технику "размытый фон" - фото вписывается с сохранением 
    пропорций, а пустые места заполняются размытой версией самой фотографии.
    """
    # Открываем изображение
    original = Image.open(BytesIO(image_bytes))
    
    # Получаем настройки
    target_width = image_config['image_processing']['width']
    target_height = image_config['image_processing']['height']
    quality = image_config['image_processing']['quality']
    
    # Конвертируем в RGB если нужно
    if original.mode in ('RGBA', 'P'):
        original = original.convert('RGB')
    
    # 1. Создаём размытый фон (растягиваем оригинал на весь размер и размываем)
    background = original.resize((target_width, target_height), Image.Resampling.LANCZOS)
    background = background.filter(ImageFilter.GaussianBlur(radius=20))
    
    # 2. Вписываем оригинальное фото с сохранением пропорций
    # thumbnail() сохраняет пропорции и вписывает в заданные размеры
    photo = original.copy()
    photo.thumbnail((target_width, target_height), Image.Resampling.LANCZOS)
    
    # 3. Вычисляем позицию по центру
    paste_x = (target_width - photo.width) // 2
    paste_y = (target_height - photo.height) // 2
    
    # 4. Накладываем фото на размытый фон
    background.paste(photo, (paste_x, paste_y))
    
    # 5. Добавляем watermark в правый нижний угол, если файл существует
    if WATERMARK_PATH.exists():
        watermark = Image.open(WATERMARK_PATH).convert("RGBA")
        canvas = background.convert("RGBA")

        # Пропорционально уменьшаем: не больше доли холста и не больше самого изображения
        max_w = max(1, target_width - WATERMARK_MARGIN * 2)
        max_h = max(1, target_height - WATERMARK_MARGIN * 2)
        max_wm_w = max(
            1,
            int(target_width * image_config["image_processing"].get("watermark_max_width_ratio", 0.22)),
        )
        max_wm_h = max(
            1,
            int(target_height * image_config["image_processing"].get("watermark_max_width_ratio", 0.22)),
        )
        wm_scale = min(
            max_w / watermark.width,
            max_h / watermark.height,
            max_wm_w / watermark.width,
            max_wm_h / watermark.height,
            1.0,
        )
        if wm_scale < 1.0:
            watermark = watermark.resize(
                (int(watermark.width * wm_scale), int(watermark.height * wm_scale)),
                Image.Resampling.LANCZOS,
            )

        wm_x = target_width - watermark.width - WATERMARK_MARGIN
        wm_y = target_height - watermark.height - WATERMARK_MARGIN
        canvas.alpha_composite(watermark, (wm_x, wm_y))
        background = canvas.convert("RGB")

    # 6. Сохраняем в байты
    output = BytesIO()
    background.save(output, format='JPEG', quality=quality, optimize=True)
    output.seek(0)
    
    return output.getvalue()