"""Run `python main.py` to rank the sample messages for laser transmission."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from priority_scheduler import Message, PriorityScheduler, ScoredMessage, classify
from serial_publisher import publish_messages


def read_messages(path: Path) -> list[Message]:
    if path.suffix.lower() == ".json":
        raw = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(raw, list):
            raise ValueError("JSON input must be a list of messages")
        if any(not isinstance(item, (dict, str)) for item in raw):
            raise ValueError("JSON items must be strings or {id, text} objects")
        messages = [
            Message(str(item.get("id", f"M{index:02d}")), str(item["text"]), index)
            if isinstance(item, dict) else Message(f"M{index:02d}", item, index)
            for index, item in enumerate(raw, start=1)
        ]
    else:
        lines = [line.strip() for line in path.read_text(encoding="utf-8").splitlines()
                 if line.strip() and not line.lstrip().startswith("#")]
        messages = [Message(f"M{index:02d}", text, index)
                    for index, text in enumerate(lines, start=1)]
    if len({m.id for m in messages}) != len(messages):
        raise ValueError("Duplicate message IDs are not allowed")
    if any(not m.text.strip() or "\n" in m.text or "\r" in m.text for m in messages):
        raise ValueError("Each message must contain nonempty, single-line text")
    return messages


def bytes_waiting_before_urgent(messages: list[Message]) -> float:
    """Average payload bytes preceding urgent items (transport overhead excluded)."""
    bytes_before = 0
    waits = []
    for item in messages:
        if classify(item).priority >= 89:
            waits.append(bytes_before)
        bytes_before += len(item.text.encode("utf-8"))
    return sum(waits) / len(waits) if waits else 0.0


def main() -> None:
    parser = argparse.ArgumentParser(description="HackTX rule-based message prioritizer")
    parser.add_argument("--input", type=Path, default=Path(__file__).with_name("messages.txt"))
    parser.add_argument("--payload-output", type=Path, default=Path("transmit_order.txt"))
    parser.add_argument("--json-output", type=Path, default=Path("ranking.json"))
    parser.add_argument(
        "--serial-port",
        help="Optional serial port for ranked payloads, for example COM14",
    )
    parser.add_argument("--baud-rate", type=int, default=115200)
    parser.add_argument(
        "--serial-startup-delay-ms",
        type=int,
        default=2000,
        help="Wait after opening the port for the Arduino Uno to restart (default: 2000)",
    )
    parser.add_argument(
        "--serial-delay-ms",
        type=int,
        default=100,
        help="Delay between newline-delimited messages (default: 100)",
    )
    parser.add_argument(
        "--serial-ack-timeout-seconds",
        type=float,
        default=600.0,
        help="Maximum time to wait for each Arduino READY/SENT acknowledgement (default: 600)",
    )
    parser.add_argument(
        "--serial-no-handshake",
        action="store_true",
        help="Send without waiting for Arduino READY/SENT acknowledgements (not recommended)",
    )
    args = parser.parse_args()
    if args.serial_startup_delay_ms < 0 or args.serial_delay_ms < 0:
        parser.error("serial delays cannot be negative")
    if args.serial_ack_timeout_seconds <= 0:
        parser.error("serial acknowledgement timeout must be positive")

    incoming = read_messages(args.input)
    scheduler = PriorityScheduler()
    for message in incoming:
        scheduler.enqueue(message)
    ranked: list[ScoredMessage] = []
    while scheduler:
        ranked.append(scheduler.dequeue())

    print("\nRANKED LASER TRANSMISSION QUEUE")
    print("#   Score  Category      ID    Message")
    for position, row in enumerate(ranked, 1):
        print(f"{position:02d}. {row.priority:3d}    {row.category:<13} "
              f"{row.message.id:<4}  {row.message.text}")

    # This is a rough proxy for time spent queued, *not* actual on-air latency.
    fifo_bytes = bytes_waiting_before_urgent(incoming)
    ranked_bytes = bytes_waiting_before_urgent([row.message for row in ranked])
    print(f"\nAverage bytes ahead of urgent messages (>=89):")
    print(f"  Arrival order (FIFO): {fifo_bytes:.1f} bytes")
    print(f"  Priority order:       {ranked_bytes:.1f} bytes")
    print("  (Excludes optical framing, retries, and per-message transmission overhead.)")

    args.payload_output.write_text(
        "\n".join(row.message.text for row in ranked) + ("\n" if ranked else ""),
        encoding="utf-8",
    )
    args.json_output.write_text(json.dumps([
        {"rank": idx, "id": row.message.id, "text": row.message.text,
         "priority": row.priority, "category": row.category,
         "reason": row.matched_rule, "arrival_order": row.message.arrival_order}
        for idx, row in enumerate(ranked, start=1)
    ], indent=2) + "\n", encoding="utf-8")
    print(f"\nSaved payloads: {args.payload_output}")
    print(f"Saved detailed results: {args.json_output}")

    if args.serial_port:
        sent = publish_messages(
            [row.message.text for row in ranked],
            port=args.serial_port,
            baudrate=args.baud_rate,
            startup_delay=args.serial_startup_delay_ms / 1000,
            inter_message_delay=args.serial_delay_ms / 1000,
            wait_for_ack=not args.serial_no_handshake,
            ack_timeout=args.serial_ack_timeout_seconds,
        )
        print(
            f"Published {sent} ranked messages to {args.serial_port} "
            f"at {args.baud_rate} baud"
            f"{' with Arduino acknowledgements.' if not args.serial_no_handshake else '.'}"
        )


if __name__ == "__main__":
    main()
