import re

from app.config import Settings

_airport_services = {"notam", "itws"}

_msg_type_patterns = [
    r'"msgType"\s*:\s*"([^"]+)"',
    r"<msgType>([^<]+)</msgType>",
    r'"messageType"\s*:\s*"([^"]+)"',
    r"<messageType>([^<]+)</messageType>",
    r'"type"\s*:\s*"([^"]+)"',
    r"<type>([^<]+)</type>",
]

_itws_alert_patterns = [
    r'"product_msg_name"\s*:\s*"([^"]+)"',
    r"<product_msg_name>([^<]+)</product_msg_name>",
    r'"trnal_message"\s*:\s*"([^"]+)"',
    r"<trnal_message>([^<]+)</trnal_message>",
]

_itws_airport_patterns = [
    r'"product_header_airports"\s*:\s*"([^"]+)"',
    r'"airports"\s*[:=]\s*"([^"]+)"',
    r"<product_header_airports>([^<]+)</product_header_airports>",
    r"<airports>([^<]+)</airports>",
]


def _first_match(payload: str, patterns: list[str]) -> str | None:
    for pattern in patterns:
        match = re.search(pattern, payload, re.IGNORECASE)
        if match:
            return match.group(1).strip().upper()
    return None


def _split_values(value: str) -> list[str]:
    return [v.strip().upper() for v in re.split(r"[,;\s]+", value) if v.strip()]


def _all_locations(payload: str, patterns: list[str]) -> set[str]:
    found: set[str] = set()
    for pattern in patterns:
        for match in re.finditer(pattern, payload, re.IGNORECASE):
            for token in _split_values(match.group(1)):
                if token:
                    found.add(token)
    return found


def _derive_alert_type(raw: str) -> str:
    raw = raw.strip().upper()
    for suffix in (" ALERT PRODUCT", " ALERT", " PRODUCT"):
        if raw.endswith(suffix):
            raw = raw[: -len(suffix)].strip()
    return raw.split()[0] if raw.split() else "MULT"


def _itws_key(payload: str) -> str:
    alert_raw = _first_match(payload, _itws_alert_patterns)
    alert = _derive_alert_type(alert_raw) if alert_raw else "MULT"
    locs = _all_locations(payload, _itws_airport_patterns)
    if len(locs) > 1:
        airport = "MULT"
    elif len(locs) == 1:
        airport = next(iter(locs))
    else:
        airport = "MULT"
    return f"ITWS_{alert}_{airport}"


def extract_key(payload: str, service: str, settings: Settings) -> str:
    service_lower = service.lower()
    if service_lower == "itws":
        return _itws_key(payload)

    msg_type = _first_match(payload, _msg_type_patterns)

    if service_lower == "notam":
        locs = _all_locations(payload, settings.swim_key_airport_patterns)
    else:
        locs = _all_locations(payload, settings.swim_key_flight_patterns)
        if not locs:
            locs = _all_locations(payload, settings.swim_key_airport_patterns)

    if msg_type:
        locs.discard(msg_type)

    if len(locs) > 1:
        loc = "MULT"
    elif len(locs) == 1:
        loc = next(iter(locs))
    else:
        loc = "MULT"

    prefix = msg_type if msg_type else service.upper()
    return f"{prefix}_{loc}"
