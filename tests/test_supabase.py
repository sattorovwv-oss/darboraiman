import io
import json
import os
import unittest
from unittest.mock import patch
from test_reviews import server

ROW={'id':1,'name':'Клиент','rating':5,'comment':'Отличная работа над проектом!','created_at':100}
CONFIG={'SUPABASE_URL':'https://example.supabase.co','SUPABASE_SECRET_KEY':'sb_secret_test-only'}

class SupabaseTests(unittest.TestCase):
    def test_server_headers_and_insert(self):
        with patch.dict(os.environ,CONFIG),patch.object(server.urllib.request,'urlopen',return_value=io.BytesIO(json.dumps([ROW]).encode())) as call:
            row=server.save_review(ROW['name'],5,ROW['comment'])
            self.assertEqual(row,ROW)
            request=call.call_args.args[0]
            self.assertEqual(request.method,'POST')
            self.assertEqual(request.get_header('Apikey'),'sb_secret_test-only')
            self.assertIsNone(request.get_header('Authorization'))
            self.assertEqual(json.loads(request.data)['rating'],5)

    def test_legacy_authorization(self):
        with patch.dict(os.environ,{**CONFIG,'SUPABASE_SECRET_KEY':'legacy-test'}),patch.object(server.urllib.request,'urlopen',return_value=io.BytesIO(b'[]')) as call:
            server.supabase_request('GET','select=id')
            self.assertEqual(call.call_args.args[0].get_header('Authorization'),'Bearer legacy-test')

    def test_pagination(self):
        with patch.dict(os.environ,CONFIG),patch.object(server,'supabase_request',side_effect=[[ROW]*100,[ROW]]) as call:
            self.assertEqual(len(server.list_reviews()),101)
            self.assertIn('offset=100',call.call_args.args[1])

    def test_partial_configuration_never_falls_back(self):
        with patch.dict(os.environ,{'SUPABASE_URL':CONFIG['SUPABASE_URL'],'SUPABASE_SECRET_KEY':''}),patch.object(server,'connect') as local:
            with self.assertRaises(server.StorageUnavailable):server.list_reviews()
            local.assert_not_called()

    def test_error_does_not_write_local(self):
        with patch.dict(os.environ,CONFIG),patch.object(server.urllib.request,'urlopen',side_effect=TimeoutError()),patch.object(server,'connect') as local:
            with self.assertRaises(server.StorageUnavailable):server.save_review('Клиент',5,'Отличная работа!')
            local.assert_not_called()

    def test_bad_urls_and_invalid_data(self):
        for url in ['http://example.supabase.co','https://evil.example','https://example.supabase.co/path']:
            with patch.dict(os.environ,{**CONFIG,'SUPABASE_URL':url}),self.assertRaises(server.StorageUnavailable):
                server.supabase_request('GET','')
        with patch.dict(os.environ,CONFIG),patch.object(server.urllib.request,'urlopen',return_value=io.BytesIO(b'{}')),self.assertRaises(server.StorageUnavailable):
            server.list_reviews()
