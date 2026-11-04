import copy
import json
import unittest
import research194_refinement as original
import research194_refinement_runner as original_runner
from research195_refinement_adapter import runtime


class AdapterTests(unittest.TestCase):
    def test_private_injection_does_not_change_sealed_imports(self):
        localizer=original.localize;controller=original.Controller;module=original_runner.r
        core,runner=runtime('L')
        self.assertIs(original.localize,localizer);self.assertIs(original.Controller,controller)
        self.assertIs(original_runner.r,module);self.assertIs(runner.r,core)
        self.assertIsNot(core,original)

    def test_null_obligation_reaches_request_without_edit_permission(self):
        candidate=[dict(label='p',antecedent='ready',consequent='valid',timing='same_sample',obligations=['response'])]
        evidence=[dict(id='unmapped',status='confirmed',label='legal',obligation=None,
            assertions=[dict(assertion='p',trigger=True,failure=True)])]
        case=dict(id='fixture',provenance={},specification='fixture only',signals=['ready','valid'],obligations=['response'])
        requests=[]
        for arm in ('F','P','L'):
            core,runner=runtime(arm);ctl=core.Controller(candidate,'R3',['response'])
            request=core.build_request(case,ctl,evidence,19507,0)
            context=json.loads(request['messages'][-1]['content'])
            self.assertIsNone(context['development_observations'][0]['obligation'])
            self.assertEqual(context['unmapped_localization'][0]['status'],'unknown_unmapped_obligation')
            self.assertEqual(context.get('localization',[]),[])
            self.assertFalse(ctl.fallback_enabled)
            requests.append(request)
        self.assertEqual({r['max_tokens'] for r in requests},{2048})

    def test_free_arms_cannot_add_delete_or_rebind_assertions(self):
        original_candidate=[dict(label='p',antecedent='ready',consequent='valid',timing='same_sample',obligations=['response'])]
        for arm in ('F','P'):
            core,_=runtime(arm);ctl=core.Controller(original_candidate,'R3',['response'])
            added=copy.deepcopy(original_candidate)+[dict(original_candidate[0],label='extra')]
            drift=[dict(original_candidate[0],obligations=['other'])]
            for candidate in (added,[],drift):
                with self.assertRaises(ValueError):ctl.parse(dict(assertions=candidate,reason='fixture'),[],lambda x:x)
            legal=[dict(original_candidate[0],consequent='!valid')]
            parsed,_=ctl.parse(dict(assertions=legal,reason='fixture'),[],lambda x:x)
            self.assertEqual(parsed,legal)

    def test_old_authorization_is_rejected_before_ledger_or_transport(self):
        import tempfile
        from pathlib import Path
        from unittest.mock import patch
        from research195_refinement_execute import AuthorizedBackend
        import research194_refinement_runner as common
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp);auth=folder/'authorization.json'
            common.dump(auth,dict(version='research194',protocol_sha256='seal',endpoint=common.ENDPOINT,approved=True,user_message_reference='old',maximum_model_calls=24))
            with patch('research195_refinement_execute.verify',return_value=({'maximum_model_calls':24},'seal')):
                with self.assertRaisesRegex(ValueError,'new_R195'):AuthorizedBackend(folder,auth,folder/'ledger.json')
            self.assertFalse((folder/'ledger.json').exists())

    def test_independent_generation_blocked_until_all_versions_freeze(self):
        import tempfile
        from pathlib import Path
        from unittest.mock import patch
        import research195_refinement_independent as independent
        import research194_refinement_runner as common
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp);common.dump(folder/'outcome.json',dict(status='running',population=24,protocol_sha256='seal'))
            with patch.object(independent,'verify',return_value=({},'seal')),patch.object(independent,'generate') as generate:
                with self.assertRaisesRegex(ValueError,'all_24'):independent.run(folder,folder,folder/'forbidden_output')
                generate.assert_not_called()
            self.assertFalse((folder/'forbidden_output').exists())


if __name__=='__main__':unittest.main()
