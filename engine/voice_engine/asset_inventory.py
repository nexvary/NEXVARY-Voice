"""Bounded read-only voice discovery in app and conventional per-user folders."""
from __future__ import annotations
import json
import os
from pathlib import Path

CODES = {'ar','en','it','ru','es','bn','hi','tr','fr','de'}


def voice_map(root: Path) -> dict[str,str]:
    mapping = {}
    try:
        value=json.loads(os.getenv('NEXVARY_PIPER_VOICES','{}'))
        if isinstance(value,dict): mapping.update({k:v for k,v in value.items() if k in CODES and isinstance(v,str)})
    except ValueError: pass
    try:
        value=json.loads((root/'voices.json').read_text(encoding='utf-8-sig'))
        if isinstance(value,dict): mapping.update({k:v for k,v in value.items() if k in CODES and isinstance(v,str)})
    except (OSError,ValueError): pass
    folders=[root/'models'/'voices',Path.home()/'.local'/'share'/'piper',Path.home()/'.cache'/'piper']
    count=0
    for folder in folders:
        if not folder.is_dir():continue
        # No whole-disk or recursive scan. At most 200 candidates, depth <= 3.
        for pattern in ('*.onnx','*/*.onnx','*/*/*.onnx'):
            for path in folder.glob(pattern):
                count+=1
                if count>200:return mapping
                config=Path(str(path)+'.json')
                try:
                    data=json.loads(config.read_text(encoding='utf-8'))
                    code=str((data.get('language') or {}).get('code') or path.name.split('_')[0]).split('_')[0]
                    if code in CODES and path.stat().st_size>1024 and data.get('audio',{}).get('sample_rate') and data.get('phoneme_id_map'):
                        if code not in mapping or not Path(mapping[code]).is_file():mapping[code]=str(path.resolve())
                except (OSError,ValueError,AttributeError):continue
    return mapping


def functional_report(root: Path) -> dict:
    try:
        data=json.loads((root/'functional-tests.json').read_text(encoding='utf-8'))
    except (OSError,ValueError):return {}
    if not isinstance(data,dict):return {}
    files=[]
    package_files=[]
    try:
        selected_model=json.loads((root/'preferences.json').read_text(encoding='utf-8')).get('whisper_model','base')
    except (OSError,ValueError,AttributeError):selected_model='base'
    whisper_files=[]
    snapshots=root/'huggingface'/'hub'/('models--Systran--faster-whisper-'+selected_model)/'snapshots'
    if snapshots.is_dir():
        for folder in list(snapshots.iterdir())[:20]:
            whisper_files.extend([folder/'model.bin',folder/'config.json',folder/'tokenizer.json'])
    for path in voice_map(root).values():files.extend([Path(path),Path(path+'.json')])
    if (root/'argos').is_dir():
        for folder in list((root/'argos').iterdir())[:200]:
            package_files.extend([folder/'metadata.json',folder/'sentencepiece.model',folder/'bpe.model',folder/'model'/'model.bin'])
    for stage,value in data.items():
        current_files=package_files if stage=='translations' else files if stage=='voices' else whisper_files if stage=='whisper' else files+package_files+whisper_files
        latest=max((p.stat().st_mtime for p in current_files if p.is_file()),default=0)
        if isinstance(value,dict):
            value['current_assets_unchanged']=value.get('checked_at',0)>=latest
            if stage=='whisper':
                value['current_assets_unchanged']=value['current_assets_unchanged'] and value.get('data',{}).get('model')==selected_model
            value['kind']='previous functional check; rerun after model changes'
    return data
