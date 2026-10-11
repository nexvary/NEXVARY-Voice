"""Bounded HTTPS downloads, resumable only with a matching source validator.

Interrupted data stays in .partial. No destination is replaced before its
upstream digest passes. Never uses a downloaded script or shell.
"""
from __future__ import annotations
import hashlib
import json
import os
import re
import urllib.request
from pathlib import Path

class DownloadCancelled(RuntimeError):
    pass


def digest_file(path: Path, algorithm: str = 'sha256') -> str:
    digest = hashlib.new(algorithm)
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def fetch_verified(url: str, target: Path, *, expected_digest: str,
                   algorithm: str = 'sha256', expected_size: int | None = None,
                   maximum: int = 220 * 1024 * 1024, progress=None, cancelled=None,
                   opener=urllib.request.urlopen) -> Path:
    if not url.startswith('https://'):
        raise ValueError('Only HTTPS download sources are permitted')
    length = {'sha256': 64, 'md5': 32}.get(algorithm)
    if not length or not re.fullmatch(r'[0-9a-fA-F]{' + str(length) + r'}', expected_digest):
        raise ValueError('Missing or invalid upstream digest')
    if expected_size is not None and not 0 < expected_size <= maximum:
        raise ValueError('Invalid expected download size')
    target = Path(target)
    if target.is_file() and (expected_size is None or target.stat().st_size == expected_size):
        if digest_file(target, algorithm).lower() == expected_digest.lower():
            if progress: progress(target.stat().st_size, target.stat().st_size)
            return target
    target.parent.mkdir(parents=True, exist_ok=True)
    stage = target.with_name(target.name + '.partial')
    meta = stage.with_name(stage.name + '.json')
    identity = {'url': url, 'digest': expected_digest.lower(), 'algorithm': algorithm}
    previous = {}
    try:
        previous = json.loads(meta.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        pass
    offset = 0
    if stage.is_file() and all(previous.get(k) == v for k, v in identity.items()):
        if previous.get('validator') and stage.stat().st_size <= maximum:
            offset = stage.stat().st_size
    # Complete partial from a connection that closed before validation.
    if stage.is_file() and expected_size == stage.stat().st_size:
        if digest_file(stage, algorithm).lower() == expected_digest.lower():
            os.replace(stage, target)
            meta.unlink(missing_ok=True)
            return target
    headers = {'User-Agent': 'NEXVARY-Voice/0.5.1', 'Accept-Encoding': 'identity'}
    if offset:
        headers.update({'Range': f'bytes={offset}-', 'If-Range': previous['validator']})
    if cancelled and cancelled(): raise DownloadCancelled('تم إيقاف التنزيل بأمان.')
    with opener(urllib.request.Request(url, headers=headers), timeout=20) as response:
        if not response.geturl().startswith('https://'):
            raise ValueError('Insecure redirect rejected')
        status = response.status
        total = expected_size
        if offset and status == 206:
            match = re.fullmatch(r'bytes (\d+)-(\d+)/(\d+)', response.headers.get('Content-Range', ''))
            if not match or int(match[1]) != offset:
                raise ValueError('Invalid download resume response')
            if expected_size is not None and int(match[3]) != expected_size:
                raise ValueError('Remote size changed')
            total = int(match[3])
        elif status == 200:
            offset = 0
            announced = response.headers.get('Content-Length')
            if announced and announced.isdigit():
                if expected_size is not None and int(announced) != expected_size:
                    raise ValueError('Remote size does not match metadata')
                total = int(announced)
        else:
            raise ValueError('Unexpected download status')
        if total is not None and not 0 < total <= maximum:
            raise ValueError('Download exceeds size limit')
        validator = response.headers.get('ETag') or response.headers.get('Last-Modified')
        meta.write_text(json.dumps({**identity, 'validator': validator}), encoding='utf-8')
        received = offset
        with stage.open('ab' if offset else 'wb') as sink:
            if progress: progress(received, total)
            while True:
                if cancelled and cancelled():
                    raise DownloadCancelled('تم إيقاف التنزيل. يمكن استكماله عند إعادة المحاولة.')
                chunk = response.read(256 * 1024)
                if not chunk: break
                received += len(chunk)
                if received > maximum or (total is not None and received > total):
                    raise ValueError('Download exceeds declared size')
                sink.write(chunk)
                if progress: progress(received, total)
        if total is not None and received != total:
            raise RuntimeError('انقطع التنزيل قبل اكتمال الملف؛ أعد المحاولة للاستكمال.')
    if digest_file(stage, algorithm).lower() != expected_digest.lower():
        stage.unlink(missing_ok=True)
        meta.unlink(missing_ok=True)
        raise ValueError('فشل التحقق من سلامة الملف؛ لم يتم تثبيته.')
    os.replace(stage, target)
    meta.unlink(missing_ok=True)
    return target
