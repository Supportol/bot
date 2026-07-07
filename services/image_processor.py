from PIL import Image, ImageFilter
from pathlib import Path
from io import BytesIO
from config import image_config

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
    
    # 5. Сохраняем в байты
    output = BytesIO()
    background.save(output, format='JPEG', quality=quality, optimize=True)
    output.seek(0)
    
    return output.getvalue()