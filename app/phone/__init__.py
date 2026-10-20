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
    configured_phone_host,
    lan_addresses,
    lan_ip,
    lan_urls,
    lan_warning,
    normalize_phone_host,
    phone_base_url,
    phone_host_warning,
    phone_link_host,
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
    "configured_phone_host",
    "detect_firewall",
    "firewall_supported",
    "lan_addresses",
    "lan_ip",
    "lan_urls",
    "lan_warning",
    "normalize_phone_host",
    "phone_base_url",
    "phone_host_warning",
    "phone_link_host",
    "phone_url_for_phone",
    "remove_firewall",
]
