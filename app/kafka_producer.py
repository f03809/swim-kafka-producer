import asyncio
import logging
import queue
from contextlib import suppress
from datetime import UTC, datetime
from typing import Any

from aiokafka import AIOKafkaProducer
from aiokafka.errors import KafkaError
from prometheus_client import Counter, Histogram

from app.config import Settings
from app.key_extractor import extract_key

logger = logging.getLogger(__name__)

messages_produced = Counter(
    "swim_kafka_messages_produced_total",
    "Total SWIM messages produced to Kafka",
    ["service", "topic"],
)

produce_errors = Counter(
    "swim_kafka_produce_errors_total",
    "Total errors producing to Kafka",
    ["service", "topic"],
)

produce_latency = Histogram(
    "swim_kafka_produce_latency_seconds",
    "Kafka produce latency",
    ["service", "topic"],
)


class KafkaProducer:
    def __init__(self, settings: Settings, incoming: queue.SimpleQueue) -> None:
        self._settings = settings
        self._incoming = incoming
        self._producer: AIOKafkaProducer | None = None
        self._stop_event = asyncio.Event()
        self._task: asyncio.Task[Any] | None = None

    async def start(self) -> None:
        self._producer = AIOKafkaProducer(
            bootstrap_servers=self._settings.kafka_bootstrap_servers,
            client_id=self._settings.kafka_client_id,
            compression_type=self._settings.kafka_compression_type,
            acks=self._settings.kafka_acks,
            request_timeout_ms=self._settings.kafka_request_timeout_ms,
            value_serializer=lambda v: v,
            key_serializer=lambda k: k,
        )
        await self._producer.start()
        logger.info("Kafka producer started: %s", self._settings.kafka_bootstrap_servers)
        self._task = asyncio.create_task(self._drain(), name="kafka-drain")

    async def stop(self) -> None:
        self._stop_event.set()
        if self._task and not self._task.done():
            self._task.cancel()
            with suppress(asyncio.CancelledError):
                await self._task
        if self._producer:
            await self._producer.stop()
            logger.info("Kafka producer stopped")

    async def _drain(self) -> None:
        while not self._stop_event.is_set() or not self._incoming.empty():
            try:
                item = await asyncio.to_thread(
                    self._incoming.get, block=True, timeout=0.2
                )
            except queue.Empty:
                await asyncio.sleep(0.05)
                continue
            except Exception:
                await asyncio.sleep(0.05)
                continue

            await self._publish(item)

    async def _publish(self, item: dict[str, Any]) -> None:
        service = item["service"]
        topic = self._topic_for(service)
        key = extract_key(item["payload"], service, self._settings)
        value = item["payload"].encode("utf-8", errors="replace")
        key_bytes = key.encode("utf-8") if isinstance(key, str) else str(key).encode("utf-8")

        while not self._stop_event.is_set():
            try:
                start = datetime.now(UTC)
                headers = [
                    ("swim_service", service.encode()),
                    ("swim_queue", (item.get("queue") or "").encode()),
                    ("received_at", item["received_at"].isoformat().encode()),
                ]
                await self._producer.send(  # type: ignore[union-attr]
                    topic,
                    key=key_bytes,
                    value=value,
                    headers=headers,
                )
                produce_latency.labels(service=service, topic=topic).observe(
                    (datetime.now(UTC) - start).total_seconds()
                )
                messages_produced.labels(service=service, topic=topic).inc()
                return
            except KafkaError as exc:
                produce_errors.labels(service=service, topic=topic).inc()
                logger.error("Kafka send failed for %s/%s: %s; retrying in 5s", service, topic, exc)
                with suppress(asyncio.CancelledError):
                    await asyncio.wait_for(self._stop_event.wait(), timeout=5)
            except Exception:
                logger.exception("Unexpected error publishing %s/%s", service, topic)
                return

    def _topic_for(self, service: str) -> str:
        for sub in self._settings.swim_subscriptions:
            if sub.service == service:
                return sub.topic
        return f"faa-{service}-raw"
