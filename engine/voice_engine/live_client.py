"""Experimental Windows/Linux desktop microphone interpreter.

Uses existing system sound devices; translated sound is output to selected speakers/headphones.
OBS can capture application audio on compatible desktop systems; this is NOT virtual mic injection.
"""
from __future__ import annotations

import argparse
import json
import os
import queue
import threading


def main() -> None:
    parser = argparse.ArgumentParser(description="NEXVARY Voice streamed audio client")
    parser.add_argument("--url", required=True, help="wss://host/v1/live/audio")
    parser.add_argument("--source", default="ar")
    parser.add_argument("--target", default="en")
    parser.add_argument("--token", default=None, help="Prefer NEXVARY_API_TOKEN environment variable")
    parser.add_argument("--input-device", type=int)
    parser.add_argument("--output-device", type=int)
    parser.add_argument("--allow-insecure-localhost", action="store_true",
                        help="Only permits ws://127.0.0.1 or ws://localhost for local testing")
    args = parser.parse_args()
    if args.source == args.target:
        parser.error("Choose two different languages")
    if not args.url.startswith("wss://"):
        if not (args.allow_insecure_localhost and
                args.url.startswith(("ws://localhost:", "ws://127.0.0.1:"))):
            parser.error("Use wss://; local ws:// requires --allow-insecure-localhost")
    try:
        import sounddevice as sd
        from websockets.sync.client import connect
    except ImportError as exc:
        parser.exit(1, "Install desktop dependencies: pip install -e '.[desktop]'\n")
    token = args.token or os.environ.get("NEXVARY_API_TOKEN", "")
    headers = {"Authorization": "Bearer " + token} if token else {}
    frames = queue.Queue(maxsize=30)
    speaker_busy = threading.Event()
    closing = threading.Event()

    def capture(indata, count, time_info, status):
        if closing.is_set() or speaker_busy.is_set():
            return
        try:
            frames.put_nowait(bytes(indata))
        except queue.Full:
            pass  # Drop stale speech rather than adding unbounded delay.

    print("Connecting to audio service. Use headphones to prevent translation feedback.")
    with connect(args.url, additional_headers=headers, max_size=6_000_000,
                 open_timeout=15) as socket:
        socket.send(json.dumps({"source_language": args.source,
                                "target_language": args.target,
                                "format": "pcm_s16le", "sample_rate": 16000}))
        with sd.RawOutputStream(samplerate=16000, blocksize=1600, channels=1,
                                dtype="int16", device=args.output_device) as output:
            def receive():
                try:
                    for message in socket:
                        if isinstance(message, bytes):
                            speaker_busy.set()
                            try:
                                output.write(message)
                            finally:
                                speaker_busy.clear()
                        else:
                            response = json.loads(message)
                            if response.get("type") == "translated":
                                print(f"Original: {response['original_text']}")
                                print(f"Translated: {response['translated_text']}")
                            elif response.get("type") == "error":
                                print("Server error:", response.get("message", "unknown"))
                except Exception as exc:
                    print("Connection closed:", type(exc).__name__)
                finally:
                    closing.set()

            thread = threading.Thread(target=receive, daemon=True)
            thread.start()
            try:
                with sd.RawInputStream(samplerate=16000, blocksize=1600, channels=1,
                                       dtype="int16", device=args.input_device, callback=capture):
                    print("Listening and translating in 3.2s speech chunks. Ctrl+C to stop.")
                    while not closing.is_set():
                        try:
                            packet = frames.get(timeout=0.2)
                            if not speaker_busy.is_set():
                                socket.send(packet)
                        except queue.Empty:
                            pass
            except KeyboardInterrupt:
                print("Stopping microphone stream.")
            finally:
                closing.set()
                try:
                    socket.send(json.dumps({"type": "stop"}))
                except Exception:
                    pass


if __name__ == "__main__":
    main()
