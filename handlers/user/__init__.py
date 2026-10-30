from aiogram import Router

from . import forward, inline, potato, profile, reply, settings, start

router = Router()
router.include_routers(
    start.router,
    profile.router,
    settings.router,
    potato.router,
    inline.router,
    reply.router,
    forward.router,
)
