import copy
import json
import traceback
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
from juemeng_auto.demo import create_app
from juemeng_auto.browser_demo import submit_demo
from juemeng_auto.script.analyzers.mock import MockStoryboardAnalyzer
from juemeng_auto.script.analyzers.openai import OpenAIStoryboardAnalyzer, OpenAIAnalyzerError
from juemeng_auto.script.validator import validate_storyboard

SCRIPT=Path(__file__).resolve().parents[1].joinpath('examples/episode.txt').read_text(encoding='utf-8')

class CoreTests(unittest.TestCase):
    def setUp(self):
        self.app=create_app(); self.app.testing=True; self.client=self.app.test_client()
    def test_nonobject_and_malformed_json(self):
        for body in ['[]','[1]','null','1','true','"text"','{']:
            self.assertEqual(self.client.post('/analyze',data=body,content_type='application/json').status_code,400)
    def test_cross_origin(self):
        self.assertEqual(self.client.post('/analyze',json={'script':SCRIPT},headers={'Origin':'https://example.invalid'}).status_code,403)
    def test_body_limit(self):
        self.assertEqual(self.client.post('/analyze',data='x'*65000).status_code,413)
    def test_duplicate_resets_approval(self):
        ident=self.client.post('/analyze',json={'script':SCRIPT}).json['id']
        self.client.post('/approve/'+ident)
        self.assertFalse(self.client.post('/analyze',json={'script':SCRIPT}).json['approved'])
    def test_app_isolation(self):
        ident=self.client.post('/analyze',json={'script':SCRIPT}).json['id']
        other=create_app();other.testing=True
        self.assertEqual(other.test_client().get('/jobs/'+ident).status_code,404)
    def test_recovery_after_bad_request(self):
        self.client.post('/analyze',json=['invalid'])
        self.assertEqual(self.client.post('/analyze',json={'script':SCRIPT}).status_code,200)
    def test_browser_url_variants(self):
        for url in ['http://user@127.0.0.1:5050/','http://127.0.0.1:5050/?next=external','http://127.0.0.1:5050/#fragment']:
            with self.assertRaises(ValueError): submit_demo(None,url,SCRIPT)
    def test_validation_rejects_duplicate_shots(self):
        data=MockStoryboardAnalyzer().analyze('DEMO01',SCRIPT)
        _,issues=validate_storyboard(data);self.assertFalse(issues)
        shots=data['segments'][0]['shots'];shots[1]['shot_id']=shots[0]['shot_id']
        _,issues=validate_storyboard(data);self.assertTrue(issues)
    def test_openai_structured_output_contract(self):
        data=MockStoryboardAnalyzer().analyze('DEMO01',SCRIPT)
        client=Mock();client.responses.create.return_value=SimpleNamespace(output_text=json.dumps(data))
        analyzer=OpenAIStoryboardAnalyzer('placeholder','test-model','Direct the scene',Path('runtime'),client=client)
        result=analyzer.analyze('DEMO01',SCRIPT)
        self.assertEqual(result['episode_id'],'DEMO01')
        kwargs=client.responses.create.call_args.kwargs
        self.assertFalse(kwargs['store']);self.assertTrue(kwargs['text']['format']['strict'])
        self.assertEqual(kwargs['model'],'test-model')
    def test_openai_failure_sanitization_and_recovery(self):
        client=Mock();data=MockStoryboardAnalyzer().analyze('DEMO01',SCRIPT)
        client.responses.create.side_effect=[RuntimeError('PRIVATE_DIAGNOSTIC_SENTINEL'),SimpleNamespace(output_text=json.dumps(data))]
        analyzer=OpenAIStoryboardAnalyzer('placeholder','test-model','Instructions',Path('runtime'),client=client)
        try: analyzer.analyze('DEMO01',SCRIPT)
        except OpenAIAnalyzerError:
            self.assertNotIn('PRIVATE_DIAGNOSTIC_SENTINEL',traceback.format_exc())
        else: self.fail('Expected provider error')
        self.assertEqual(analyzer.analyze('DEMO01',SCRIPT)['episode_id'],'DEMO01')
    def test_openai_rejects_invalid_outputs(self):
        client=Mock();analyzer=OpenAIStoryboardAnalyzer('placeholder','test-model','Instructions',Path('runtime'),client=client)
        for output in ['', 'invalid', '[]', '{}']:
            client.responses.create.return_value=SimpleNamespace(output_text=output)
            with self.assertRaises(OpenAIAnalyzerError): analyzer.analyze('DEMO01',SCRIPT)

    def test_host_boundary(self):
        client=create_app().test_client()
        self.assertEqual(client.get('/',base_url='http://example.invalid').status_code,403)
        self.assertEqual(client.get('/',base_url='http://127.0.0.1:5050').status_code,200)
    def test_capacity_and_existing_draft(self):
        for i in range(100):
            response=self.client.post('/analyze',json={'script':f'Mira opens observatory door number {i}.'})
            self.assertEqual(response.status_code,200)
        self.assertEqual(self.client.post('/analyze',json={'script':'Jon opens another door.'}).status_code,503)
        self.assertEqual(self.client.post('/analyze',json={'script':'Mira opens observatory door number 0.'}).status_code,200)
    def test_real_sdk_construction_without_request(self):
        analyzer=OpenAIStoryboardAnalyzer('placeholder','test-model','Instructions',Path('runtime'))
        client=analyzer._create_client()
        try: self.assertTrue(callable(client.responses.create))
        finally: client.close()
