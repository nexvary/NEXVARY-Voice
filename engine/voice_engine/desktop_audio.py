"""Bounded microphone/audio WebSocket loop used by the graphical Windows client.

Audio leaves the device only after explicit Start. Translated audio plays through
the OS-selected output. This is half-duplex, NOT a Windows virtual microphone.
"""
from __future__ import annotations

import json
import queue
import threading
from urllib.parse import urlsplit

from .desktop_api import ClientError


def run_audio_session(url: str, token: str, source: str, target: str,
                      stopping: threading.Event, log,
                      input_device=None, output_device=None) -> None:
    if not url.startswith("wss://"):
        parts = urlsplit(url)
        if not (parts.scheme == "ws" and parts.hostname in ("localhost", "127.0.0.1", "::1")):
            raise ClientError("استخدم WSS أو اتصالًا محليًا فقط.")
    try:
        import sounddevice as sd
        from websockets.sync.client import connect
    except ImportError as exc:
        raise ClientError("مكونات الصوت غير مثبتة؛ يلزم إصدار Windows المزود بالصوت.") from exc

    if source == target:
        raise ClientError("اختر لغتين مختلفتين.")
    if stopping.is_set():
        return

    frames = queue.Queue(maxsize=24)
    speaker_busy = threading.Event()
    worker_done = threading.Event()
    headers = {"Authorization": "Bearer " + token} if token else {}

    def capture(pcm, count, time_info, status):
        if stopping.is_set() or speaker_busy.is_set():
            return
        try:
            frames.put_nowait(bytes(pcm))
        except queue.Full:
            pass

    log("جارٍ الاتصال بمحرك الترجمة الصوتية…")
    with connect(url, additional_headers=headers, max_size=6_000_000,
                 open_timeout=12, close_timeout=3) as ws:
        ws.send(json.dumps({"source_language": source, "target_language": target,
                            "format": "pcm_s16le", "sample_rate": 16000}))
        with sd.RawOutputStream(samplerate=16000, channels=1, dtype="int16",
                                blocksize=1600, device=output_device) as output:

            def receive():
                try:
                    for message in ws:
                        if stopping.is_set():
                            break
                        if isinstance(message, bytes):
                            speaker_busy.set()
                            try:
                                # Drop queued microphone frames to prevent feedback.
                                while not frames.empty():
                                    try: frames.get_nowait()
                                    except queue.Empty: break
                                output.write(message)
                            finally:
                                speaker_busy.clear()
                        else:
                            data = json.loads(message)
                            if data.get("type") == "translated":
                                log(f"زمن المعالجة: {data.get('processing_seconds', 'غير متاح')} ثانية بعد مقطع {data.get('chunk_seconds', 3.2)} ثانية")
                                log("النص الأصلي: " + str(data.get("original_text", ""))[:280])
                                log("الترجمة: " + str(data.get("translated_text", ""))[:280])
                            elif data.get("type") == "error":
                                log("خطأ المحرك: " + str(data.get("message", ""))[:180])
                except Exception as exc:
                    if not stopping.is_set():
                        log("انقطع البث الصوتي: " + type(exc).__name__)
                finally:
                    worker_done.set()

            threading.Thread(target=receive, daemon=True).start()
            with sd.RawInputStream(samplerate=16000, channels=1, dtype="int16",
                                   blocksize=1600, device=input_device, callback=capture):
                log("الميكروفون يعمل. زمن كل مقطع صوتي نحو 3.2 ثانية إضافة إلى زمن المعالجة.")
                try:
                    while not stopping.is_set() and not worker_done.is_set():
                        try:
                            frame = frames.get(timeout=0.15)
                        except queue.Empty:
                            continue
                        if not speaker_busy.is_set():
                            ws.send(frame)
                finally:
                    stopping.set()
                    try:
                        ws.send(json.dumps({"type": "stop"}))
                    except Exception:
                        pass
                    ws.close()
    log("توقفت الجلسة الصوتية.")
