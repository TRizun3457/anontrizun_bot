from aiogram import Router

from . import forward, inline, potato, profile, reply, report, settings, shop, start

router = Router()
router.include_routers(
    start.router,
    profile.router,
    settings.router,
    report.router,
    potato.router,
    shop.router,
    inline.router,
    reply.router,
    forward.router,
)
