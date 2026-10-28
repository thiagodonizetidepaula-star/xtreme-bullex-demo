"""Regression tests for optional PRACTICE cooldown between settled orders."""
import unittest
from strategy import entry_pause_seconds, validate_config

def config(mode='off'):
    return {'asset':'EURUSD','stake':2,'payout':80,'stop_win':20,
            'stop_loss':10,'limit':5,'strategy':'lab_m1',
            'stop_win_enabled':True,'stop_loss_enabled':True,
            'sniper_source':'hl2','entry_pause_mode':mode}

class EntryPauseTests(unittest.TestCase):
    def test_all_operations_wait_exact_configured_minutes(self):
        for mode,seconds in [('all_2',120),('all_3',180),('all_5',300)]:
            for result in ('WIN','LOSS','EMPATE'):
                with self.subTest(mode=mode,result=result):
                    self.assertEqual(entry_pause_seconds(mode,result),seconds)

    def test_loss_only_waits_after_single_loss(self):
        self.assertEqual(entry_pause_seconds('loss_3','LOSS'),180)
        for result in ('WIN','EMPATE'):
            self.assertEqual(entry_pause_seconds('loss_3',result),0)

    def test_no_pause_for_unconfirmed_broker_outcomes(self):
        for status in ('ABERTA','ENVIANDO','INCERTA','IGNORADA','RECUSADA',None):
            for mode in ('all_2','all_3','all_5','loss_3'):
                with self.subTest(status=status,mode=mode):
                    self.assertEqual(entry_pause_seconds(mode,status),0)

    def test_off_is_backward_compatible(self):
        self.assertEqual(entry_pause_seconds('off','LOSS'),0)
        cfg=config();cfg.pop('entry_pause_mode')
        self.assertEqual(validate_config(cfg)['entry_pause_mode'],'off')

    def test_only_documented_modes_accepted(self):
        for mode in ('off','all_2','all_3','all_5','loss_3'):
            self.assertEqual(validate_config(config(mode))['entry_pause_mode'],mode)
        for mode in ('all_1','loss_5',3,True,None):
            with self.subTest(mode=mode):
                with self.assertRaises(ValueError):
                    validate_config(config(mode))

    def test_settlement_never_changes_risk_settings(self):
        cfg=validate_config(config('loss_3'))
        self.assertEqual(cfg['stake'],2)
        self.assertEqual(cfg['limit'],5)
        self.assertEqual(cfg['stop_loss'],10)
        self.assertTrue(cfg['stop_loss_enabled'])

if __name__=='__main__':
    unittest.main()
