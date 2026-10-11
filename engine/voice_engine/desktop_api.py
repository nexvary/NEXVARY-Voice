"""Typed, bounded HTTP client for the NEXVARY Windows graphical application.

Do not permit remote plaintext transport; localhost HTTP is for explicit local
model testing only. Never put bearer tokens into URLs, logs or configuration.
"""
from __future__ import annotations

import ipaddress
import os
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import httpx

MAX_UPLOAD = 80 * 1024 * 1024
LANGUAGES = {"ar", "en", "hi", "tr", "fr", "de", "es", "it", "ru", "bn"}


class ClientError(RuntimeError):
    pass


def _local(name: str) -> bool:
    if name.lower() == "localhost":
        return True
    try:
        return ipaddress.ip_address(name).is_loopback
    except ValueError:
        return False


def normalize_url(base: str) -> str:
    """Canonical HTTP(S) origin; reject injected paths, credentials, unsafe HTTP."""
    parsed = urlsplit(base.strip())
    if not parsed.hostname or parsed.username or parsed.password:
        raise ClientError("عنوان الخادم غير صالح.")
    if parsed.query or parsed.fragment or parsed.path not in ("", "/"):
        raise ClientError("أدخل عنوان الخادم الأساسي فقط دون مسار أو معاملات.")
    if parsed.scheme not in ("https", "http"):
        raise ClientError("يلزم استخدام HTTPS.")
    if parsed.scheme == "http" and not _local(parsed.hostname):
        raise ClientError("يُسمح بـ HTTP على الجهاز المحلي فقط. استخدم HTTPS للخادم البعيد.")
    try:
        parsed.port  # raises ValueError for malformed port
    except ValueError as exc:
        raise ClientError("رقم منفذ غير صحيح.") from exc
    return urlunsplit((parsed.scheme, parsed.netloc, "", "", "")).rstrip("/")


def websocket_url(base: str) -> str:
    normal = normalize_url(base)
    if normal.startswith("https://"):
        return "wss://" + normal[8:] + "/v1/live/audio"
    return "ws://" + normal[7:] + "/v1/live/audio"


def _check_pair(source: str, target: str) -> None:
    if source not in LANGUAGES or target not in LANGUAGES or source == target:
        raise ClientError("اختر لغتين مختلفتين ومدعومتين.")


