# HackTX Laser Message Priority Scheduler (No AI Dependencies)

The simplest working priority engine for the Arduino-to-ESP32 optical messaging
demo. It sorts the 30 sample messages, generates a transmission-order file, and
reports a basic comparison against first-in-first-out (FIFO) scheduling.

## Quick start in VS Code

1. Extract all ZIP contents into one folder.
2. Open that folder in VS Code.
3. Select any Python 3.10+ interpreter (no third-party packages needed).
4. In the VS Code Terminal, run:

```bash
python main.py
```

On some systems, use `python3 main.py` instead.

## Send the ranked queue to an Arduino Uno

Install the one serial dependency in your active virtual environment:

```bash
python -m pip install -r requirements.txt
```

With the Uno connected as `COM14`, rank the input and send it at 115200 baud:

```bash
python main.py --serial-port COM14
```

Each ranked payload is sent as UTF-8 text ending in `\n`. The matching Uno
sketch must send `READY` after its startup calibration and `SENT <number>`
after each payload finishes transmitting; Python waits for these acknowledgements
before sending the next line. This prevents the Uno's receive buffer from
overflowing while a slow laser transmission is underway. The program waits two
seconds after opening the port because opening serial commonly restarts an Uno.
Adjust the USB baud rate, acknowledgement timeout, or inter-message delay as
needed:

```bash
python main.py --serial-port COM14 --baud-rate 115200 --serial-ack-timeout-seconds 600
```

The normal `transmit_order.txt` and `ranking.json` outputs are still written
before serial publishing starts.

Outputs are written to the current working directory:

- `transmit_order.txt`: **one prioritized message per line**.
- `ranking.json`: message ID, original arrival order, score, category, and reason.

Run tests:

```bash
python -m unittest -v test_scheduler.py
```

Run a different input file:

```bash
python main.py --input my_messages.txt --payload-output ready_to_send.txt
```

Input can be `.txt` (one message per line) or `.json` (list of strings or
`{"id":"M01","text":"..."}` objects).

## How it works

1. `classify()` in `priority_scheduler.py` uses case-insensitive phrase patterns
   and contextual negation checks to select the highest applicable rule.
2. Each message is inserted into a heap-based `PriorityScheduler`.
3. `dequeue()` returns the most urgent waiting message; ties stay FIFO.
4. `main.py` writes the ordered payloads and a JSON audit trail.

`enqueue()` and `dequeue()` take O(log n) time; classification scans a small,
fixed set of rules. The `PriorityScheduler` can accept **new** messages while
earlier messages are queued; it never interrupts a message already being sent.

## Files

| File | Purpose |
| --- | --- |
| `main.py` | CLI entry point, input/output, and FIFO comparison |
| `priority_scheduler.py` | Classification rules and live priority queue |
| `messages.txt` | 30 example remote-station messages |
| `test_scheduler.py` | Unit tests for emergency priority, FIFO ties, and live insertion |

## Integration with laser transmitter

This code intentionally does NOT write directly to a USB serial port because
the current Arduino firmware's framing/handshake format has not yet been
specified. Use `transmit_order.txt` as the input to the transmitter adapter.
The next step is to connect a sender that reads one line, sends it using the
Arduino's existing frame protocol, waits for acknowledgment or completion,
then requests the next prioritized message.

For live arrivals, call `scheduler.enqueue(Message(...))` when data arrives,
and `scheduler.dequeue()` **only when the transmitter is ready**.

## Scope and limitations

- This is **rule-based**, not machine learning or an LLM.
- It is a demonstration, not a validated real-world emergency alert system.
- Unrecognized alerts may get the default 35 score. Add patterns in `RULES`.
- Basic negation detection handles examples like `No fire detected` but is not
  a full natural-language parser.
- Priority scheduling can reduce **latency for urgent messages**; it does not
  increase the physical bitrate of the laser link.
- The FIFO comparison is based on payload-byte positions only, **not** actual
  hardware measurements. Measure arrival times on the ESP32 for a true result.
