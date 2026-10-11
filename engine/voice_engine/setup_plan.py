"""Small metadata-only preflight, before consent to heavy downloads."""
from __future__ import annotations
import json
import urllib.request
from pathlib import Path
from .asset_inventory import voice_map
from .setup_assets import REGISTRY, VOICES, model_entries, verified_file

INDEX = 'https://raw.githubusercontent.com/argosopentech/argospm-index/main/index.json'


def read_https(url, limit=5 * 1024 * 1024):
    request = urllib.request.Request(url, headers={'User-Agent':'NEXVARY-Voice/0.5.1'})
    with urllib.request.urlopen(request, timeout=15) as source:
        if not source.geturl().startswith('https://'): raise ValueError('Insecure metadata source')
        data = source.read(limit + 1)
    if len(data) > limit: raise ValueError('Metadata too large')
    return data


def build_plan(state: dict, root: Path, mode='all') -> dict:
    selected = state.get('selected_model', 'base')
    missing = []
    voice_bytes = 0
    licenses = []
    unavailable = []
    if mode in {'all','runtime'} and state.get('runtime_details',{}).get('state') != 'ready':
        missing.append('Python 3.11 مستقل + Faster-Whisper + Argos + Piper')
    if mode in {'all','ffmpeg'} and not (state.get('ffmpeg') and state.get('ffprobe')):
        missing.append('FFmpeg / FFprobe — LGPL/GPL حسب توزيعة gyan.dev (تراخيص مرفقة في المصدر)')
    if mode in {'all','whisper'} and not state.get('whisper_cached'):
        missing.append('Whisper ' + selected + ' CPU INT8 — MIT')
    if mode in {'all','translations'} and not state.get('translation_ready'):
        index = json.loads(read_https(INDEX))
        pairs = {(entry.get('from_code'),entry.get('to_code')) for entry in index}
        needed = [(c,'en') for c in VOICES if c != 'en'] + [('en',c) for c in VOICES if c != 'en']
        for source,target in needed:
            if (source,target) not in pairs: unavailable.append(source+'→'+target)
        missing.append('نماذج Argos: عشرة اتجاهات عبر الإنجليزية؛ أحجام غير معلنة في الفهرس')
        licenses.append('Argos Translate: MIT/CC0. تراخيص النماذج قد تختلف؛ راجع بيانات الحزمة والفهرس الرسمي: ' + INDEX)
    if mode in {'all','voices'}:
        installed_voices = voice_map(root)
        registry = json.loads(read_https(REGISTRY + '/voices.json'))
        for code,name in VOICES.items():
            try:
                entries = model_entries(registry,name)
                needed = 0
                for relative,record in entries:
                    filename = Path(relative).name
                    if filename == 'MODEL_CARD':
                        card = read_https(REGISTRY+'/'+relative,limit=200_000).decode('utf-8')
                        licenses.append(code + ' — ' + name + '\n' + card)
                        filename = 'MODEL_CARD-'+code+'.txt'
                    target = root/'models'/'voices'/code/filename
                    existing = installed_voices.get(code)
                    if existing and filename.endswith(('.onnx','.onnx.json')):
                        possible = Path(existing + ('.json' if filename.endswith('.json') else ''))
                        if verified_file(possible,record): target=possible
                    if not verified_file(target,record): needed += record['size_bytes']
                if needed:
                    voice_bytes += needed
                    missing.append('صوت Piper '+code+' — '+str(round(needed/1024**2,1))+' MB')
            except (RuntimeError, ValueError, KeyError) as exc:
                unavailable.append(code+': '+str(exc)[:150])
        licenses.append('Piper runtime: GPL-3.0 (OHF-Voice). تراخيص بيانات وأصوات كل لغة موضحة أعلاه.')
    return {'missing':missing,'voice_download_bytes':voice_bytes,
            'other_download_bytes':None,'storage_estimate_gb':6 if mode=='all' else 3,
            'selected_model':selected, 'execution':'CPU INT8; حتى 4 خيوط؛ مهمة صوت أو فيديو واحدة',
            'licenses':licenses, 'unavailable':unavailable,
            'note':'المساحة تقدير احتياطي؛ لا يُعرف إجمالي التنزيل بدقة حتى يحدد مدير الحزم الملفات.'}
