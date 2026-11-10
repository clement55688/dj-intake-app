#!/usr/bin/env python3
"""Apply artist_song names to this app's existing staging files while stopped."""
import argparse
import fcntl
import json
import sqlite3
import sys
import time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from dj_intake.core import Store, digest, publish_file, tidy_track, job_stem


def migrate(store):
    folder=Path(store.setting('output_dir',str(Path.home()/'Music/DJ Intake Staging'))).expanduser().resolve()
    journal=store.home/'rename-history.jsonl'
    seen=set()
    results=[]
    backup=store.home/('queue-before-rename-'+str(time.time_ns())+'.sqlite3')
    with store.connect() as source, sqlite3.connect(backup) as destination:
        source.backup(destination)
    for job in store.jobs():
        previous=job.get('output')
        if job['status']!='successful' or not previous or previous in seen:
            continue
        seen.add(previous)
        old=Path(previous)
        if old.parent.resolve()!=folder or not old.is_file():
            continue
        if job.get('output_hash') and digest(old)!=job['output_hash']:
            raise RuntimeError('File changed since delivery; left unchanged: '+str(old))
        artist,title=tidy_track(job['artist'],job['title'])
        if old.stem==job_stem(artist,title,job):
            continue
        output=publish_file(old,folder,job_stem(artist,title,job),old.suffix)
        event={'old':str(old),'new':str(output),'sha256':digest(output),'time':time.time()}
        with journal.open('a') as stream:
            stream.write(json.dumps(event,ensure_ascii=False)+'\n')
        with store.connect() as connection:
            connection.execute('UPDATE jobs SET output=?,title=?,artist=?,updated=? WHERE output=?',(str(output),title,artist,time.time(),previous))
        # Update result manifests for every request referencing this file.
        for sibling in store.jobs():
            if sibling.get('output')!=str(output):continue
            manifest=store.home/'jobs'/sibling['id']/'result.json'
            if manifest.exists():
                data=json.loads(manifest.read_text())
                data.update(output=str(output),title=title,artist=artist)
                temporary=manifest.with_suffix('.tmp')
                temporary.write_text(json.dumps(data,indent=2,ensure_ascii=False))
                temporary.replace(manifest)
        if old!=output:old.unlink()
        results.append(event)
    return results


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--home',type=Path,default=Path.home()/'Library/Application Support/DJ Intake')
    args=parser.parse_args()
    args.home.mkdir(parents=True,exist_ok=True)
    with (args.home/'app.lock').open('w') as lock:
        try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:raise SystemExit('Quit DJ Intake before renaming its staged files.')
        for event in migrate(Store(args.home)):
            print(Path(event['old']).name+' -> '+Path(event['new']).name)


if __name__=='__main__':main()
