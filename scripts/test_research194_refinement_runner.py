"""Synthetic unit fixtures only, not experimental/native or model evidence."""
import copy
from pathlib import Path
import tempfile
import unittest
import research194_refinement as r
import research194_refinement_runner as run
from test_research194_refinement import INITIAL,validate


class FixtureAdapter:
    case_id='unit_fixture'
    case=dict(id='unit_fixture',initial=INITIAL,obligations=['o'],signals=['req','ready','ack'],provenance='synthetic unit fixture',specification='Unit control only.',rtl={})
    def validate(self,candidate):return validate(candidate)
    def measure(self,candidate,folder,detected):
        folder=Path(folder);folder.mkdir(parents=True,exist_ok=True)
        run.dump(folder/'result.json',dict(synthetic_unit_fixture=True))
        evidence=[dict(id=x,status='confirmed',label='violation',obligation='o',counted_target=True,cycle=i,
            assertions=[dict(assertion=candidate[0]['label'],obligations=['o'],trigger=x in detected,failure=x in detected)]) for i,x in enumerate(('old','new'))]
        return dict(candidate_sha256=r.digest(candidate),targets=['old','new'],detected_ids=list(detected),triggered_ids=list(detected),
            false_positives=[],critical_unknown=[],native_complete=True,reference_complete=True,evidence=evidence,
            executions=[dict(folder=str(folder))],cost=dict(native_compile_attempts=0,native_execution_attempts=0),native_bindings={str(folder/'result.json'):run.file_hash(folder/'result.json')})
    def evaluate(self,candidate,out,queries):
        detected=['old'] if len(candidate)>1 else [] if candidate[0]['antecedent']=='bad' else ['old','new']
        return self.measure(candidate,out,detected)

class FixtureSession:
    strategy='S0'
    def __init__(self,adapter,folder):self.adapter=adapter;self.folder=folder;self.rounds=[]
    def acquire(self,candidate,round,history):
        self.rounds.append(round);q=dict(id='q'+str(round),rows=[dict(req=round)])
        m=self.adapter.measure(candidate,self.folder/('q'+str(round)),['old'])
        return dict(queries=[q],query=q,measurement=m,cost=dict(model_calls=0,native_compile_attempts=0,native_execution_attempts=0))

class RunnerTests(unittest.TestCase):
    def test_three_round_loop_passes_real_state_and_freezes_retained_candidate(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);adapter=FixtureAdapter();baseline=adapter.measure(INITIAL,root/'baseline',['old'])
            session=FixtureSession(adapter,root/'session')
            final=[dict(INITIAL[0],antecedent='req')]
            backend=run.HandwrittenBackend([
                dict(edits=[dict(op='replace_field',assertion='p',field='antecedent',value='bad')],reason='fixture'),
                dict(edits=[dict(op='add_assertion',assertion=dict(INITIAL[0],label='extra',consequent='wrong'))],reason='fixture'),
                dict(assertions=final,reason='fixture')])
            outcome=run.run_trajectory(adapter,'R3',19407,root/'run',baseline,[],session,backend)
            self.assertEqual(session.rounds,[0,1,2]);self.assertEqual(outcome['model_calls'],0)
            self.assertEqual(run.read(root/'run'/'frozen.json'),final)
            self.assertEqual(run.read(root/'run'/'terminal_measurement.json')['candidate_sha256'],r.digest(final))
            self.assertEqual([x['stage'] for x in run.read(root/'run'/'rounds.json')],['local','compose','regenerate'])
            request=run.read(root/'run'/'round03'/'request.preview.json')
            self.assertEqual(request['max_tokens'],2048);self.assertIn('fallback_receipt',request['messages'][1]['content'])

    def test_noop_consumes_round_without_enabling_composition(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);adapter=FixtureAdapter();baseline=adapter.measure(INITIAL,root/'baseline',['old'])
            backend=run.HandwrittenBackend([dict(edits=[dict(op='replace_field',assertion='p',field='consequent',value='ack')],reason='fixture')]*3)
            outcome=run.run_trajectory(adapter,'R3',19407,root/'run',baseline,[],FixtureSession(adapter,root/'session'),backend)
            self.assertEqual(outcome['interface_failures'],3);self.assertEqual(outcome['accepted_rounds'],0)
            self.assertEqual(run.read(root/'run'/'frozen.json'),INITIAL)
            self.assertTrue(all(x['stage']=='local' for x in run.read(root/'run'/'controller_history.json')))

    def test_fault_sensitive_query_dedup(self):
        q=dict(id='q',rows=[dict(req=1)])
        self.assertEqual(len(run.query_union([q,q])),1)
        self.assertEqual(len(run.query_union([q,dict(q,_fault='dev')])),2)

if __name__=='__main__':unittest.main()
