from aiogram import Router

from . import forward, inline, profile, reply, settings, start

router = Router()
router.include_routers(
    start.router,
    profile.router,
    settings.router,
    inline.router,
    reply.router,
    forward.router,
)
