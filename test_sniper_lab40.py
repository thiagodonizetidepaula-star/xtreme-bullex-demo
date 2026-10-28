"""Regression checks for research-only XS-40; no broker needed."""
import math
import unittest
from sniper_lab40 import CANDIDATES,evaluate,MIN_OBSERVATIONS
from lab40_autoupdate import merge_closed_bars,favorite_rows

def sample_bars(n=310):
    rows=[]
    base=1700000040
    for i in range(n):
        open_=1.1000+0.0008*math.sin(i*0.24)+0.00011*i/n
        close=open_+0.00030*math.sin(i*0.67)+0.00007*math.sin(i*0.11)
        low=min(open_,close)-0.00014
        high=max(open_,close)+0.00017
        rows.append({'from':base+i*60,'open':open_,'close':close,'min':low,'max':high})
    return rows

class ResearchLabTests(unittest.TestCase):
    def test_40_unique_configurations(self):
        self.assertEqual(len(CANDIDATES),40)
        self.assertEqual(len({x['id'] for x in CANDIDATES}),40)
        self.assertEqual(len({(x['pattern'],x['source'],x['confirmation'],x['trend']) for x in CANDIDATES}),40)
    def test_40_results_and_no_unproven_approval(self):
        result=evaluate(sample_bars(),'EURUSD')
        self.assertEqual(len(result['strategies']),40)
        self.assertEqual(result['primary']['id'],'XS-PRINCIPAL')
        self.assertEqual(result['primary']['samples'],result['primary']['wins']+result['primary']['losses'])
        self.assertEqual(result['primary']['train_samples'],result['primary']['train_wins']+result['primary']['train_losses'])
        self.assertEqual(result['primary']['approved'],
                         result['primary']['samples']>=30 and result['primary']['rate'] is not None and result['primary']['rate']>60)
        self.assertIn('TENDENCIA',result['primary']['source'].upper())

        self.assertEqual(result['data_source'],'BULLEX_PRACTICE_CANDLES')
        for row in result['strategies']:
            self.assertEqual(row['samples'],row['wins']+row['losses'])
            self.assertEqual(row['train_samples'],row['train_wins']+row['train_losses'])
            self.assertEqual(row['approved'],row['samples']>=MIN_OBSERVATIONS and row['rate'] is not None and row['rate']>60)
            self.assertIn(row['status'],('APROVADA EM ESTUDO','EM ESTUDO','AMOSTRA INSUFICIENTE'))
            self.assertEqual(row['recent_samples'],
                             row['recent_wins']+row['recent_losses'])
            self.assertLessEqual(row['recent_samples'],20)
            self.assertLessEqual(row['recent_samples'],row['samples'])
            self.assertEqual(row['recent_validation_ready'],
                             row['recent_samples']>=10)
            if row['recent_samples']:
                self.assertAlmostEqual(row['recent_rate'],
                    100*row['recent_wins']/row['recent_samples'],places=2)
    def test_primary_matches_original_formula_and_flags_price_source(self):
        result=evaluate(sample_bars(),'EURUSD')
        main=result['primary']
        self.assertIn('original conferido',main['source_note'].lower())
        self.assertIn('WMA(5)',main['base'])
        self.assertEqual(main['price_source_assumption'],'hl2')
        self.assertIn('INDICE_5',main['price_source_confirmation'])
        self.assertIn('visual',main['plot_offset'])
    def test_sma1_sma34_wma5_reproduces_supplied_original(self):
        from strategy import sniper_buffers
        bars=sample_bars(125)
        fast,slow=sniper_buffers(bars,'hl2')
        values=[(b['max']+b['min'])/2 for b in bars]
        buffer=[values[i]-sum(values[i-33:i+1])/34 for i in range(33,len(values))]
        smooth=[sum((j+1)*z for j,z in enumerate(buffer[i-4:i+1]))/15 for i in range(4,len(buffer))]
        self.assertEqual(len(fast),len(buffer[4:]))
        for actual,expected in zip(fast,buffer[4:]):
            self.assertAlmostEqual(actual,expected,places=11)
        for actual,expected in zip(slow,smooth):
            self.assertAlmostEqual(actual,expected,places=11)
    def test_favorites_include_main_if_statistically_qualified(self):
        from lab40_autoupdate import favorite_rows
        result={'asset':'EURUSD','primary':{'id':'XS-PRINCIPAL','name':'Principal','wins':20,'losses':10},
                'strategies':[]}
        self.assertEqual([x['id'] for x in favorite_rows(result)],['XS-PRINCIPAL'])
    def test_gaps_and_doubles_rejected(self):
        candles=sample_bars()
        candles[115]['from']+=60
        with self.assertRaises(ValueError):evaluate(candles,'EURUSD')
    def test_ohlc_validation_rejects_bad_candle(self):
        candles=sample_bars()
        candles[95]['max']=candles[95]['min']-.01
        with self.assertRaises(ValueError):evaluate(candles,'EURUSD')
    def test_auto_merge_is_continuous_and_does_not_invent_candles(self):
        bars=sample_bars(120)
        merged=merge_closed_bars(bars[:100],bars[88:])
        self.assertEqual(len(merged),120)
        self.assertEqual(merged[-1]['from'],bars[-1]['from'])
        interrupted=[dict(b) for b in bars]
        interrupted[93]['from']+=60
        tail=merge_closed_bars([],interrupted)
        self.assertLess(len(tail),120)
        self.assertTrue(all(b['from']-a['from']==60 for a,b in zip(tail,tail[1:])))
    def test_no_favorite_without_30_oos_tests_and_strict_above_60(self):
        rows=[
            {"id":"XS-01","name":"Menos amostras","wins":25,"losses":4,"samples":29},
            {"id":"XS-02","name":"Exatamente 60%","wins":18,"losses":12,"samples":30},
            {"id":"XS-03","name":"Favorita real de estudo","wins":19,"losses":11,"samples":30}
        ]
        favorite=favorite_rows({"asset":"EURUSD","strategies":rows})
        self.assertEqual(len(favorite),1)
        self.assertEqual(favorite[0]['id'],"XS-03")
        self.assertEqual(favorite[0]['category'],"ESTUDO_HISTORICO_NAO_EXECUTAVEL")
    def test_research_helper_rejects_invalid_closed_m1_price(self):
        invalid=sample_bars(100)
        invalid[30]['open']=-1
        with self.assertRaises(ValueError):
            merge_closed_bars([],invalid)
    def test_research_scanner_strict_payout_above_80(self):
        from multiasset_lab import ResearchRegistry
        reg=ResearchRegistry()
        reg.set_market([
            {'asset':'EURUSD','payout':80,'open':True},
            {'asset':'EURUSD-OTC','payout':80.1,'open':True},
            {'asset':'GBPUSD','payout':84,'open':False}
        ])
        snap=reg.snapshot()
        self.assertEqual(snap['asset_count'],1)
        self.assertEqual(snap['catalog'][0]['asset'],'EURUSD-OTC')
        self.assertFalse(snap['parallel_orders_supported'])
        self.assertFalse(snap['m5_execution_supported'])
    def test_derive_only_completed_m5_from_real_contiguous_m1(self):
        from multiasset_lab import aggregate_m5
        bars=sample_bars(620)
        m5=aggregate_m5(bars)
        self.assertGreater(len(m5),87)
        self.assertTrue(all(int(n['from'])-int(m['from'])==300 for m,n in zip(m5,m5[1:])))
        result=evaluate(m5,'EURUSD',timeframe='M5')
        self.assertEqual(result['timeframe'],'M5')
        self.assertEqual(len(result['strategies']),40)
        self.assertEqual(result['primary']['timeframe'],'M5')
        for x in result['strategies']:
            self.assertEqual(x['approved'],x['samples']>=30 and x['rate'] is not None and x['rate']>60)
    def test_50_percent_is_research_watchlist_only_not_a_trade(self):
        from multiasset_lab import shortlist
        artificial={'asset':'EURUSD','timeframe':'M1','to':1700000640,
          'primary':{'id':'XS-PRINCIPAL','name':'Sniper Principal','wins':16,'losses':14,'samples':30,'principal':True},
          'strategies':[]}
        watch=shortlist(artificial,81)
        self.assertEqual(len(watch),1)
        self.assertFalse(watch[0]['passes_break_even_math'])
        self.assertEqual(watch[0]['status'],'ESTUDO_CANDIDATO_NAO_EXECUTAVEL')
        self.assertEqual(shortlist(artificial,80),[])
        self.assertEqual(shortlist(artificial,79),[])
    def test_scanner_tracks_two_timeframes_without_ordering(self):
        from multiasset_lab import ResearchRegistry,aggregate_m5
        reg=ResearchRegistry();reg.set_market([{'asset':'EURUSD','open':True,'payout':82}])
        bars=sample_bars(620)
        self.assertTrue(reg.ingest('EURUSD','M1',bars,'test'))
        self.assertTrue(reg.ingest('EURUSD','M5',aggregate_m5(bars),'test'))
        snap=reg.snapshot()
        self.assertEqual(snap['studies'],2)
        self.assertEqual(snap['ready_by_timeframe']['M1'],1)
        self.assertEqual(snap['ready_by_timeframe']['M5'],1)
        self.assertEqual(snap['mode'],'RESEARCH_ONLY')
    def test_live_stream_120_candles_is_recorded_even_without_favorites(self):
        # An analyzed asset is NOT the same as an approved/validated strategy.
        # A short 120-bar stream must still publish research progress.
        from multiasset_lab import ResearchRegistry
        reg=ResearchRegistry()
        reg.set_market([{'asset':'EURUSD','payout':85.0,'open':True}])
        self.assertTrue(reg.ingest('EURUSD','M1',sample_bars(120),'STREAMING_M1'))
        status=reg.snapshot()
        self.assertEqual(status['studies'],1)
        self.assertEqual(status['researched_assets'],1)
        self.assertEqual(status['ready_by_timeframe']['M1'],1)
        self.assertEqual(status['mode'],'RESEARCH_ONLY')
        self.assertFalse(status['m5_execution_supported'])
    def test_contiguous_m5_seed_starts_as_insufficient_not_a_fake_signal(self):
        from multiasset_lab import ResearchRegistry,aggregate_m5
        reg=ResearchRegistry()
        reg.set_market([{'asset':'EURUSD','payout':85,'open':True}])
        bars=aggregate_m5(sample_bars(120))
        self.assertTrue(reg.ingest('EURUSD','M5',bars,'STREAMING_M1'))
        status=reg.snapshot()
        self.assertEqual(status['studies'],1)
        self.assertEqual(status['ready_by_timeframe']['M5'],0)
        self.assertEqual(status['signals'],[])
    def test_research_threads_recover_inside_serving_worker(self):
        # Static regression: avoid importing app.py (which starts live threads).
        from pathlib import Path
        source=(Path(__file__).resolve().parent/'app.py').read_text()
        self.assertIn('def ensure_research_threads():',source)
        self.assertIn('if pid!=research_thread_pid:',source)
        self.assertIn('ensure_research_threads()\n    if request.method',source)
        self.assertIn("('MultiTimeframeStudy',multi_worker)",source)
        self.assertIn("('ResearchMarketScanner',multi_paused_scanner)",source)
        self.assertIn("'scanner_alive':any(",source)
    def test_short_history_rejected(self):
        with self.assertRaises(ValueError):evaluate(sample_bars(40),'EURUSD')
if __name__=='__main__':
    unittest.main()
