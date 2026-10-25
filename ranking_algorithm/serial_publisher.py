"""Publish already-ranked message payloads to an Arduino over a serial port."""

from __future__ import annotations

import time
from collections.abc import Callable, Sequence
from typing import Any


class SerialPublishError(RuntimeError):
    """Raised when ranked messages cannot be published over serial."""


def _wait_for_status(
    device: Any,
    expected_prefix: str,
    timeout: float,
    *,
    monotonic: Callable[[], float] = time.monotonic,
) -> str:
    """Read diagnostic lines until the Arduino emits the expected status."""
    deadline = monotonic() + timeout
    while monotonic() < deadline:
        line = device.readline().decode("utf-8", errors="replace").strip()
        if line.startswith(expected_prefix):
            return line
        if line.startswith("ERROR"):
            raise SerialPublishError(f"Arduino reported: {line}")
    raise SerialPublishError(
        f"Timed out after {timeout:g}s waiting for Arduino status: {expected_prefix}"
    )


def publish_messages(
    messages: Sequence[str],
    *,
    port: str,
    baudrate: int = 115200,
    startup_delay: float = 2.0,
    inter_message_delay: float = 0.1,
    wait_for_ack: bool = True,
    ack_timeout: float = 600.0,
    serial_factory: Callable[..., Any] | None = None,
    sleep: Callable[[float], None] = time.sleep,
) -> int:
    """Send one UTF-8 message per newline-delimited serial frame.

    Opening a serial connection normally resets an Arduino Uno. When
    ``wait_for_ack`` is enabled (the default), the Uno must emit ``READY``
    before receiving data and ``SENT <number>`` after it finishes transmitting
    each payload. This prevents the Uno's serial buffer from overflowing while
    it is occupied sending a slow optical frame. ``serial_factory`` and
    ``sleep`` are injectable for tests.
    """
    if not port.strip():
        raise ValueError("A serial port is required (for example, COM14)")
    if baudrate <= 0:
        raise ValueError("baudrate must be positive")
    if startup_delay < 0 or inter_message_delay < 0:
        raise ValueError("serial delays cannot be negative")
    if ack_timeout <= 0:
        raise ValueError("ack_timeout must be positive")

    if serial_factory is None:
        try:
            import serial
        except ImportError as exc:
            raise SerialPublishError(
                "Serial publishing needs pyserial. Install it with "
                "python -m pip install -r requirements.txt"
            ) from exc
        serial_factory = serial.Serial

    try:
        with serial_factory(
            port=port,
            baudrate=baudrate,
            timeout=min(1.0, ack_timeout),
            write_timeout=5,
        ) as device:
            if startup_delay:
                sleep(startup_delay)
            if wait_for_ack:
                _wait_for_status(device, "READY", ack_timeout)

            for index, message in enumerate(messages):
                payload = message.encode("utf-8") + b"\n"
                written = device.write(payload)
                if written != len(payload):
                    raise SerialPublishError(
                        f"Only wrote {written} of {len(payload)} bytes for message {index + 1}"
                    )
                device.flush()
                if wait_for_ack:
                    _wait_for_status(device, f"SENT {index + 1}", ack_timeout)
                if inter_message_delay and index < len(messages) - 1:
                    sleep(inter_message_delay)
    except SerialPublishError:
        raise
    except Exception as exc:
        raise SerialPublishError(f"Could not publish to {port}: {exc}") from exc

    return len(messages)
