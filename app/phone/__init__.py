"""Local-network phone attendance (small HTTP check-in service)."""

from app.phone.server import (
    CHECKIN_PATH_PREFIX,
    DEFAULT_PORT,
    PhoneAddressError,
    PhoneServer,
    lan_ip,
    phone_base_url,
    phone_url_for_phone,
)

__all__ = [
    "CHECKIN_PATH_PREFIX",
    "DEFAULT_PORT",
    "PhoneAddressError",
    "PhoneServer",
    "lan_ip",
    "phone_base_url",
    "phone_url_for_phone",
]
