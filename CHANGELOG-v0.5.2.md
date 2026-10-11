# NEXVARY Voice Studio 0.5.2

Based on main ff0fca19bd0c5775c0d84fa931f197244b6be46d (0.5.0).

- Nine Arabic RTL pages, SVG icons, internal back navigation, scroll-safe sidebar, separate diagnostic/setup tabs.
- Read-only Windows/CPU/RAM/disk/audio/network/port probes with reasons; binary execution checks and isolated runtime version/import checks.
- Metadata-only download plan and individual voice MODEL_CARDs before one consent for heavy setup.
- CPU INT8 tiny/base/small choice, bounded threads, shared ASR, heavy workload lock and local process ownership.
- HTTPS voice downloads retain partial files, resume with validators and Range, verify upstream size+MD5; FFmpeg archive requires upstream SHA-256 before extraction and executable tests.
- Partial voice mapping checkpoint; reuses valid voice files and existing private runtime; repair avoids rebuilding an existing venv.
- Unicode-safe Argos tokenization/model loading and native CPU inference with a two-model cache; conservative sentence chunking avoids unavailable Bengali Stanza resources. Piper API handles Unicode native data paths and forbids implicit diacritizer downloads.
- Functional validation: 30 translation directions, six Piper WAV samples, Whisper recognition benchmark, short real AI dubbed MP4/SRT. Installed file checks are explicitly separate from inference checks.
- Engine start/stop/restart with identity check and readiness timeout. Owned-process metrics and redacted session logs.
- Video phase/segment progress, cooperative cancellation, SRT download, saved video preview, and output audio/video stream validation.
- Windows CI now runs all tests, frozen EXE smoke test and real screenshots, creates versioned portable ZIP with SHA-256. Separate Windows job exercises actual isolated setup and model inference; failures are retained, not hidden.

## Known limits

- Bluetooth audio: lists currently connected Windows audio endpoints. Automatic pairing and proof that a given endpoint uses Bluetooth are not implemented.
- GPU inventory does not prove CUDA inference compatibility. Managed setup deliberately uses CPU INT8.
- CPU/RAM recommendation is an initial conservative choice. Functional report measures real inference/load time; no unmeasured small/large model recommendation.
- Argos/Whisper package downloads use their upstream library cache; exact byte progress/resume depends on upstream support. Voice and FFmpeg downloads provide measured bytes and validated resume. No artificial aggregate percentage.
- Cancellation during native model inference takes effect after the current model call. FFmpeg and setup subprocesses can be stopped; completed verified assets are retained.
- No virtual microphone/driver or true simultaneous interpretation. Audio uses 3.2-second half-duplex chunks and reports processing time.
- No proof of physical microphone/speaker behavior on GitHub-hosted runners. Audio audibility requires local listening.
- Model functional checks prove execution and valid media, not human translation quality.

- Runtime compatibility pins are checked against the application version; older private environments are upgraded instead of being mistaken for current ones. Existing voices are discovered in bounded app/per-user folders and reused after upstream integrity verification. Historical functional success is invalidated when relevant models change.
