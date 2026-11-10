from __future__ import annotations
import argparse
import fcntl
import json
import os
import secrets
import subprocess
import sys
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse
from .core import ROOT, Store, Worker, tool
from .recognition import identify, open_setup
from .updates import VERSION, UpdateChecker, installed_copy, latest_release, start_install


class Server(ThreadingHTTPServer):
    daemon_threads = True

    def get_request(self):
        connection, address = super().get_request()
        connection.settimeout(15)
        return connection, address


def start(home, port=8765, browser=True):
    home = Path(home).expanduser()
    home.mkdir(parents=True,exist_ok=True)
    lock = (home/'app.lock').open('w')
    try:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    except BlockingIOError:
        url = (home/'app-url.txt').read_text().strip()
        if browser:
            webbrowser.open(url)
        print('Already running: '+url)
        return
    store = Store(home)
    token = secrets.token_urlsafe(32)
    folder_picker = threading.Lock()
    recognition = threading.Lock()
    # Looked up through this module so tests can replace latest_release.
    updates = UpdateChecker(fetch=lambda: latest_release())
    can_update = installed_copy(ROOT)
    update_enabled = lambda: store.setting('update_check', 'on') == 'on'

    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):
            pass

        def reply(self,code,value):
            blob = json.dumps(value,ensure_ascii=False).encode()
            self.send_response(code)
            self.send_header('Content-Type','application/json; charset=utf-8')
            self.send_header('Content-Length',str(len(blob)))
            self.send_header('Cache-Control','no-store')
            self.send_header('X-Content-Type-Options','nosniff')
            self.end_headers(); self.wfile.write(blob)

        def valid_host(self):
            return self.headers.get('Host') in {f'127.0.0.1:{self.server.server_port}',f'localhost:{self.server.server_port}'}

        def authorized(self):
            return self.valid_host() and secrets.compare_digest(self.headers.get('X-Intake-Token',''),token)

        def do_GET(self):
            if not self.valid_host():
                return self.reply(403,{'error':'Local access only.'})
            path = urlparse(self.path).path
            if path.startswith('/api/'):
                if not self.authorized():
                    return self.reply(403,{'error':'Reopen DJ Intake to reconnect.'})
                if path == '/api/settings':
                    return self.reply(200, {'output_dir': store.setting('output_dir', str(Path.home()/'Music/DJ Intake Staging'))})
                if path == '/api/state':
                    return self.reply(200,{'jobs':store.jobs(),'finds':store.finds(),'settings':{'output_dir':store.setting('output_dir',str(Path.home()/'Music/DJ Intake Staging')),'profile':store.setting('profile','mp3')},'tools':{n:bool(tool(n)) for n in ('yt-dlp','ffmpeg','ffprobe')},'version':VERSION,
                        'update':updates.status(update_enabled()),'can_update':can_update,'update_check':update_enabled()})
                return self.reply(404,{'error':'Not found'})
            assets = {'/':'index.html','/style.css':'style.css','/app.js':'app.js','/app-icon.png':'app-icon.png','/quick':'quick.html','/quick.js':'quick.js','/hero.jpg':'hero.jpg','/fonts/Geist.woff2':'fonts/Geist.woff2','/fonts/GeistMono.woff2':'fonts/GeistMono.woff2','/recognition-setup':'RECOGNITION.md'}
            if path not in assets:
                return self.reply(404,{'error':'Not found'})
            file = ROOT/'assets/app-icon.png' if path == '/app-icon.png' else ROOT/'dj_intake/static'/assets[path]
            if path == '/recognition-setup':
                file = ROOT/'RECOGNITION.md'
            if not file.is_file():
                return self.reply(404,{'error':'Not found'})
            blob = file.read_bytes()
            if path in ('/', '/quick'):
                blob = blob.replace(b'__TOKEN__',token.encode())
            self.send_response(200)
            self.send_header('Content-Type',{'/':'text/html; charset=utf-8','/style.css':'text/css','/app.js':'text/javascript','/app-icon.png':'image/png','/quick':'text/html; charset=utf-8','/quick.js':'text/javascript','/hero.jpg':'image/jpeg','/fonts/Geist.woff2':'font/woff2','/fonts/GeistMono.woff2':'font/woff2','/recognition-setup':'text/plain; charset=utf-8'}[path])
            self.send_header('Content-Length',str(len(blob)))
            self.send_header('Cache-Control','no-store')
            self.send_header('X-Frame-Options','DENY')
            self.send_header('Content-Security-Policy',"default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
            self.end_headers(); self.wfile.write(blob)

        def do_POST(self):
            if not self.authorized():
                return self.reply(403,{'error':'Reopen DJ Intake to reconnect.'})
            origin = self.headers.get('Origin')
            if origin and origin not in {f'http://127.0.0.1:{self.server.server_port}',f'http://localhost:{self.server.server_port}'}:
                return self.reply(403,{'error':'Local access only.'})
            try:
                if self.headers.get_content_type() != 'application/json':
                    return self.reply(415, {'error':'Send a JSON request.'})
                length = int(self.headers.get('Content-Length','0'))
                if not 0 < length <= 20000:
                    raise ValueError('Request too large or empty.')
                body = json.loads(self.rfile.read(length))
                if not isinstance(body, dict):
                    raise ValueError('Expected a JSON object.')
                path = urlparse(self.path).path
                if path == '/api/jobs':
                    value = body.get('input','')
                    if not isinstance(value, str):
                        raise ValueError('Enter a URL or song name.')
                    lines = value.splitlines()
                    if not 1 <= len(lines) <= 50:
                        raise ValueError('Add up to 50 requests at a time.')
                    added,errors = [],[]
                    for line in lines:
                        if line.strip():
                            try:
                                added.append(store.add(line, body.get('clip_start',''), body.get('clip_end','')))
                            except ValueError as exc:
                                errors.append({'input':line,'error':str(exc)})
                    return self.reply(200,{'added':added,'errors':errors})
                if path == '/api/identify':
                    if not recognition.acquire(blocking=False):
                        raise ValueError('Already listening for a song.')
                    try:
                        match = store.remember_find(identify())
                    finally:
                        recognition.release()
                    return self.reply(200, match)
                if path == '/api/recognition/setup':
                    return self.reply(200, {'installed': open_setup()})
                if path == '/api/retry':
                    store.retry(body['id'])
                elif path == '/api/finds/rename':
                    store.rename_find(body['identity'], body['name'])
                elif path == '/api/finds/delete':
                    return self.reply(200, store.delete_find(body['identity']))
                elif path == '/api/finds/restore':
                    return self.reply(200, store.restore_find(body.get('identity'), body.get('name'), body.get('found_at')))
                elif path == '/api/finds/search':
                    return self.reply(200, store.request_find(body['identity']))
                elif path == '/api/finds/download':
                    if not isinstance(body.get('url'), str):
                        raise ValueError('Paste a track link.')
                    return self.reply(200, store.request_find(body['identity'], body['url']))
                elif path == '/api/choose':
                    store.choose(body['id'],body['url'])
                elif path == '/api/settings':
                    store.save_settings(body)
                    if 'update_check' in body:
                        store.set_setting('update_check', 'on' if body['update_check'] is True else 'off')
                elif path == '/api/update/check':
                    updates.refresh(force=True)
                    return self.reply(200, {'update': updates.status(update_enabled())})
                elif path == '/api/update/install':
                    if not can_update:
                        raise ValueError('This copy wasn’t installed with the DJ Intake installer. Update it with git instead.')
                    if any(job['status'] in ('queued','resolving','downloading','processing') for job in store.jobs()):
                        raise ValueError('Let the current downloads finish, then update.')
                    start_install(ROOT)
                    threading.Timer(.5, self.server.shutdown).start()
                elif path == '/api/pick-folder':
                    if sys.platform != 'darwin':
                        raise ValueError('The folder picker is available on macOS.')
                    current = store.setting('output_dir', str(Path.home()/'Music/DJ Intake Staging'))
                    helper = ROOT/'outputs/DJ Intake.app/Contents/MacOS/DJIntake'
                    if helper.is_file():
                        command = [str(helper), '--choose-folder', current]
                    else:
                        command = ['/usr/bin/osascript', '-e', 'POSIX path of (choose folder with prompt "Choose the default DJ Intake download folder")']
                    if not folder_picker.acquire(blocking=False):
                        raise ValueError('The folder picker is already open.')
                    try:
                        result = subprocess.run(command, capture_output=True, text=True, timeout=180)
                    finally:
                        folder_picker.release()
                    if result.returncode:
                        if result.returncode == 2 or '(-128)' in result.stderr:
                            return self.reply(200, {'cancelled': True})
                        raise ValueError('Could not open the folder picker. Enter a folder path in the library settings.')
                    return self.reply(200, {'output_dir': store.set_output_dir(result.stdout.rstrip('\n'))})
                elif path == '/api/reveal':
                    row = store.get(body['id'])
                    if row['status'] != 'successful' or not row.get('output') or not Path(row['output']).is_file():
                        raise ValueError('The output file is missing. Check its staging folder.')
                    if sys.platform == 'darwin':
                        subprocess.Popen(['open','-R',row['output']])
                    else:
                        raise ValueError('Show in Finder is available on macOS.')
                elif path == '/api/quit':
                    threading.Timer(.3,self.server.shutdown).start()
                elif path == '/api/folder':
                    folder = Path(store.setting('output_dir',str(Path.home()/'Music/DJ Intake Staging')))
                    folder.mkdir(parents=True,exist_ok=True)
                    subprocess.Popen(['open',str(folder)])
                else:
                    return self.reply(404,{'error':'Not found'})
                return self.reply(200,{'ok':True})
            except (ValueError,KeyError,TypeError) as exc:
                return self.reply(400,{'error':str(exc)})
            except Exception:
                return self.reply(500,{'error':'The action failed. Check the app log.'})

    server = Server(('127.0.0.1',port),Handler)
    url = f'http://127.0.0.1:{server.server_port}'
    (home/'app-url.txt').write_text(url)
    worker = Worker(store)
    threading.Thread(target=worker.run,daemon=True).start()
    print('DJ Intake: '+url,flush=True)
    if browser:
        threading.Timer(.5,lambda:webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        worker.stop.set()
        server.server_close()
        lock.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--home',default=os.environ.get('DJ_INTAKE_HOME',str(Path.home()/'Library/Application Support/DJ Intake')))
    parser.add_argument('--port',type=int,default=8765)
    parser.add_argument('--no-browser',action='store_true')
    args = parser.parse_args()
    start(args.home,args.port,not args.no_browser)


if __name__ == '__main__':
    main()
