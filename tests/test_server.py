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
        code='from dj_intake.server import start; from dj_intake.core import Worker; Worker.run=lambda self:None; import sys; start(sys.argv[1],0,False)'
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
