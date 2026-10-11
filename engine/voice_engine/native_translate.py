"""Argos package inference without implicit Stanza/SBD downloads.

Uses the installed package tokenizer and its CTranslate2 model. Conservative
punctuation/chunk segmentation avoids loading a separate NLP model. Cache holds
at most two translation models so English pivoting has bounded memory.
"""
from __future__ import annotations
import os
import re
import threading
from collections import deque
from functools import lru_cache
from pathlib import Path

_guard = threading.RLock()


def route(pairs,source,target):
    if (source,target) in pairs: return [(source,target)]
    if (source,'en') in pairs and ('en',target) in pairs: return [(source,'en'),('en',target)]
    todo = deque([(source,[])]);seen={source}
    while todo:
        node,path=todo.popleft()
        for a,b in sorted(pairs):
            if a!=node or b in seen: continue
            next_path=path+[(a,b)]
            if b==target: return next_path
            seen.add(b);todo.append((b,next_path))
    raise RuntimeError('لا يوجد مسار ترجمة مثبت من '+source+' إلى '+target)


def chunks(text,limit=600):
    result=[]
    for sentence in re.split(r'(?<=[.!?؟।])\s+|\n+',text.strip()):
        while len(sentence)>limit:
            split=sentence.rfind(' ',0,limit)
            if split<limit//2: split=limit
            result.append(sentence[:split].strip());sentence=sentence[split:].strip()
        if sentence: result.append(sentence)
    return result


@lru_cache(maxsize=2)
def model(path,revision):
    import ctranslate2
    folder=Path(path)/'model'
    kwargs=dict(device='cpu',compute_type='int8', inter_threads=1,
                intra_threads=max(1,min(4,(os.cpu_count() or 2)//2)))
    # Pass file bytes on Windows when a native library cannot resolve UTF-8 paths.
    if os.name=='nt' and not str(folder).isascii():
        files={p.name:p.read_bytes() for p in folder.iterdir() if p.is_file()}
        if sum(map(len,files.values()))>1024**3: raise RuntimeError('Translation model exceeds memory policy')
        return ctranslate2.Translator(str(folder),files=files,**kwargs)
    return ctranslate2.Translator(str(folder),**kwargs)


def translate(text,source,target):
    import argostranslate.package as packages
    installed={(p.from_code,p.to_code):p for p in packages.get_installed_packages() if p.type=='translate'}
    path=route(installed,source,target)
    value=text
    with _guard:
        for pair in path:
            pkg=installed[pair]
            # SentencePiece can load serialized bytes without native path encoding.
            if hasattr(pkg.tokenizer,'model_file') and str(pkg.tokenizer.model_file).endswith('.model') and type(pkg.tokenizer).__name__=='SentencePieceTokenizer':
                import sentencepiece as spm
                pkg.tokenizer.processor=spm.SentencePieceProcessor(model_proto=Path(pkg.tokenizer.model_file).read_bytes())
            segments=chunks(value)
            tokenized=[pkg.tokenizer.encode(s) for s in segments]
            prefix=[[pkg.target_prefix]]*len(tokenized) if pkg.target_prefix else None
            translator=model(str(pkg.package_path),str(pkg.package_version))
            output=translator.translate_batch(tokenized,target_prefix=prefix,replace_unknowns=True,
                max_batch_size=32,batch_type='tokens',beam_size=4,num_hypotheses=1,
                length_penalty=.2,max_input_length=1024,max_decoding_length=1024)
            rendered=[]
            for batch in output:
                sentence=pkg.tokenizer.decode(batch.hypotheses[0])
                if pkg.target_prefix and sentence.startswith(pkg.target_prefix): sentence=sentence[len(pkg.target_prefix):]
                rendered.append(sentence.strip())
            value=' '.join(rendered).strip()
            if not value: raise RuntimeError('محرك الترجمة أعاد نصًا فارغًا.')
    return value
