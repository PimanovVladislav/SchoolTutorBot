from aiogram import Router

from tutor_bot.handlers import learn, menu, start, subscription


def setup_routers() -> Router:
    root = Router()
    root.include_router(start.router)
    root.include_router(subscription.router)
    root.include_router(menu.router)
    root.include_router(learn.router)
    return root
