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

_primary_aircraft_patterns = [
    r'"aid"\s*:\s*"([^"]+)"',
    r'"-aircraftIdentification"\s*:\s*"([^"]+)"',
    r'"aircraftIdentification"\s*[:=]\s*"([^"]+)"',
    r'"acid"\s*[:=]\s*"([^"]+)"',
    r'"callsign"\s*[:=]\s*"([^"]+)"',
    r'\baid\s*=\s*"([^"]+)"',
    r"<aid>([^<]+)</aid>",
    r"<acid>([^<]+)</acid>",
    r"<callSign>([^<]+)</callSign>",
    r"<aircraftIdentification[^>]*>([^<]+)</aircraftIdentification>",
    r'\baircraftIdentification\s*=\s*"([^"]+)"',
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
    airport = _one_or_mult(locs)
    return f"ITWS_{alert}_{airport}"


def _one_or_mult(locs: set[str]) -> str:
    if len(locs) > 1:
        return "MULT"
    if len(locs) == 1:
        return next(iter(locs))
    return "MULT"


def _primary_location(payload: str, patterns: list[str]) -> str | None:
    for pattern in patterns:
        locs = _all_locations(payload, [pattern])
        if len(locs) == 1:
            return next(iter(locs))
        if len(locs) > 1:
            return "MULT"
    return None


def extract_key(payload: str, service: str, settings: Settings) -> str:
    service_lower = service.lower()
    if service_lower == "itws":
        return _itws_key(payload)

    msg_type = _first_match(payload, _msg_type_patterns)

    if service_lower == "notam":
        locs = _all_locations(payload, settings.swim_key_airport_patterns)
        if msg_type:
            locs.discard(msg_type)
        loc = _one_or_mult(locs)
    else:
        loc = _primary_location(payload, _primary_aircraft_patterns)
        if loc is None:
            locs = _all_locations(payload, settings.swim_key_flight_patterns)
            if msg_type:
                locs.discard(msg_type)
            loc = _one_or_mult(locs)
            if loc == "MULT" and not locs:
                # no flight identifier found; try airports as a last resort
                locs = _all_locations(payload, settings.swim_key_airport_patterns)
                if msg_type:
                    locs.discard(msg_type)
                loc = _one_or_mult(locs)

    prefix = msg_type if msg_type else service.upper()
    return f"{prefix}_{loc}"
