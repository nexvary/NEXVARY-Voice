FROM python:3.11-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 XDG_CACHE_HOME=/models/cache XDG_CONFIG_HOME=/models/config XDG_DATA_HOME=/models/data HF_HOME=/models/huggingface
WORKDIR /srv/nexvary-voice
COPY engine/pyproject.toml ./pyproject.toml
COPY engine/voice_engine ./voice_engine
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg && rm -rf /var/lib/apt/lists/*\nRUN python -m pip install --no-cache-dir -e ".[offline,speech]" && \
    useradd --system --uid 10001 --create-home voice
USER 10001:10001
EXPOSE 8000
CMD ["uvicorn","voice_engine.api:app","--host","0.0.0.0","--port","8000","--no-proxy-headers"]
