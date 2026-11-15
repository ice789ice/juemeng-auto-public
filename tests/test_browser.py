import json
import threading
import unittest
from pathlib import Path
from werkzeug.serving import make_server
from playwright.sync_api import sync_playwright
from juemeng_auto.demo import create_app
from juemeng_auto.browser_demo import submit_demo

class BrowserTests(unittest.TestCase):
    def test_local_browser_review_flow(self):
        server=make_server('127.0.0.1',5050,create_app())
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            with sync_playwright() as pw:
                browser=pw.chromium.launch(headless=True)
                try:
                    context=browser.new_context(service_workers='block')
                    blocked=[]
                    def guard(route):
                        from urllib.parse import urlsplit
                        u=urlsplit(route.request.url)
                        if (u.scheme,u.hostname,u.port)==('http','127.0.0.1',5050): route.continue_()
                        else: blocked.append(route.request.url);route.abort()
                    context.route('**/*',guard)
                    page=context.new_page()
                    script=(Path(__file__).resolve().parents[1]/'examples/episode.txt').read_text(encoding='utf-8')
                    result=json.loads(submit_demo(page,'http://127.0.0.1:5050/',script))
                    self.assertFalse(result['approved'])
                    approved=page.evaluate("async id => (await fetch('/approve/'+id,{method:'POST'})).json()",result['id'])
                    self.assertTrue(approved['approved'])
                    page.goto('http://127.0.0.1:5050/jobs/'+result['id'])
                    self.assertTrue(json.loads(page.locator('body').inner_text())['approved'])
                    self.assertFalse(blocked)
                finally: browser.close()
        finally: server.shutdown();thread.join(timeout=5);server.server_close()
