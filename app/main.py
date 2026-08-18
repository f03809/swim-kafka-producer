import asyncio
import logging
import queue
import signal
import sys
from typing import Any

from app.config import Settings
from app.health_server import HealthServer
from app.kafka_producer import KafkaProducer
from app.logging_config import configure_logging
from app.swim_consumer import SwimConsumer

logger = logging.getLogger(__name__)


def _setup_logging(settings: Settings) -> None:
    configure_logging(settings.log_level, settings.log_format)


def _load_subscriptions(settings: Settings) -> None:
    if not settings.swim_subscriptions:
        logger.error("No SWIM_SUBSCRIPTIONS configured; nothing to consume.")
        sys.exit(1)
    logger.info(
        "Loaded %s SWIM subscription(s): %s",
        len(settings.swim_subscriptions),
        [s.service for s in settings.swim_subscriptions],
    )


async def main() -> None:
    settings = Settings()
    _setup_logging(settings)
    _load_subscriptions(settings)

    health_server = HealthServer(
        port=settings.health_port,
        health_path=settings.health_path,
        metrics_path=settings.metrics_path,
    )
    health_server.start()

    incoming: queue.SimpleQueue = queue.SimpleQueue()
    consumer = SwimConsumer(settings, incoming)
    producer = KafkaProducer(settings, incoming)

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, lambda: asyncio.create_task(_shutdown(consumer, producer, health_server)))

    await producer.start()
    consumer.start()

    logger.info("SWIM to Kafka producer running")
    try:
        await asyncio.Event().wait()
    except asyncio.CancelledError:
        pass
    finally:
        await _shutdown(consumer, producer, health_server)


async def _shutdown(consumer: SwimConsumer, producer: KafkaProducer, health_server: HealthServer) -> None:
    logger.info("Shutting down...")
    await consumer.stop()
    await producer.stop()
    health_server.stop()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Interrupted")
