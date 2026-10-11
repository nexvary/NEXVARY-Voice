"""One active heavy workload per engine. No video/live overlap on CPU."""
from __future__ import annotations
import threading
from contextlib import contextmanager

lock = threading.Lock()
state = 'idle'

@contextmanager
def exclusive(kind):
    global state
    if not lock.acquire(blocking=False):
        raise RuntimeError('المحرك مشغول بمهمة صوت أو دبلجة؛ انتظر اكتمالها.')
    state = kind
    try: yield
    finally:
        state = 'idle'; lock.release()
