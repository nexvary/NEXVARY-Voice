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
    import ssl, httpx
    from voice_engine.phone_bridge import PhoneBridge
    manager = desktop_setup.EngineManager()
    bridge = None
    try:
        log(manager.start())
        assert manager.process is not None, 'CI must start its own loopback engine'
        bridge=PhoneBridge('127.0.0.1',allow_loopback=True).start()
        bridge.qr()
        tls=ssl.create_default_context(cafile=str(Path(bridge.temp.name)/'cert.pem'))
        with httpx.Client(verify=tls,trust_env=False) as pairing:
            assert pairing.get(bridge.endpoint+'/health').status_code==401
            token=pairing.post(bridge.endpoint+'/pair',json={'code':bridge.state.code}).json()['token']
        client = DesktopAPI(bridge.endpoint,token,transport=httpx.HTTPTransport(verify=tls))
        assert client.health()['status']=='ok'
        assert client.translate('Hello, this is a voice test.', 'en', 'ar').strip()
        srt = client.translate_srt('1\n00:00:00,000 --> 00:00:02,000\nHello\n','en','ar')
        assert '00:00:00,000 --> 00:00:02,000' in srt
        log('PASS: managed engine + GUI HTTP text and SRT clients')
        timings=[]
        for round_index in range(3):
            for source,target,text in [('ar','ru','مرحباً، هذا اختبار ترجمة قصير.'),('ru','ar','Здравствуйте, это короткий тест перевода.')]:
                started=time.monotonic()
                assert client.translate(text,source,target).strip()
                timings.append({'round':round_index+1,'source':source,'target':target,'seconds':round(time.monotonic()-started,3)})
        log('PERFORMANCE: actual bidirectional pivot request timings '+json.dumps(timings))
        raw = root/'samples'/'live-input.pcm'
        ffmpeg, ffprobe = desktop_setup.ffmpeg_pair(root)
        assert ffmpeg and ffprobe
        subprocess.run([str(ffmpeg),'-hide_banner','-loglevel','error','-nostdin','-y',
                        '-i',str(root/'samples'/'en.wav'),'-ac','1','-ar','16000',
                        '-f','s16le',str(raw)],check=True,timeout=30)
        pcm = raw.read_bytes()[:102400]
        with connect(bridge.endpoint.replace('https://','wss://')+'/v1/live/audio',ssl=tls,
                     additional_headers={'Authorization':'Bearer '+token},open_timeout=15,close_timeout=5) as ws:
            ws.send(json.dumps(dict(source_language='en',target_language='ar',format='pcm_s16le',sample_rate=16000)))
            for offset in range(0,len(pcm),32000): ws.send(pcm[offset:offset+32000])
            ws.send(json.dumps({'type':'flush'}))
            meta = json.loads(ws.recv(timeout=90))
            assert meta.get('translated_text'), meta
            assert set(meta['stage_seconds'])=={'asr','translation','tts','conversion'}
            log('PERFORMANCE: real live pipeline stage times '+json.dumps(meta['stage_seconds']))
            speech = ws.recv(timeout=90)
            assert isinstance(speech,bytes) and len(speech)>16000
            (root/'samples'/'live-translated.pcm').write_bytes(speech)
            # Exercise the short-turn flush protocol with the actual installed models.
            short_pcm = pcm[:96000]
            for offset in range(0,len(short_pcm),32000): ws.send(short_pcm[offset:offset+32000])
            ws.send(json.dumps({'type':'flush'}))
            short_meta = json.loads(ws.recv(timeout=90))
            assert short_meta.get('translated_text'), short_meta
            assert short_meta['chunk_seconds'] < 3.2
            assert isinstance(ws.recv(timeout=90),bytes)
            log('PASS: short-turn flush through real ASR/MT/TTS; '+json.dumps(short_meta['stage_seconds']))
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
        return {'state':'ready','transport':'real paired HTTPS and WSS relay through DesktopAPI','hardware_audio':False,'translation_turn_seconds':timings,'live_stage_seconds':meta['stage_seconds'],'short_turn_stage_seconds':short_meta['stage_seconds']}
    finally:
        if bridge: bridge.stop()
        log(manager.stop())

parser=argparse.ArgumentParser()
parser.add_argument('--stage',default='all',choices=['all','runtime','ffmpeg','translations','whisper','voices','whisper-test','video-test'])
args=parser.parse_args()
worker = SetupTask(args.stage)
worker.message.connect(log);worker.problem.connect(log)
worker.done.connect(results.append)
# Inject only the optional-link error AFTER the real downloader has extracted
# its interpreter. This exercises real Python/venv/packages with a simulated
# Windows policy failure, not a claim of reproducing the user's cloud driver.
recovered = []
if args.stage == 'runtime':
    original_execute = worker.execute
    def optional_link_failure(argv, label):
        original_execute(argv, label)
        if argv[1:3] == ['python', 'install']:
            recovered.append(True)
            raise desktop_setup.SetupCommandError(label, 2,
                'Failed to create Python minor version link directory (os error 448)')
    worker.execute = optional_link_failure
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
if args.stage == 'runtime' and results and results[-1]:
    assert recovered, 'Fresh private Python must exercise the injected link failure'
    # Healthy retry must return before executing any installer or redownloading.
    def unexpected_install(*args): raise AssertionError('Healthy runtime was reinstalled')
    worker.execute = unexpected_install
    worker.install_runtime()
    log('PASS: real extracted Python + copied venv + runtime imports after simulated 448; healthy retry installs nothing')
    (output/'runtime-recovery-results.json').write_text(json.dumps({
        'passed':True, 'error_injection':'simulated optional junction failure (448)',
        'python_venv_packages':'real Windows execution', 'healthy_retry':'no installation commands',
        'physical_windows_10_cloud_filter':'not reproduced'}, indent=2), encoding='utf-8')
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
