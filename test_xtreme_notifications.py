"""Regression checks for session-scoped DEMO notifications (no broker I/O)."""
import os
import unittest
from unittest.mock import patch

from clean_v1 import notifications

class NotificationTests(unittest.TestCase):
    def test_event_names_are_real_states(self):
        state={}
        with patch.dict(os.environ,{"XTREME_PUSH_PUBLIC_KEY":"","XTREME_PUSH_PRIVATE_KEY":""}):
            notifications.publish(state,"opportunity","EURUSD-OTC","CALL")
            notifications.publish(state,"order","EURUSD-OTC","CALL")
            notifications.publish(state,"win","EURUSD-OTC","CALL",1.72)
            notifications.publish(state,"loss","EURUSD-OTC","PUT",-2.)
        items=state["_alert_events"]
        self.assertEqual([e["kind"] for e in items],["opportunity","order","win","loss"])
        self.assertEqual(len({e["id"] for e in items}),4)
        self.assertIn("WIN",items[2]["title"])
        self.assertIn("LOSS",items[3]["title"])

    def test_unknown_event_has_no_payload(self):
        state={}
        notifications.publish(state,"arbitrary")
        self.assertNotIn("_alert_events",state)

    def test_no_ssrf_via_subscription(self):
        for endpoint in ("http://localhost/x","https://127.0.0.1/x",
                         "https://internal.example/x",
                         "https://fcm.googleapis.com.attacker.com/x",
                         "https://fcm.googleapis.com:8080/x"):
            self.assertFalse(notifications._valid_endpoint(endpoint),endpoint)
        self.assertTrue(notifications._valid_endpoint("https://fcm.googleapis.com/fcm/send/token"))
        self.assertTrue(notifications._valid_endpoint("https://updates.push.services.mozilla.com/wpush/v2/token"))

    def test_subscribe_is_account_scoped_and_unsubscribe(self):
        sub={"endpoint":"https://fcm.googleapis.com/fcm/send/token",
             "keys":{"auth":"A"*22,"p256dh":"B"*87}}
        session={}
        self.assertEqual(notifications.subscribe(session,sub),1)
        self.assertEqual(notifications.subscribe(session,sub),1)
        self.assertEqual(len(session["_push_subscribers"]),1)
        notifications.unsubscribe(session,sub["endpoint"])
        self.assertEqual(session["_push_subscribers"],[])

    def test_subscriptions_are_never_returned_in_event(self):
        state={}
        sub={"endpoint":"https://fcm.googleapis.com/fcm/send/token",
             "keys":{"auth":"A"*22,"p256dh":"B"*87}}
        notifications.subscribe(state,sub)
        with patch.dict(os.environ,{"XTREME_PUSH_PUBLIC_KEY":"","XTREME_PUSH_PRIVATE_KEY":""}):
            notifications.publish(state,"opportunity","GBPUSD-OTC","PUT")
        self.assertNotIn("endpoint",str(state["_alert_events"]))
        self.assertNotIn("keys",str(state["_alert_events"]))

if __name__=="__main__":
    unittest.main()
