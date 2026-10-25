import unittest

from priority_scheduler import Message, PriorityScheduler, classify


class SchedulerTests(unittest.TestCase):
    def test_emergency_before_telemetry(self):
        q = PriorityScheduler()
        q.enqueue(Message("M1", "Battery level at 87%.", 1))
        q.enqueue(Message("M2", "Fire detected in Sector B.", 2))
        self.assertEqual(q.dequeue().message.id, "M2")

    def test_equal_scores_remain_fifo(self):
        q = PriorityScheduler()
        q.enqueue(Message("M2", "Routine maintenance scheduled tomorrow.", 2))
        q.enqueue(Message("M1", "Communication link operating normally.", 1))
        self.assertEqual(q.dequeue().message.id, "M1")

    def test_new_emergency_jumps_ahead_of_waiting_work(self):
        q = PriorityScheduler()
        q.enqueue(Message("M1", "Battery level at 87%.", 1))
        q.enqueue(Message("M2", "Humidity sensor reports 45%.", 2))
        self.assertEqual(q.dequeue().message.id, "M1")  # Already sent
        q.enqueue(Message("M3", "Fire detected in Sector B.", 3))
        self.assertEqual(q.dequeue().message.id, "M3")
        self.assertEqual(q.dequeue().message.id, "M2")

    def test_negation(self):
        result = classify(Message("M1", "No fire detected in Sector B.", 1))
        self.assertLess(result.priority, 89)

    def test_default_priority(self):
        result = classify(Message("M1", "New subsystem report ready.", 1))
        self.assertEqual(result.priority, 35)


if __name__ == "__main__":
    unittest.main()
