import unittest
from pathlib import Path
from juemeng_auto.demo import create_app
from juemeng_auto.browser_demo import submit_demo
from juemeng_auto.script.analyzers.mock import MockStoryboardAnalyzer
from juemeng_auto.script.validator import validate_storyboard

class DemoTests(unittest.TestCase):
    def test_review_flow(self):
        app=create_app();app.testing=True;c=app.test_client()
        script=(Path(__file__).resolve().parents[1]/'examples/episode.txt').read_text()
        r=c.post('/analyze',json={'script':script})
        self.assertEqual(r.status_code,200)
        data=r.get_json();self.assertFalse(data['approved'])
        self.assertTrue(c.post('/approve/'+data['id']).get_json()['approved'])
        self.assertEqual(c.get('/jobs/'+data['id']).status_code,200)
    def test_invalid_inputs(self):
        app=create_app();app.testing=True;c=app.test_client()
        for script in ['',42,'x'*12001]: self.assertEqual(c.post('/analyze',json={'script':script}).status_code,400)
        self.assertEqual(c.post('/approve/missing').status_code,404)
    def test_browser_boundary(self):
        for url in ['https://example.com/','http://127.0.0.1:5050/other']:
            with self.assertRaises(ValueError):submit_demo(None,url,'demo')
    def test_mock_structure(self):
        data=MockStoryboardAnalyzer().analyze('DEMO01',(Path(__file__).resolve().parents[1]/'examples/episode.txt').read_text())
        self.assertTrue(data['segments'])
