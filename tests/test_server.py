import json
import re
import subprocess
import sys
import tempfile
import unittest
import urllib.error
import urllib.request
from pathlib import Path


class HTTPTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory()
        code='import dj_intake.server as server; server.identify=lambda: "Avicii - Levels"; from dj_intake.server import start; from dj_intake.core import Worker; Worker.run=lambda self:None; import sys; start(sys.argv[1],0,False)'
        cls.proc=subprocess.Popen([sys.executable,'-c',code,cls.tmp.name],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
        cls.url=cls.proc.stdout.readline().strip().split('DJ Intake: ')[-1]
        if not cls.url.startswith('http://127.0.0.1:'):
            raise RuntimeError('Test server failed to start')
        cls.html=urllib.request.urlopen(cls.url,timeout=5).read().decode()
        cls.token=re.search(r'name="intake-token" content="([^"]+)"',cls.html)[1]

    @classmethod
    def tearDownClass(cls):
        cls.proc.terminate();cls.proc.communicate(timeout=5);cls.tmp.cleanup()

    def request(self,path,body=None,headers=None):
        headers={'X-Intake-Token':self.token,'Content-Type':'application/json',**(headers or {})}
        req=urllib.request.Request(self.url+path,data=None if body is None else json.dumps(body).encode(),headers=headers)
        return json.load(urllib.request.urlopen(req,timeout=5))

    def test_token_host_and_origin_checks(self):
        for headers in [{'X-Intake-Token':''},{'Host':'attacker.example'},{'Origin':'https://attacker.example'}]:
            with self.subTest(headers=headers),self.assertRaises(urllib.error.HTTPError) as ctx:
                self.request('/api/jobs',{'input':'Test track'},headers)
            self.assertEqual(ctx.exception.code,403)

    def test_identified_song_is_saved_once_without_queuing_a_download(self):
        before = len(self.request('/api/state')['jobs'])
        for _ in range(2):
            self.assertEqual(self.request('/api/identify', {})['name'], 'Avicii - Levels')
        state = self.request('/api/state')
        self.assertEqual([row['name'] for row in state['finds']], ['Avicii - Levels'])
        self.assertEqual(len(state['jobs']), before)

    def test_saved_find_edit_search_and_direct_download(self):
        match = self.request('/api/identify', {})
        identity = match['identity']
        self.request('/api/finds/rename', {'identity':identity,'name':'Avicii - Levels (Club Edit)'})
        try:
            self.assertEqual(self.request('/api/identify', {})['name'], 'Avicii - Levels (Club Edit)')
            with self.assertRaises(urllib.error.HTTPError) as ctx:
                self.request('/api/finds/download', {'identity':identity,'url':'https://127.0.0.1/private'})
            self.assertEqual(ctx.exception.code, 400)
            search = self.request('/api/finds/search', {'identity':identity})
            self.assertEqual((search['source'], search['url'], search['find_identity']),
                             ('Search', 'Avicii - Levels (Club Edit)', identity))
            with self.assertRaises(urllib.error.HTTPError) as ctx:
                self.request('/api/finds/search', {'identity':identity})
            self.assertEqual(ctx.exception.code, 400)
            # Resolve the search deterministically without hitting a streaming service.
            from dj_intake.core import Store, Worker
            from unittest.mock import patch
            worker = Worker(Store(self.tmp.name))
            with patch.object(worker, 'metadata', return_value={'entries':[{'id':'BaW_jenozKc','title':'A club version'}]}):
                worker.process(search)
            selected = json.loads(worker.store.get(search['id'])['candidates'])[0]['url']
            self.request('/api/choose', {'id':search['id'],'url':selected})
            self.assertEqual(worker.store.get(search['id'])['source'], 'YouTube')
            worker.store.update(search['id'], status='successful')
            direct = self.request('/api/finds/download', {'identity':identity,'url':'https://soundcloud.com/artist/track'})
            self.assertEqual((direct['source'], direct['status'], direct['find_identity']), ('SoundCloud','queued',identity))
        finally:
            self.request('/api/finds/rename', {'identity':identity,'name':'Avicii - Levels'})

    def test_delete_find_cancels_its_search_and_undo_restores_it(self):
        server_identify = self.request('/api/identify', {})  # Avicii - Levels (shared fixture)
        identity = server_identify['identity']
        self.request('/api/finds/rename', {'identity':identity,'name':'Avicii - Levels (Edit)'})
        search = self.request('/api/finds/search', {'identity':identity})
        deleted = self.request('/api/finds/delete', {'identity':identity})
        self.assertEqual(deleted['name'], 'Avicii - Levels (Edit)')
        state = self.request('/api/state')
        self.assertNotIn(identity, [row['identity'] for row in state['finds']])
        self.assertEqual(next(j for j in state['jobs'] if j['id']==search['id'])['status'], 'cancelled')
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            self.request('/api/finds/delete', {'identity':identity})
        self.assertEqual(ctx.exception.code, 400)
        restored = self.request('/api/finds/restore', {'identity':identity,'name':deleted['name'],'found_at':deleted['found_at']})
        self.assertEqual((restored['identity'], restored['name'], restored['found_at']), (identity, 'Avicii - Levels (Edit)', deleted['found_at']))
        self.request('/api/finds/rename', {'identity':identity,'name':'Avicii - Levels'})

    def test_mixed_batch_keeps_errors_and_valid_requests(self):
        result=self.request('/api/jobs',{'input':'Artist - Track\nhttps://127.0.0.1/private'})
        self.assertEqual(len(result['added']),1)
        self.assertEqual(len(result['errors']),1)
        state=self.request('/api/state')
        self.assertTrue(any(j['input']=='Artist - Track' for j in state['jobs']))

    def test_clip_request_roundtrips_and_invalid_range_is_rejected(self):
        result=self.request('/api/jobs',{'input':'Clip track','clip_start':'00:50','clip_end':'02:30'})
        self.assertEqual(result['added'][0]['clip_start'],50)
        self.assertEqual(result['added'][0]['clip_end'],150)
        invalid=self.request('/api/jobs',{'input':'Invalid clip','clip_start':'2:30','clip_end':'00:50'})
        self.assertEqual(invalid['added'],[])
        self.assertEqual(len(invalid['errors']),1)

    def test_mutations_reject_non_json_and_non_object_bodies(self):
        for body, headers, expected in [
            ({'input':'Track'}, {'Content-Type':'text/plain'}, 415),
            (['not an object'], {}, 400),
            ({'input':42}, {}, 400),
        ]:
            with self.subTest(body=body), self.assertRaises(urllib.error.HTTPError) as ctx:
                self.request('/api/jobs', body, headers)
            self.assertEqual(ctx.exception.code, expected)

    def test_settings_and_invalid_actions(self):
        self.request('/api/settings',{'profile':'original','output_dir':str(Path(self.tmp.name)/'ready')})
        self.assertEqual(self.request('/api/state')['settings']['profile'],'original')
        self.assertEqual(self.request('/api/settings')['output_dir'],str((Path(self.tmp.name)/'ready').resolve()))
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            self.request('/api/choose',{'id':'missing','url':'https://youtu.be/BaW_jenozKc'})
        self.assertEqual(ctx.exception.code,400)

    def test_quick_add_uses_authenticated_queue_and_hidden_optional_times(self):
        page=urllib.request.urlopen(self.url+'/quick',timeout=5).read().decode()
        self.assertIn('content="'+self.token+'"',page)
        self.assertIn('id="quick-trim" type="checkbox"',page)
        self.assertIn('id="quick-fields" hidden',page)
        script=urllib.request.urlopen(self.url+'/quick.js',timeout=5).read().decode()
        self.assertNotIn('innerHTML',script)

    def test_frontend_is_local_and_html_injection_not_used(self):
        self.assertNotIn('__TOKEN__',self.html)
        self.assertIn('DJ Intake',self.html)
        js=urllib.request.urlopen(self.url+'/app.js',timeout=5).read().decode()
        self.assertNotIn('innerHTML',js)

if __name__=='__main__':unittest.main()