class DesktopAPI:
    def __init__(self, base: str, token: str = "", transport=None):
        self.base = normalize_url(base)
        self.token = token.strip()
        self._transport = transport

    def _request(self, method: str, path: str, *, json=None, files=None, data=None,
                 timeout: float = 40) -> httpx.Response:
        headers = {"Authorization": "Bearer " + self.token} if self.token else {}
        try:
            with httpx.Client(
                transport=self._transport, timeout=httpx.Timeout(timeout, connect=8),
                follow_redirects=False, trust_env=False
            ) as client:
                response = client.request(method, self.base + path,
                                          headers=headers, json=json, files=files, data=data)
                response.raise_for_status()
                return response
        except httpx.HTTPStatusError as exc:
            code = exc.response.status_code
            if code == 503:
                raise ClientError("محرك الذكاء الاصطناعي غير متاح أو النماذج غير مثبتة (503).") from exc
            if code in (401, 403):
                raise ClientError("تم رفض المصادقة. تحقق من رمز API.") from exc
            if code == 413:
                raise ClientError("الفيديو أكبر من الحد المسموح (80 MB).") from exc
            raise ClientError(f"رفض الخادم الطلب: HTTP {code}.") from exc
        except httpx.HTTPError as exc:
            raise ClientError("تعذر الاتصال بالخادم. تحقق من الرابط وTLS والشبكة.") from exc

    def health(self) -> dict:
        data = self._request("GET", "/health", timeout=12).json()
        if data.get("status") != "ok":
            raise ClientError("الخادم لا يستجيب بحالة سليمة.")
        return data

    def translate(self, text: str, source: str, target: str) -> str:
        _check_pair(source, target)
        if not text.strip() or len(text) > 4000:
            raise ClientError("النص مطلوب ولا يجوز أن يتجاوز 4000 حرف.")
        answer = self._request("POST", "/v1/translate", json={
            "text": text, "source_language": source, "target_language": target
        }).json()
        return str(answer["translated_text"])

    def translate_srt(self, srt: str, source: str, target: str) -> str:
        _check_pair(source, target)
        if not srt.strip() or len(srt) > 500_000:
            raise ClientError("ملف SRT غير صالح أو كبير جدًا.")
        answer = self._request("POST", "/v1/subtitles/translate", json={
            "srt": srt, "source_language": source, "target_language": target
        }, timeout=120).json()
        return str(answer["srt"])

    def submit_video(self, path: Path, source: str, target: str) -> dict:
        _check_pair(source, target)
        path = Path(path)
        if not path.is_file() or path.suffix.lower() != ".mp4":
            raise ClientError("اختر ملف MP4 موجودًا.")
        size = path.stat().st_size
        if not 0 < size <= MAX_UPLOAD:
            raise ClientError("يلزم أن يكون حجم الفيديو بين 1 بايت و80 MB.")
        with path.open("rb") as stream:
            response = self._request("POST", "/v1/dub/jobs",
                files={"file": (path.name, stream, "video/mp4")},
                data={"source_language": source, "target_language": target},
                timeout=180)
        return response.json()

    def video_status(self, job_id: str) -> dict:
        if not job_id or len(job_id) > 80 or "/" in job_id:
            raise ClientError("رقم مهمة غير صالح.")
        return self._request("GET", "/v1/dub/jobs/" + job_id).json()

    def download_video(self, job_id: str, target: Path) -> Path:
        if not job_id or len(job_id) > 80 or "/" in job_id:
            raise ClientError("رقم مهمة غير صالح.")
        path = Path(target)
        if path.exists():
            raise ClientError("الملف المحدد موجود بالفعل، ولن تتم الكتابة فوقه.")
        temp = path.with_name(path.name + ".partial")
        if temp.exists():
            raise ClientError("هناك تنزيل غير مكتمل بنفس الاسم؛ احذفه بعد التحقق.")
        headers = {"Authorization": "Bearer " + self.token} if self.token else {}
        try:
            with httpx.Client(timeout=httpx.Timeout(180, connect=8),
                              follow_redirects=False, trust_env=False) as client:
                with client.stream("GET", self.base + "/v1/dub/jobs/" + job_id + "/video",
                                   headers=headers) as response:
                    response.raise_for_status()
                    total = 0
                    with temp.open("xb") as out:
                        for chunk in response.iter_bytes(128 * 1024):
                            total += len(chunk)
                            if total > 500 * 1024 * 1024:
                                raise ClientError("حجم الملف الناتج تجاوز حد 500 MB.")
                            out.write(chunk)
            if not temp.stat().st_size:
                raise ClientError("الملف الناتج فارغ.")
            os.replace(temp, path)
            return path
        except (httpx.HTTPError, OSError) as exc:
            raise ClientError("فشل تنزيل الفيديو المترجم.") from exc
        finally:
            if temp.exists():
                temp.unlink()


    def models(self):
        return self._request('GET','/v1/models/status',timeout=60).json()

    def cancel_video(self,job_id):
        if not job_id or len(job_id)>80 or '/' in job_id: raise ClientError('رقم مهمة غير صالح.')
        return self._request('POST','/v1/dub/jobs/'+job_id+'/cancel').json()

    def download_subtitles(self,job_id,target):
        if not job_id or len(job_id)>80 or '/' in job_id: raise ClientError('رقم مهمة غير صالح.')
        response = self._request('GET','/v1/dub/jobs/'+job_id+'/subtitles')
        path = Path(target)
        if path.exists(): raise ClientError('اختر اسم ملف جديدًا؛ الملف موجود بالفعل.')
        # Preserve server CRLF exactly; text-mode output on Windows would turn
        # CRLF into CRCRLF and split SRT cue lines into invalid empty blocks.
        with path.open('xb') as output: output.write(response.content)
        return path
