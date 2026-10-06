import os,sys,pathlib,unittest,time
from unittest.mock import patch
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]))
os.environ['APP_ACCESS_KEY']='test-access-key-only'
from strategy import analyze,risk_ok,validate_config
import app as module

class Core(unittest.TestCase):
    def setUp(self):
        self.web=module.app.test_client()
        module.state.update(connected=False,running=False,uncertain=False,trades=[])
    def login(self):
        return self.web.post('/api/access',json={'key':'test-access-key-only'}).json['csrf']
    def test_auth_and_csrf(self):
        self.assertEqual(self.web.get('/api/state').status_code,401)
        self.assertEqual(self.web.post('/api/access',json={'key':'wrong'}).status_code,401)
        token=self.login()
        self.assertEqual(self.web.post('/api/start',json={}).status_code,403)
        self.assertEqual(self.web.post('/api/start',json={},headers={'X-CSRF-Token':token}).status_code,409)
    def test_stops_and_risk_reserve(self):
        c=module.state['config'];self.assertTrue(risk_ok(c,0,0))
        self.assertFalse(risk_ok(c,-9,0));self.assertFalse(risk_ok(c,20,0));self.assertFalse(risk_ok(c,0,5))
    def test_invalid_config(self):
        for changed in [{'stake':-1},{'limit':2.5},{'payout':101},{'asset':'../x'},{'stake':float('nan')}]:
            with self.assertRaises(ValueError):validate_config({**module.state['config'],**changed})
    def test_closed_candles_and_stale(self):
        bars=[{'from':i*60,'close':100+i*.1} for i in range(100)]
        a=analyze(bars,6000);b=analyze(bars+[{'from':6000,'close':900}],6000)
        self.assertEqual(a,b)
        self.assertIsNone(analyze(bars,6030)['direction'])
        self.assertIn('próxima vela',analyze(bars,6030)['reason'])
        self.assertIn('checks',analyze(bars,6030))
        self.assertEqual(analyze(bars,6030)['ema9'],a['ema9'])
        self.assertIn('atrasadas',analyze(bars,6120)['reason'])
        with self.assertRaises(ValueError):analyze(bars[:-2]+bars[-1:],6000)
    def test_failed_connection_does_not_enable_bot(self):
        token=self.login()
        with patch.object(module,'Client') as cls:
            cls.return_value.call.side_effect=RuntimeError('Falha de conexão')
            r=self.web.post('/api/connect',json={'email':'test@example.com','password':'not-real'},headers={'X-CSRF-Token':token})
        self.assertEqual(r.status_code,502);self.assertFalse(module.state['connected'])
    def test_uncertain_order_blocks_restart(self):
        token=self.login();module.state.update(uncertain=True,connected=True)
        r=self.web.post('/api/start',json={},headers={'X-CSRF-Token':token})
        self.assertEqual(r.status_code,409)
    def test_management_counts_only_confirmed_results_today(self):
        module.state['trades']=[{'day':module.day(),'status':'WIN','profit':1.68},{'day':module.day(),'status':'LOSS','profit':-2},{'day':module.day(),'status':'IGNORADA'},{'day':'2000-01-01','status':'WIN','profit':50}]
        token=self.login();m=self.web.get('/api/state').json['management']
        self.assertEqual((m['wins'],m['losses'],m['used']),(1,1,2))
        self.assertEqual(m['profit'],-.32)
        self.assertEqual(m['stop_loss_remaining'],9.68)
    def test_page_and_health(self):
        self.assertEqual(self.web.get('/').status_code,200)
        self.assertEqual(self.web.get('/health').status_code,200)

if __name__=='__main__':unittest.main()

class OrderGuards(unittest.TestCase):
    def setUp(self):
        import worker
        from unittest.mock import MagicMock
        self.worker=worker;self.api=MagicMock();worker.api=self.api
        self.api.check_connect.return_value=True
        self.api.get_balance_mode.return_value='PRACTICE'
        self.api.get_all_open_time.return_value={'turbo':{'EURUSD':{'open':True}}}
        self.api.get_all_profit.return_value={'EURUSD':{'turbo':.87}}
        self.api.get_all_init_v2.return_value={'turbo':{'actives':{'1':{'name':'front.EURUSD','enabled':True,'is_suspended':False,'option':{'profit':{'commission':13}}}}}}
        self.api.get_server_timestamp.return_value=time.time()
        self.api.get_balance.return_value=100
        self.api.buy.return_value=(True,123)
        self.c={'op':'order','asset':'EURUSD','stake':2,'payout':80,'direction':'call','candle':time.time()-61}
    def test_real_is_blocked(self):
        self.api.get_balance_mode.return_value='REAL'
        with self.assertRaises(RuntimeError):self.worker.dispatch(self.c)
        self.api.buy.assert_not_called()
    def test_low_payout_is_blocked(self):
        self.api.get_all_init_v2.return_value['turbo']['actives']['1']['option']['profit']['commission']=30
        self.assertFalse(self.worker.dispatch(self.c)['sent']);self.api.buy.assert_not_called()
    def test_scanner_includes_otc_and_excludes_exact_80_and_closed(self):
        import copy
        base=self.api.get_all_init_v2.return_value['turbo']['actives']['1']
        otc=copy.deepcopy(base);otc['name']='front.EURUSD-OTC'
        exact=copy.deepcopy(base);exact['name']='front.GBPUSD';exact['option']['profit']['commission']=20
        closed=copy.deepcopy(base);closed['name']='front.USDJPY';closed['is_suspended']=True
        self.api.get_all_init_v2.return_value['turbo']['actives'].update({'2':otc,'3':exact,'4':closed})
        assets=self.worker.dispatch({'op':'market','payout':80})['assets']
        self.assertEqual({a['asset'] for a in assets},{'EURUSD','EURUSD-OTC'})
    def test_exact_80_is_blocked_at_order(self):
        self.api.get_all_init_v2.return_value['turbo']['actives']['1']['option']['profit']['commission']=20
        self.assertFalse(self.worker.dispatch(self.c)['sent']);self.api.buy.assert_not_called()
    def test_late_order_is_blocked(self):
        self.c['candle']=time.time()-80
        self.assertFalse(self.worker.dispatch(self.c)['sent']);self.api.buy.assert_not_called()
    def test_demo_order_sent_once(self):
        r=self.worker.dispatch(self.c);self.assertTrue(r['sent']);self.api.buy.assert_called_once_with(2,'EURUSD','call',1)
    def test_uncertain_response_not_retried(self):
        self.api.buy.return_value=(False,None)
        with self.assertRaises(RuntimeError):self.worker.dispatch(self.c)
        self.api.buy.assert_called_once()
