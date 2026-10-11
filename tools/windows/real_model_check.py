"""CI explicitly opts into heavy downloads. Exercises the real GUI setup worker.

Not a claim of microphone/speaker hardware or translation semantic accuracy.
"""
import argparse
import json
import os
import shutil
import sys
import subprocess
import time
from pathlib import Path
import uv
from PySide6.QtCore import QCoreApplication
from voice_engine import desktop_setup
from voice_engine.setup_wizard import SetupTask

root = Path(os.environ.get('RUNNER_TEMP',Path.cwd()/'build'))/'voice-setup-اختبار'
root.mkdir(parents=True,exist_ok=True)
# Same isolated runtime installer, but CI locates uv from the installed package.
desktop_setup.home = lambda: root
desktop_setup.uv_path = lambda: Path(uv.find_uv_bin())
# Prove setup without any reusable system Python; uv installs its own runtime.
desktop_setup.existing_system_python = lambda: None
app = QCoreApplication([])
output = Path('build');output.mkdir(exist_ok=True)
log_path = output/'real-model-log.txt'
results = []

def log(message):
    print(message,flush=True)
    with log_path.open('a',encoding='utf-8') as out: out.write(message+'\n')

def check_managed_client():
    """Real GUI client transport and owned engine; generated audio, no hardware."""
    from voice_engine.desktop_api import DesktopAPI
    from websockets.sync.client import connect
    manager = desktop_setup.EngineManager()
    try:
        log(manager.start())
        assert manager.process is not None, 'CI must start its own loopback engine'
        client = DesktopAPI('http://127.0.0.1:8000')
        assert client.health()['status']=='ok'
        assert client.translate('Hello, this is a voice test.', 'en', 'ar').strip()
        srt = client.translate_srt('1\n00:00:00,000 --> 00:00:02,000\nHello\n','en','ar')
        assert '00:00:00,000 --> 00:00:02,000' in srt
        log('PASS: managed engine + GUI HTTP text and SRT clients')
        raw = root/'samples'/'live-input.pcm'
        ffmpeg, ffprobe = desktop_setup.ffmpeg_pair(root)
        assert ffmpeg and ffprobe
        subprocess.run([str(ffmpeg),'-hide_banner','-loglevel','error','-nostdin','-y',
                        '-i',str(root/'samples'/'en.wav'),'-ac','1','-ar','16000',
                        '-f','s16le',str(raw)],check=True,timeout=30)
        pcm = raw.read_bytes()[:102400]
        with connect('ws://127.0.0.1:8000/v1/live/audio',open_timeout=15,close_timeout=5) as ws:
            ws.send(json.dumps(dict(source_language='en',target_language='ar',format='pcm_s16le',sample_rate=16000)))
            for offset in range(0,len(pcm),32000): ws.send(pcm[offset:offset+32000])
            ws.send(json.dumps({'type':'flush'}))
            meta = json.loads(ws.recv(timeout=90))
            assert meta.get('translated_text'), meta
            speech = ws.recv(timeout=90)
            assert isinstance(speech,bytes) and len(speech)>16000
            (root/'samples'/'live-translated.pcm').write_bytes(speech)
            ws.send(json.dumps({'type':'stop'}))
        log('PASS: GUI WebSocket transport → Whisper → Argos → Piper → PCM; no physical microphone/speaker')
        job = client.submit_video(root/'validation-video'/'input.mp4','en','ar')
        deadline = time.monotonic()+180
        while time.monotonic()<deadline:
            state = client.video_status(job['job_id'])
            if state['status']=='complete': break
            if state['status'] in ('failed','cancelled'): raise RuntimeError(str(state))
            time.sleep(0.5)
        else: raise TimeoutError('GUI video API validation exceeded 180s')
        target = root/'validation-video'/'gui-client-dubbed.mp4'
        target.unlink(missing_ok=True);target.with_suffix('.srt').unlink(missing_ok=True)
        client.download_video(job['job_id'],target)
        client.download_subtitles(job['job_id'],target.with_suffix('.srt'))
        inspected = subprocess.run([str(ffprobe),'-v','error','-show_streams','-of','json',str(target)],capture_output=True,text=True,check=True,timeout=30)
        assert {'audio','video'}<={v['codec_type'] for v in json.loads(inspected.stdout)['streams']}
        assert target.with_suffix('.srt').read_text(encoding='utf-8').strip()
        from voice_engine.subtitles import translate_srt
        class Identity:
            def translate(self,text,source,target):return text
        # Parsing validates real downloaded cue structure, not just file size.
        translate_srt(target.with_suffix('.srt').read_text(encoding='utf-8-sig'),'ar','en',Identity())
        log('PASS: GUI video submit, progress polling, MP4 and SRT download; verified both media streams')
        manager.restart();assert manager.health()
        return {'state':'ready','transport':'real HTTP and WebSocket through DesktopAPI','hardware_audio':False}
    finally:
        log(manager.stop())

parser=argparse.ArgumentParser()
parser.add_argument('--stage',default='all',choices=['all','runtime','ffmpeg','translations','whisper','voices','whisper-test','video-test'])
args=parser.parse_args()
worker = SetupTask(args.stage)
worker.message.connect(log);worker.problem.connect(log)
worker.done.connect(results.append)
if args.stage.endswith('-test'):
    try:
        worker.verify(args.stage.split('-')[0])
        if args.stage=='video-test':
            client_result = check_managed_client()
            functional_path=root/'functional-tests.json'
            data=json.loads(functional_path.read_text(encoding='utf-8'))
            data['managed_client']={'checked_at':time.time(),'passed':True,'data':client_result}
            functional_path.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
        results.append(True)
    except Exception as exc:
        log(str(exc));results.append(False)
else: worker.run()
state = desktop_setup.detect()
functional = root/'functional-tests.json'
report = {'stage':args.stage,'setup_passed':bool(results and results[-1]),'diagnostics':state,
          'kind':'real Windows CPU INT8 model inference; no hardware audio',
          'functional_tests':json.loads(functional.read_text(encoding='utf-8')) if functional.exists() else {}}
(output/'real-model-results.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
evidence = output/'real-model-evidence';evidence.mkdir(exist_ok=True)
for directory in ('samples','validation-video'):
    if (root/directory).exists(): shutil.copytree(root/directory,evidence/directory,dirs_exist_ok=True)
# Re-scan without downloads; repeated healthy voice downloads are verified/skipped
# by the downloader unit tests. This job proves model inference only.
raise SystemExit(0 if report['setup_passed'] else 1)
