"""Bounded microphone/audio WebSocket loop used by the graphical Windows client.

Audio leaves the device only after explicit Start. Translated audio plays through
the OS-selected output. This is half-duplex, NOT a Windows virtual microphone.
"""
from __future__ import annotations

import json
import queue
import threading
import time

from .audio_turns import SpeechTurns
from .live import pcm_rms, MAX_FRAME_BYTES, CHUNK_BYTES
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
    awaiting_reply = threading.Event()
    sent_at = [0.0]
    turns = SpeechTurns()
    headers = {"Authorization": "Bearer " + token} if token else {}

    def capture(pcm, count, time_info, status):
        if stopping.is_set() or worker_done.is_set() or speaker_busy.is_set() or awaiting_reply.is_set():
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
                                for offset in range(0, len(message), 3200):
                                    if stopping.is_set() or worker_done.is_set():
                                        break
                                    output.write(message[offset:offset+3200])
                            finally:
                                speaker_busy.clear()
                                awaiting_reply.clear()
                        else:
                            data = json.loads(message)
                            if data.get("type") == "translated":
                                if data.get("stage_seconds"):
                                    stages=data["stage_seconds"]
                                    log("زمن المراحل بالثواني: تعرف="+str(stages.get("asr"))+"، ترجمة="+str(stages.get("translation"))+"، نطق="+str(stages.get("tts"))+"، تحويل="+str(stages.get("conversion")))
                                if sent_at[0]:
                                    log(f"زمن انتظار الرد حتى وصول النص: {time.monotonic()-sent_at[0]:.2f} ثانية")
                                log(f"زمن المعالجة: {data.get('processing_seconds', 'غير متاح')} ثانية بعد مقطع {data.get('chunk_seconds', 3.2)} ثانية")
                                log("النص الأصلي: " + str(data.get("original_text", ""))[:280])
                                log("الترجمة: " + str(data.get("translated_text", ""))[:280])
                            elif data.get("type") == "idle":
                                awaiting_reply.clear()
                            elif data.get("type") == "error":
                                awaiting_reply.clear()
                                log("خطأ المحرك: " + str(data.get("message", ""))[:180])
                except Exception as exc:
                    if not stopping.is_set():
                        log("انقطع البث الصوتي: " + type(exc).__name__)
                finally:
                    worker_done.set()

            receiver = threading.Thread(target=receive, daemon=True)
            receiver.start()
            with sd.RawInputStream(samplerate=16000, channels=1, dtype="int16",
                                   blocksize=1600, device=input_device, callback=capture):
                log("الميكروفون يعمل. يُرسل الكلام بعد توقف قصير (0.4 ثانية) أو حد 3.2 ثانية. انتظر الرد قبل الكلام التالي.")
                try:
                    while not stopping.is_set() and not worker_done.is_set():
                        if awaiting_reply.is_set() and time.monotonic()-sent_at[0] > 90:
                            raise ClientError("تأخر الرد أكثر من 90 ثانية؛ أعد فحص المحرك والاتصال.")
                        try:
                            frame = frames.get(timeout=0.15)
                        except queue.Empty:
                            continue
                        if not speaker_busy.is_set() and not awaiting_reply.is_set():
                            chunk = turns.feed(frame)
                            if chunk is not None:
                                awaiting_reply.set()
                                sent_at[0] = time.monotonic()
                                while not frames.empty():
                                    try: frames.get_nowait()
                                    except queue.Empty: break
                                for offset in range(0, len(chunk), MAX_FRAME_BYTES):
                                    ws.send(chunk[offset:offset+MAX_FRAME_BYTES])
                                # Max-size chunks are handled automatically by the server.
                                if len(chunk) < CHUNK_BYTES:
                                    ws.send(json.dumps({"type": "flush"}))
                finally:
                    worker_done.set()
                    try:
                        ws.send(json.dumps({"type": "stop"}))
                    except Exception:
                        pass
                    ws.close()
                    receiver.join(timeout=3)
    log("توقفت الجلسة الصوتية.")


def test_audio_devices(input_device=None, output_device=None):
    """Explicit local-only 3 second capture/playback; retains no recording."""
    import sounddevice as sd
    sd.check_input_settings(device=input_device, channels=1, dtype='int16', samplerate=16000)
    sd.check_output_settings(device=output_device, channels=1, dtype='int16', samplerate=16000)
    with sd.RawInputStream(device=input_device, channels=1, dtype='int16', samplerate=16000) as stream:
        pcm, overflow = stream.read(48000)
        pcm = bytes(pcm)
    level = pcm_rms(pcm)
    if overflow:
        raise ClientError('حدث انقطاع أثناء تسجيل اختبار الميكروفون؛ أعد الاختبار.')
    if level < 170:
        raise ClientError('الصوت المسجل ضعيف أو صامت؛ افحص الميكروفون ومستوى الإدخال ثم أعد الاختبار.')
    with sd.RawOutputStream(device=output_device, channels=1, dtype='int16', samplerate=16000) as stream:
        if stream.write(pcm):
            raise ClientError('حدث انقطاع أثناء تشغيل الاختبار؛ أعد الاختبار.')
    return f'تم تسجيل وتشغيل 3 ثوانٍ محليًا، مستوى الصوت {level:.0f}. هل سمعت تسجيلك؟ نجاح إرسال الصوت للجهاز لا يثبت أنك سمعته.'
