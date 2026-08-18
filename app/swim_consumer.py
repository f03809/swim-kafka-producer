import asyncio
import json
import logging
import queue
import re
import threading
import uuid
from contextlib import suppress
from datetime import UTC, datetime
from typing import Any

import xmltodict

from solace.messaging.config.solace_properties import (
    authentication_properties,
    client_properties,
    service_properties,
    transport_layer_properties,
    transport_layer_security_properties,
)
from solace.messaging.messaging_service import MessagingService
from solace.messaging.receiver.inbound_message import InboundMessage
from solace.messaging.receiver.message_receiver import MessageHandler
from solace.messaging.resources.queue import Queue

logger = logging.getLogger(__name__)

STATUS: dict[str, dict] = {}
_status_lock = threading.Lock()


def _set_state(
    service_key: str,
    state: str,
    error: str | None = None,
    received_at: datetime | None = None,
) -> None:
    now = datetime.now(UTC)
    with _status_lock:
        entry = STATUS.setdefault(service_key, {})
        entry["state"] = state
        if received_at is not None:
            entry["last_received_at"] = received_at
        if error is not None:
            entry["last_error"] = error
            entry["last_error_at"] = now


def _xml_to_json(payload: str) -> str:
    stripped = payload.strip()
    if not (stripped.startswith("<") and (stripped.startswith("<?xml") or "<" in stripped[:50])):
        return payload
    try:
        parsed = xmltodict.parse(
            payload,
            attr_prefix="",
            cdata_key="#content",
        )
        return json.dumps(parsed, ensure_ascii=False, separators=(",", ":"))
    except Exception:
        logger.warning("Failed to convert XML payload to JSON, passing through as string")
        return payload


def _is_heartbeat(payload: str) -> bool:
    try:
        parsed = json.loads(payload)
        return isinstance(parsed, dict) and isinstance(parsed.get("mis"), dict) and "hb" in parsed["mis"]
    except Exception:
        return False


class _SolaceWarningHandler(logging.Handler):
    _app_id_pattern = re.compile(r"APP ID: tracker-([a-z0-9]+)-")

    def __init__(self) -> None:
        super().__init__(level=logging.WARNING)

    def emit(self, record: logging.LogRecord) -> None:
        if not record or not record.getMessage():
            return
        msg = record.getMessage()
        if "SSL" not in msg and "COMMUNICATION_ERROR" not in msg:
            return
        match = self._app_id_pattern.search(msg)
        if not match:
            return
        service_key = match.group(1)
        _set_state(service_key, "error", error=msg[:200])


_solace_log_handler = _SolaceWarningHandler()
logging.getLogger("solace.messaging").addHandler(_solace_log_handler)
logging.getLogger("solace.messaging.core").addHandler(_solace_log_handler)
logging.getLogger("solace.messaging.connections").addHandler(_solace_log_handler)


class _SwimMessageHandler(MessageHandler):
    def __init__(
        self,
        incoming: queue.SimpleQueue,
        service: str,
        queue_name: str,
        client_name: str,
    ):
        self._incoming = incoming
        self._service = service
        self._queue_name = queue_name
        self._client_name = client_name

    def on_message(self, message: InboundMessage) -> None:
        payload = message.get_payload_as_string()
        if payload is None:
            raw = message.get_payload_as_bytes()
            payload = (
                raw.decode("utf-8", errors="replace")
                if raw is not None
                else ""
            )
        payload = _xml_to_json(payload)
        if not payload.strip():
            _set_state(self._service, "connected", received_at=datetime.now(UTC))
            return
        if _is_heartbeat(payload):
            _set_state(self._service, "connected", received_at=datetime.now(UTC))
            return
        received_at = datetime.now(UTC)
        _set_state(self._service, "connected", received_at=received_at)
        self._incoming.put({
            "service": self._service,
            "queue": self._queue_name,
            "client_name": self._client_name,
            "payload": payload,
            "received_at": received_at,
        })


class SwimConsumer:
    def __init__(self, settings: Any, incoming: queue.SimpleQueue) -> None:
        self._settings = settings
        self._incoming = incoming
        self._stop_event = asyncio.Event()
        self._task: asyncio.Task[Any] | None = None

    def start(self) -> None:
        self._task = asyncio.create_task(self._run(), name="swim-consumer")

    async def stop(self) -> None:
        self._stop_event.set()
        if self._task and not self._task.done():
            self._task.cancel()
            with suppress(asyncio.CancelledError):
                await self._task

    async def _run(self) -> None:
        active = [sub for sub in self._settings.swim_subscriptions if sub.enabled]
        if not active:
            logger.warning("No SWIM subscriptions enabled; consumer idle")
            return

        consumer_tasks = [
            asyncio.create_task(self._consume_one(sub))
            for sub in active
        ]
        try:
            await asyncio.gather(*consumer_tasks, return_exceptions=True)
        except Exception:
            logger.exception("SWIM consumer runner failed")

    async def _consume_one(self, sub: Any) -> None:
        service_key = sub.service
        client_name = sub.client_name or f"swim-producer-{service_key}-{uuid.uuid4().hex[:8]}"

        props = {
            transport_layer_properties.HOST: sub.host,
            service_properties.VPN_NAME: sub.vpn,
            authentication_properties.SCHEME_BASIC_USER_NAME: self._settings.swim_username,
            authentication_properties.SCHEME_BASIC_PASSWORD: self._settings.swim_password,
            client_properties.NAME: client_name,
            transport_layer_security_properties.CERT_VALIDATED: False,
        }

        while not self._stop_event.is_set():
            _set_state(service_key, "connecting")
            service = None
            receiver = None
            try:
                service = await asyncio.to_thread(
                    lambda: MessagingService.builder().from_properties(props).build()
                )
                await asyncio.to_thread(service.connect)
                queue_obj = await asyncio.to_thread(
                    lambda: Queue.durable_exclusive_queue(sub.queue)
                )
                receiver = await asyncio.to_thread(
                    lambda s=service, q=queue_obj: s.create_persistent_message_receiver_builder()
                    .with_message_auto_acknowledgement()
                    .build(q)
                )
                await asyncio.to_thread(receiver.start)
                handler = _SwimMessageHandler(
                    self._incoming,
                    service_key,
                    sub.queue,
                    client_name,
                )
                await asyncio.to_thread(receiver.receive_async, handler)
                logger.info("SWIM receiver started for %s", service_key)
                _set_state(service_key, "connected")

                while not self._stop_event.is_set():
                    await asyncio.sleep(1)
            except Exception as exc:
                _set_state(service_key, "error", error=str(exc))
                logger.exception("SWIM consumer error for %s", service_key)
            finally:
                if receiver:
                    with suppress(Exception):
                        await asyncio.to_thread(receiver.terminate)
                if service:
                    with suppress(Exception):
                        await asyncio.to_thread(service.disconnect)

            if not self._stop_event.is_set():
                logger.info("SWIM consumer for %s will retry in 30s", service_key)
                with suppress(asyncio.CancelledError):
                    await asyncio.sleep(30)
