FROM python:3.11-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /srv/nexvary-voice
COPY engine/pyproject.toml ./pyproject.toml
COPY engine/voice_engine ./voice_engine
RUN python -m pip install --no-cache-dir -e ".[offline]" && \
    useradd --system --uid 10001 --create-home voice
USER 10001:10001
EXPOSE 8000
CMD ["uvicorn","voice_engine.api:app","--host","0.0.0.0","--port","8000","--proxy-headers=false"]
