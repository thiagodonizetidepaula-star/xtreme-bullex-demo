import unittest
from signals import SignalBook
class SignalBookTests(unittest.TestCase):
    def make(self,d='BUY',expiry=5):
        b=SignalBook();r=b.add({'direction':d},'A','Ativo',60,expiry,100,10,200);return b,r
    def test_call_put_and_tie(self):
        for direction,price,result in [('BUY',11,'positive'),('BUY',9,'negative'),('SELL',9,'positive'),('SELL',11,'negative'),('BUY',10,'tie')]:
            b,r=self.make(direction)
            for t in (101,102,103,104):b.tick('A',t,10)
            b.tick('A',105,price);self.assertEqual(r['status'],result)
    def test_gap_and_wrong_asset_do_not_invent_result(self):
        b,r=self.make();b.tick('B',105,20);self.assertEqual(r['status'],'pending')
        b.tick('A',105,20);self.assertEqual(r['status'],'inconclusive')
    def test_expiry_is_frozen_and_result_once(self):
        b,r=self.make(expiry=1);b.tick('A',101,11);b.tick('A',102,9)
        self.assertEqual(r['status'],'positive');self.assertEqual(r['exit_price'],11)
        self.assertEqual(r['expires_at'],101)
    def test_timeout_and_counts(self):
        b,r=self.make();snapshot=b.snapshot(109)
        self.assertEqual(snapshot['counts']['inconclusive'],1)
        self.assertEqual(snapshot['counts']['positive'],0)
    def test_late_tick_inconclusive(self):
        b,r=self.make();b.tick('A',104,10);b.tick('A',108,11)
        self.assertEqual(r['status'],'inconclusive')

    def test_feed_records_actual_next_tick_and_frozen_expiry(self):
        from unittest.mock import patch
        from feed import Feed
        f=Feed({});f.symbol='A';f.connected=True;f.expiry=15;f.history_requested=True
        t=1800000000
        f.current={'time':t-60,'open':9,'high':11,'low':9,'close':10,'first':t-60,'last':t-1,'max_gap':1}
        with patch.object(f,'source_now',return_value=t),patch('feed.confirmed_signal',return_value={'direction':'BUY','price':10,'time':t,'reason':'teste'}):f.tick(t,12)
        self.assertEqual(f.book.rows[0]['entry_price'],12)
        self.assertEqual(f.book.rows[0]['expires_at'],t+15)
        f.expiry=60
        self.assertEqual(f.book.rows[0]['expiry'],15)
