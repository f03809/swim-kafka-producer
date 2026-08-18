import json
from typing import Any

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class SwimSubscription(BaseSettings):
    model_config = SettingsConfigDict(extra="allow")

    service: str
    enabled: bool = True
    host: str = "tcps://ems1.swim.faa.gov:55443"
    vpn: str
    queue: str
    client_name: str | None = None
    topic: str | None = None

    @field_validator("topic", mode="before")
    @classmethod
    def default_topic(cls, v: Any, info: Any) -> str:
        if v:
            return str(v)
        service = info.data.get("service", "unknown")
        return f"faa-{service}-raw"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    log_level: str = "INFO"
    log_format: str = "json"  # "json" or "text"

    kafka_bootstrap_servers: str = "10.0.0.94:9092"
    kafka_client_id: str = "swim-producer"
    kafka_request_timeout_ms: int = 30000
    kafka_compression_type: str | None = None
    kafka_acks: int | str = 1

    swim_username: str
    swim_password: str
    swim_subscriptions: list[SwimSubscription] = Field(default_factory=list)

    swim_key_flight_patterns: list[str] = Field(
        default_factory=lambda: [
            r'"aid"\s*:\s*"([^"]+)"',
            r'"-aircraftIdentification"\s*:\s*"([^"]+)"',
            r'"aircraftIdentification"\s*[:=]\s*"([^"]+)"',
            r'"acid"\s*[:=]\s*"([^"]+)"',
            r'"callsign"\s*[:=]\s*"([^"]+)"',
            r'"flightRef"\s*[:=]\s*"([^"]+)"',
            r'"gufi"\s*[:=]\s*"([^"]+)"',
            r'\baid\s*=\s*"([^"]+)"',
            r'<aid>([^<]+)</aid>',
            r'<acid>([^<]+)</acid>',
            r'<callSign>([^<]+)</callSign>',
            r'<aircraftIdentification[^>]*>([^<]+)</aircraftIdentification>',
            r'\baircraftIdentification\s*=\s*"([^"]+)"',
            r'<flightRef[^>]*>([^<]+)</flightRef>',
            r'<gufi>([^<]+)</gufi>',
        ]
    )
    swim_key_airport_patterns: list[str] = Field(
        default_factory=lambda: [
            r'"apt"\s*[:=]\s*"([^"]+)"',
            r'"airportId"\s*[:=]\s*"([^"]+)"',
            r'"airport"\s*[:=]\s*"([^"]+)"',
            r'"location"\s*[:=]\s*"([^"]+)"',
            r'<apt>([^<]+)</apt>',
            r'<airportId>([^<]+)</airportId>',
            r'<airport>([^<]+)</airport>',
            r'<locationIdentifier[^>]*>([^<]+)</locationIdentifier>',
        ]
    )

    health_port: int = 8080
    health_path: str = "/health"
    metrics_path: str = "/metrics"

    @field_validator("swim_subscriptions", mode="before")
    @classmethod
    def parse_subscriptions(cls, v: Any) -> list[SwimSubscription]:
        if isinstance(v, str):
            data = json.loads(v)
        else:
            data = v
        if not data:
            return []
        if isinstance(data, str):
            data = json.loads(data)
        return [SwimSubscription.model_validate(sub) if isinstance(sub, dict) else sub for sub in data]
