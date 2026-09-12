from aiogram import Router

from tutor_bot.handlers import admin, learn, start, student, subscription


def setup_routers() -> Router:
    root = Router()
    root.include_router(start.router)
    root.include_router(subscription.router)
    root.include_router(student.router)
    root.include_router(admin.router)
    root.include_router(learn.router)
    return root
