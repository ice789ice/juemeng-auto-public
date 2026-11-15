"""Local portfolio demonstration; no production service integration."""
import hashlib
from collections.abc import Mapping
from flask import Flask, request, jsonify
from .script.analyzers.mock import MockStoryboardAnalyzer

def create_app():
    app=Flask(__name__)
    app.config['MAX_CONTENT_LENGTH']=64000
    jobs={}
    @app.before_request
    def local_only():
        if request.host != '127.0.0.1:5050' and not app.testing:
            return jsonify(error='Use the loopback demo address'),403
        if request.method == 'POST' and request.headers.get('Origin') not in (None,'http://127.0.0.1:5050'):
            return jsonify(error='Cross-origin writes are disabled'),403
    @app.get('/')
    def index():
        return '<h1>Storyboard review demo</h1><p>Local mock analysis and human approval</p><form method="post" action="/analyze"><textarea name="script"></textarea><button>Analyze</button></form>'
    @app.post('/analyze')
    def analyze():
        payload=request.get_json(silent=True) if request.is_json else request.form
        if not isinstance(payload, Mapping):
            return jsonify(error='Expected an object'),400
        script=payload.get('script','')
        if not isinstance(script,str) or not script.strip() or len(script)>12000:
            return jsonify(error='Provide a script of 1 to 12000 characters'),400
        try: result=MockStoryboardAnalyzer().analyze('DEMO01',script)
        except ValueError: return jsonify(error='The mock analyzer requires English story lines'),400
        ident=hashlib.sha256(script.encode()).hexdigest()[:16]
        if ident not in jobs and len(jobs)>=100:
            return jsonify(error='Demo capacity reached; restart to clear drafts'),503
        jobs[ident]={'storyboard':result,'approved':False}
        return jsonify(id=ident,**jobs[ident])
    @app.post('/approve/<ident>')
    def approve(ident):
        if ident not in jobs: return jsonify(error='Unknown draft'),404
        jobs[ident]['approved']=True
        return jsonify(jobs[ident])
    @app.get('/jobs/<ident>')
    def job(ident):
        if ident not in jobs: return jsonify(error='Unknown draft'),404
        return jsonify(jobs[ident])
    return app

if __name__=='__main__':
    create_app().run(host='127.0.0.1',port=5050,debug=False)
