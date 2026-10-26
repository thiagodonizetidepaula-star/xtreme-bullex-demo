"""Offline safety regression tests for account-scoped resets and study selection."""
import unittest
from clean_v1.study_selector import select,effective,update

def observation(pattern='Engolfo de alta',tf=1,wins=25,losses=15,held=10,validation=60):
    return {'pattern':pattern,'timeframe':tf,'wins':wins,'losses':losses,
        'accuracy':100*wins/(wins+losses),'validation_events':held,
        'validation_accuracy':validation}

class StudySelectorTests(unittest.TestCase):
    def test_every_qualified_strategy_selected(self):
        ids,details=select([
            observation(),
            observation('Falso rompimento de suporte',5,25,15,10,60),
            observation('Rompimento de resistência',1,22,18,10,60)])
        self.assertEqual(len(ids),3)
        self.assertIn('engolfo_alta_m1',ids)
        self.assertIn('falso_romp_suporte_m5',ids)
        self.assertTrue(all(d['eligible'] for d in details))
    def test_insufficient_sample_never_activates(self):
        ids,details=select([observation(wins=9,losses=1,held=10,validation=100)])
        self.assertEqual(ids,())
        self.assertFalse(details[0]['eligible'])
    def test_exactly_fifty_is_excluded(self):
        ids,_=select([observation(wins=20,losses=20,held=10,validation=60)])
        self.assertEqual(ids,())
        ids,_=select([observation(wins=25,losses=15,held=10,validation=50)])
        self.assertEqual(ids,())
    def test_unknown_names_are_not_executable(self):
        ids,details=select([observation('Padrao que nao existe',1,60,0,30,100)])
        self.assertEqual(ids,())
        self.assertEqual(details,[])
    def test_disabled_keeps_manual(self):
        state={'enabled_strategies':('sniper','price_action'),
            'auto_study_enabled':False,'auto_study_ids':('engolfo_alta_m1',)}
        self.assertEqual(effective(state),{'sniper','price_action'})
        state['auto_study_enabled']=True
        self.assertEqual(effective(state),{'engolfo_alta_m1'})
    def test_enabled_empty_never_defaults_to_sniper(self):
        state={'enabled_strategies':('sniper',),'auto_study_enabled':True,
            'auto_study_ids':()}
        self.assertEqual(effective(state),set())
    def test_update_isolated_to_this_session(self):
        class FakeStudy:
            def report(self):
                return {'patterns':[observation()],
                    'source':'Supabase','storage_error':''}
        state={'auto_study_enabled':True,'auto_study_ids':(),
            'study':FakeStudy()}
        update(state)
        self.assertEqual(state['auto_study_ids'],('engolfo_alta_m1',))
        self.assertEqual(len(state['auto_study_evidence']),1)
    def test_storage_error_does_not_replace_previous_approval(self):
        class FakeStudy:
            def report(self):
                return {'patterns':[],'storage_error':'indisponivel',
                    'source':'memória da sessão'}
        state={'auto_study_enabled':True,'auto_study_ids':('engolfo_alta_m1',),
            'study':FakeStudy()}
        update(state)
        self.assertEqual(state['auto_study_ids'],('engolfo_alta_m1',))

if __name__=='__main__':unittest.main()
