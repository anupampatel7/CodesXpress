"""Handlers router aggregation."""

from aiogram import Router
from handlers.start import router as start_router
from handlers.channels import router as channels_router
from handlers.device import router as device_router
from handlers.menu import router as menu_router
from handlers.coupons import router as coupons_router
from handlers.referrals import router as referrals_router
from handlers.profile import router as profile_router
from handlers.support import router as support_router
from handlers.admin import router as admin_router


def setup_routers() -> Router:
    """Aggregate all modular routers in priority order."""
    root_router = Router(name="root_router")

    # Include routers
    root_router.include_router(admin_router)
    root_router.include_router(support_router)
    root_router.include_router(start_router)
    root_router.include_router(device_router)
    root_router.include_router(channels_router)
    root_router.include_router(coupons_router)
    root_router.include_router(referrals_router)
    root_router.include_router(profile_router)
    root_router.include_router(menu_router)

    return root_router
