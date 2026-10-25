import importlib.util
import io
import json
import os
from pathlib import Path
import tempfile
import threading
import unittest
import urllib.request
import urllib.error
from unittest.mock import patch

TEMP = tempfile.TemporaryDirectory()
os.environ['REVIEWS_DB'] = TEMP.name + '/test.sqlite3'
spec = importlib.util.spec_from_file_location('portfolio_server', Path(__file__).resolve().parents[1] / 'server.py')
server = importlib.util.module_from_spec(spec)
spec.loader.exec_module(server)

class ModerationTests(unittest.TestCase):
    def response(self, approved=True, reason='ok'):
        return io.BytesIO(json.dumps({'status':'completed','output':[{'content':[{'type':'output_text','text':json.dumps({'approved':approved,'reason':reason})}]}]}).encode())

    def test_missing_key_fails_closed(self):
        with patch.dict(os.environ, {}, clear=True), self.assertRaises(server.ModerationUnavailable):
            server.moderate_review('Имя', 'Комментарий')

    def test_provider_decisions(self):
        with patch.dict(os.environ, {'MODERATION_API_KEY':'test-only'}):
            for approved, reason in [(True,'ok'),(False,'abuse'),(False,'spam')]:
                with patch.object(server.urllib.request,'urlopen',return_value=self.response(approved,reason)) as request:
                    self.assertEqual(server.moderate_review('Имя','Не понравился результат.'), {'approved':approved,'reason':reason})
                    payload=json.loads(request.call_args.args[0].data)
                    self.assertFalse(payload['store'])
                    self.assertEqual(json.loads(payload['input'])['comment'],'Не понравился результат.')

    def test_bad_provider_responses_and_timeout_fail_closed(self):
        with patch.dict(os.environ, {'MODERATION_API_KEY':'test-only'}):
            for body in [b'{}',b'invalid',b'{"status":"incomplete"}']:
                with patch.object(server.urllib.request,'urlopen',return_value=io.BytesIO(body)),self.assertRaises(server.ModerationUnavailable):
                    server.moderate_review('Имя','Комментарий')
            with patch.object(server.urllib.request,'urlopen',side_effect=TimeoutError()),self.assertRaises(server.ModerationUnavailable):
                server.moderate_review('Имя','Комментарий')

class APITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.http=server.ThreadingHTTPServer(('127.0.0.1',0),server.Handler)
        cls.thread=threading.Thread(target=cls.http.serve_forever,daemon=True);cls.thread.start()
        cls.url=f'http://127.0.0.1:{cls.http.server_port}/api/reviews'

    @classmethod
    def tearDownClass(cls):
        cls.http.shutdown();cls.http.server_close();cls.thread.join()

    def setUp(self):
        server.attempts.clear()
        with server.connect() as db:db.execute('DELETE FROM reviews')

    def post(self,rating=5):
        req=urllib.request.Request(self.url,data=json.dumps({'name':'Посетитель','rating':rating,'comment':'Мне не понравилось оформление.'}).encode(),headers={'Content-Type':'application/json'})
        try:
            with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(req) as response:return response.status,json.load(response)
        except urllib.error.HTTPError as response:return response.code,json.load(response)

    def count(self):
        with server.connect() as db:return db.execute('SELECT COUNT(*) FROM reviews').fetchone()[0]

    def test_approved_negative_review_published(self):
        with patch.dict(os.environ,{'MODERATION_API_KEY':'test-only'}),patch.object(server,'moderate_review',return_value={'approved':True,'reason':'ok'}):
            self.assertEqual(self.post(rating=1)[0],201)
            self.assertEqual(self.count(),1)
            self.assertEqual(self.post()[0],429)

    def test_rejected_reviews_never_saved(self):
        for reason in ['abuse','spam']:
            server.attempts.clear()
            with patch.dict(os.environ,{'MODERATION_API_KEY':'test-only'}),patch.object(server,'moderate_review',return_value={'approved':False,'reason':reason}):
                self.assertEqual(self.post()[0],422)
                self.assertEqual(self.count(),0)

    def test_provider_outage_never_saves(self):
        with patch.dict(os.environ,{'MODERATION_API_KEY':'test-only'}),patch.object(server,'moderate_review',side_effect=server.ModerationUnavailable):
            self.assertEqual(self.post()[0],503)
            self.assertEqual(self.count(),0)

    def test_missing_key_and_invalid_rating(self):
        with patch.dict(os.environ,{},clear=True):
            self.assertEqual(self.post()[0],503)
            self.assertEqual(self.count(),0)
            self.assertEqual(self.post(rating=6)[0],400)

if __name__=='__main__':unittest.main()
