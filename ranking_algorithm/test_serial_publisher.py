import unittest

from serial_publisher import SerialPublishError, publish_messages


class FakeSerial:
    def __init__(self, status_lines=None, **kwargs):
        self.kwargs = kwargs
        self.writes = []
        self.flush_calls = 0
        self.status_lines = list(status_lines or [])

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False

    def write(self, payload):
        self.writes.append(payload)
        return len(payload)

    def flush(self):
        self.flush_calls += 1

    def readline(self):
        return self.status_lines.pop(0) if self.status_lines else b""


class SerialPublisherTests(unittest.TestCase):
    def test_messages_are_newline_delimited_utf8_frames(self):
        created = []
        delays = []

        def factory(**kwargs):
            device = FakeSerial([b"READY\n", b"SENT 1\n", b"SENT 2\n"], **kwargs)
            created.append(device)
            return device

        sent = publish_messages(
            ["Fire detected", "Temperature 24.5 C"],
            port="COM14",
            baudrate=115200,
            startup_delay=2.0,
            inter_message_delay=0.1,
            serial_factory=factory,
            sleep=delays.append,
        )

        self.assertEqual(sent, 2)
        self.assertEqual(created[0].kwargs["port"], "COM14")
        self.assertEqual(created[0].kwargs["baudrate"], 115200)
        self.assertEqual(
            created[0].writes,
            [b"Fire detected\n", b"Temperature 24.5 C\n"],
        )
        self.assertEqual(created[0].flush_calls, 2)
        self.assertEqual(delays, [2.0, 0.1])

    def test_diagnostic_lines_before_ready_are_ignored(self):
        created = []

        def factory(**kwargs):
            device = FakeSerial([b"[TX] Starting\n", b"READY\n", b"SENT 1\n"], **kwargs)
            created.append(device)
            return device

        publish_messages(
            ["Fire detected"],
            port="COM14",
            startup_delay=0,
            inter_message_delay=0,
            serial_factory=factory,
        )
        self.assertEqual(created[0].writes, [b"Fire detected\n"])

    def test_port_is_required(self):
        with self.assertRaises(ValueError):
            publish_messages([], port="", serial_factory=FakeSerial)

    def test_short_write_fails(self):
        class ShortWriteSerial(FakeSerial):
            def write(self, payload):
                return len(payload) - 1

        with self.assertRaises(SerialPublishError):
            publish_messages(
                ["Fire detected"],
                port="COM14",
                startup_delay=0,
                serial_factory=ShortWriteSerial,
                wait_for_ack=False,
            )


if __name__ == "__main__":
    unittest.main()
