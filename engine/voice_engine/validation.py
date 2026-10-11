"""Opt-in functional checks in the managed runtime; never downloads a model.

A non-empty translation proves execution, not semantic translation quality.
Audio samples are real Piper speech; speaker audibility requires user listening.
"""
from __future__ import annotations
import argparse
import json
import os
import time
import wave
from pathlib import Path

SAMPLES = {
    'ar': 'مرحبًا، هذا اختبار ترجمة الصوت.',
    'en': 'Hello, this is a voice translation test.',
    'it': 'Ciao, questa è una prova di traduzione vocale.',
    'ru': 'Здравствуйте, это тест голосового перевода.',
    'es': 'Hola, esta es una prueba de traducción de voz.',
    'bn': 'হ্যালো, এটি একটি ভয়েস অনুবাদ পরীক্ষা।',
}


def valid_wav(path: Path) -> bool:
    try:
        with wave.open(str(path), 'rb') as audio:
            return audio.getnframes() > 0 and audio.getframerate() > 0 and audio.getsampwidth() == 2
    except (OSError, EOFError, wave.Error): return False


def check_translations(log=print) -> dict:
    from .translator import ArgosTranslator
    translator = ArgosTranslator()
    results = {}
    for source, text in SAMPLES.items():
        for target in SAMPLES:
            if source == target: continue
            start = time.monotonic()
            try:
                value = translator.translate(text, source, target)
                results[source + '->' + target] = {'state': 'ready', 'elapsed_seconds': round(time.monotonic()-start, 3), 'result': value}
                log('PASS: ' + source + ' → ' + target)
            except Exception as exc:
                results[source + '->' + target] = {'state': 'failed', 'reason': str(exc)[:1400]}
                log('FAILED: ' + source + ' → ' + target + ': ' + str(exc)[:1000])
    return results


def check_voices(root: Path, log=print) -> dict:
    from .speech import PiperTTS
    mapping = json.loads((root / 'voices.json').read_text(encoding='utf-8'))
    tts = PiperTTS(mapping)
    folder = root / 'samples'
    folder.mkdir(parents=True, exist_ok=True)
    results = {}
    for code, text in SAMPLES.items():
        output = folder / (code + '.wav')
        stage = folder / (code + '.checking.wav')
        start = time.monotonic()
        try:
            tts.synthesize(text, code, stage)
            if not valid_wav(stage): raise RuntimeError('Invalid generated WAV')
            stage.replace(output)
            results[code] = {'state': 'ready', 'sample': str(output), 'elapsed_seconds': round(time.monotonic()-start, 3)}
            log('PASS: Piper ' + code + ' → WAV')
        except Exception as exc:
            results[code] = {'state': 'failed', 'reason': str(exc)[:1400]}
            log('FAILED: Piper ' + code + ': ' + str(exc)[:1400])
        finally: stage.unlink(missing_ok=True)
    return results


def check_whisper(root: Path, log=print) -> dict:
    from .speech import WhisperASR
    model = os.getenv('NEXVARY_WHISPER_MODEL', 'base')
    start = time.monotonic()
    asr = WhisperASR(model, allow_download=False)
    sample = root / 'samples' / 'en.wav'
    if not valid_wav(sample):
        return {'state': 'unverified', 'reason': 'Whisper loaded; run voice validation first to obtain speech input.'}
    decoded = asr.transcribe(sample, 'en')
    text = ' '.join(s.text for s in decoded).strip()
    if not text: raise RuntimeError('Whisper did not recognize generated speech')
    elapsed = time.monotonic()-start
    with wave.open(str(sample)) as audio: duration = audio.getnframes()/audio.getframerate()
    log(f'PASS: Whisper {model}; {elapsed:.2f}s; recognized speech')
    return {'state': 'ready', 'model': model, 'elapsed_seconds': round(elapsed, 3),
            'audio_seconds': round(duration, 3), 'real_time_factor_including_load': round(elapsed/duration, 3), 'text': text}


def check_video(root: Path, log=print) -> dict:
    from .speech import run_checked, WhisperASR, PiperTTS
    from .translator import ArgosTranslator
    from .dubbing import dub_video, probe_streams
    folder = root / 'validation-video'
    folder.mkdir(parents=True, exist_ok=True)
    source, output = folder / 'input.mp4', folder / 'dubbed.mp4'
    # Only overwrite application-owned test fixtures.
    source.unlink(missing_ok=True); output.unlink(missing_ok=True); output.with_suffix('.srt').unlink(missing_ok=True)
    sample = root / 'samples' / 'en.wav'
    if not valid_wav(sample): raise RuntimeError('Run voice validation first')
    run_checked(['ffmpeg','-hide_banner','-loglevel','error','-nostdin','-y','-f','lavfi','-i',
                 'color=c=black:s=320x180:r=15', '-i',str(sample),'-c:v','mpeg4','-c:a','aac','-shortest',str(source)])
    result = dub_video(source, output, 'en', 'ar', WhisperASR(os.getenv('NEXVARY_WHISPER_MODEL','base')),
                      ArgosTranslator(), PiperTTS())
    probe_streams(output)
    log('PASS: MP4 → Whisper → Argos → Piper → dubbed MP4 + SRT')
    return {'state':'ready', **result}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('stage', choices=['translations','voices','whisper','video','all'])
    args = parser.parse_args()
    root = Path.cwd()
    report_path = root / 'functional-tests.json'
    try: results = json.loads(report_path.read_text(encoding='utf-8'))
    except (OSError, ValueError): results = {}
    failed = False
    stages = ['translations','voices','whisper','video'] if args.stage == 'all' else [args.stage]
    for stage in stages:
        try:
            data = {'translations': lambda:check_translations(lambda s:print(s,flush=True)),
                    'voices':lambda:check_voices(root, lambda s:print(s,flush=True)),
                    'whisper':lambda:check_whisper(root), 'video':lambda:check_video(root)}[stage]()
            states = [data] if 'state' in data else list(data.values())
            okay = bool(states) and all(v['state'] == 'ready' for v in states)
            results[stage] = {'checked_at':time.time(), 'data':data, 'passed':okay}
            failed = failed or not okay
        except Exception as exc:
            results[stage] = {'checked_at':time.time(), 'passed':False, 'reason':str(exc)[:350]}
            print('FAILED: ' + stage + ': ' + str(exc)[:250], flush=True)
            failed = True
        temp = report_path.with_suffix('.json.partial')
        temp.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding='utf-8')
        temp.replace(report_path)
    raise SystemExit(1 if failed else 0)

if __name__ == '__main__': main()
