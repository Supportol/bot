from .news import router as news_router
from .processing import router as processing_router
from .images import router as images_router
from .text import router as text_router
from .ixbt import router as ixbt_router
from .drom import router as drom_router
from .motor import router as motor_router
from .list import router as list_router
from .rewrite import router as rewrite_router

__all__ = [
    'news_router', 
    'processing_router', 
    'images_router', 
    'text_router', 
    'ixbt_router',
    'drom_router',
    'motor_router',
    'list_router',
    'rewrite_router'
]