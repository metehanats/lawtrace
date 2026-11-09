"""HTTP katmanında ortak yardımcılar."""

import ipaddress

from fastapi import Request


def istemci_ip(request: Request) -> str | None:
    """Denetim kaydı için istemci adresi; geçerli bir IP değilse kaydedilmez."""
    host = request.client.host if request.client else None
    try:
        return str(ipaddress.ip_address(host)) if host else None
    except ValueError:
        return None
