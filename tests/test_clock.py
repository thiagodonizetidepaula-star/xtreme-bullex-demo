import unittest
from unittest.mock import MagicMock,patch
import worker
from bullexapi.ws.objects.timesync import TimeSync
class ClockTests(unittest.TestCase):
    def setUp(self):
        self.api=MagicMock();worker.api=self.api;self.api.api.timesync=TimeSync();self.api.get_server_timestamp.side_effect=lambda:self.api.api.timesync.server_timestamp
    def sample(self,timestamp,mono=100):
        with patch.object(worker.time,'monotonic',return_value=mono):self.api.api.timesync.server_timestamp=timestamp*1000
    def test_advances_between_sync_messages(self):
        self.sample(6000)
        with patch.object(worker.time,'monotonic',return_value=101.6),patch.object(worker.time,'time',return_value=6001.6):self.assertAlmostEqual(worker.broker_now(),6001.6)
    def test_old_sample_blocks(self):
        self.sample(6000)
        with patch.object(worker.time,'monotonic',return_value=106),patch.object(worker.time,'time',return_value=6006):
            with self.assertRaises(RuntimeError):worker.broker_now()
    def test_divergence_blocks(self):
        self.sample(6000)
        with patch.object(worker.time,'monotonic',return_value=100),patch.object(worker.time,'time',return_value=6020):
            with self.assertRaises(RuntimeError):worker.broker_now()
    def test_delayed_sample_cannot_extend_entry_window(self):
        self.sample(6000)
        with patch.object(worker.time,'monotonic',return_value=101),patch.object(worker.time,'time',return_value=6002.5):self.assertEqual(worker.broker_now(),6002.5)
    def test_new_sample_refreshes_age(self):
        self.sample(6000);self.sample(6004,104)
        with patch.object(worker.time,'monotonic',return_value=105),patch.object(worker.time,'time',return_value=6005):self.assertEqual(worker.broker_now(),6005)
