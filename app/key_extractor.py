import re
import uuid

from app.config import Settings

_airport_services = {"notam", "itws"}


def _first_match(payload: str, patterns: list[str]) -> str | None:
    for pattern in patterns:
        match = re.search(pattern, payload, re.IGNORECASE)
        if match:
            return match.group(1).strip().upper()
    return None


def extract_key(payload: str, service: str, settings: Settings) -> str:
    service_lower = service.lower()
    if service_lower in _airport_services:
        key = _first_match(payload, settings.swim_key_airport_patterns)
    else:
        key = _first_match(payload, settings.swim_key_flight_patterns)
        if key is None:
            key = _first_match(payload, settings.swim_key_airport_patterns)

    if key:
        return key
    return uuid.uuid4().hex
