from PIL import Image
from pathlib import Path
from io import BytesIO
from config import image_config

async def process_image(image_bytes: bytes) -> bytes:
    """Обрабатывает изображение: изменяет размер до точных width x height"""
    # Открываем изображение из байтов
    image = Image.open(BytesIO(image_bytes))
    
    # Получаем настройки из конфига
    target_width = image_config['image_processing']['width']
    target_height = image_config['image_processing']['height']
    quality = image_config['image_processing']['quality']
    
    # ИЗМЕНЯЕМ РАЗМЕР С РАСТЯГИВАНИЕМ/СЖАТИЕМ
    # resize() меняет размер до ТОЧНЫХ размеров, игнорируя пропорции
    image = image.resize((target_width, target_height), Image.Resampling.LANCZOS)
    
    # Конвертируем в RGB если нужно (для JPEG)
    if image.mode in ('RGBA', 'P'):
        image = image.convert('RGB')
    
    # Сохраняем в байты
    output = BytesIO()
    image.save(output, format='JPEG', quality=quality, optimize=True)
    output.seek(0)
    
    return output.getvalue()