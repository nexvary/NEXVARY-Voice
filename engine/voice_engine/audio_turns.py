"""Energy based endpointing for 100 ms PCM16 blocks; no downloaded VAD model."""
from .live import CHUNK_BYTES, MIN_CHUNK_BYTES, pcm_rms

FRAME_BYTES = 3200


class SpeechTurns:
    def __init__(self, silence_frames=4):
        self.silence_frames = silence_frames
        self.reset()

    def reset(self):
        self.buffer = bytearray()
        self.previous = b''
        self.quiet = 0

    def feed(self, frame):
        if len(frame) != FRAME_BYTES:
            raise ValueError('Expected 100 ms PCM16 block')
        speaking = pcm_rms(frame) >= 170
        if not self.buffer:
            if not speaking:
                self.previous = frame
                return None
            self.buffer.extend(self.previous)
        self.buffer.extend(frame)
        self.previous = b''
        self.quiet = 0 if speaking else self.quiet + 1
        if len(self.buffer) >= CHUNK_BYTES or self.quiet >= self.silence_frames:
            result = bytes(self.buffer)
            self.reset()
            return result + b'\0' * max(0, MIN_CHUNK_BYTES - len(result))
        return None
