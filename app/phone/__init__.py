"""Local-network phone attendance (small HTTP check-in service)."""

from app.phone.firewall import (
    AllowResult,
    Firewall,
    allow as allow_firewall,
    detect as detect_firewall,
    remove as remove_firewall,
    supported_platform as firewall_supported,
)
from app.phone.server import (
    CHECKIN_PATH_PREFIX,
    DEFAULT_PORT,
    PhoneAddressError,
    PhoneServer,
    lan_addresses,
    lan_ip,
    lan_warning,
    phone_base_url,
    phone_url_for_phone,
)

__all__ = [
    "CHECKIN_PATH_PREFIX",
    "DEFAULT_PORT",
    "AllowResult",
    "Firewall",
    "PhoneAddressError",
    "PhoneServer",
    "allow_firewall",
    "detect_firewall",
    "firewall_supported",
    "lan_addresses",
    "lan_ip",
    "lan_warning",
    "phone_base_url",
    "phone_url_for_phone",
    "remove_firewall",
]
