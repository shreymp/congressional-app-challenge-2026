FROM node:22-bookworm-slim AS node
FROM python:3.11-slim-bookworm AS models
WORKDIR /build
COPY deploy/livekit/download_models.py ./
COPY model-sources.json ./
RUN python download_models.py model-sources.json /models

FROM python:3.11-slim-bookworm
ENV PYTHONUNBUFFERED=1 HF_HUB_OFFLINE=1 TOKENIZERS_PARALLELISM=false \
    DETECTOR=remote DETECTOR_DEVICE=cpu DETECTOR_SERVICE_URL=http://127.0.0.1:8000 \
    TRANSCRIPT_ENABLED=1 VOSK_MODEL_PATH=/app/models/vosk-model-small-en-us-0.15 \
    TRANSCRIPT_SCORE_URL=http://127.0.0.1:3000/v1/jev/probability \
    TRANSCRIPT_SCORE_TIMEOUT_SEC=25 TRANSCRIPT_MAX_AGE_SEC=35 TRANSCRIPT_SCORE_EVERY_SEC=5 \
    JEV_MODEL_URL=http://127.0.0.1:8000/predict JEV_TIMEOUT_MS=20000 \
    JEV_MODEL_DIR=/app/models/JevCallV2 DETECTOR_WEIGHTS_DIR=/app/models/deepfake \
    HOST=127.0.0.1 PORT=3000 RECORD_CALLER_AUDIO=0 OMP_NUM_THREADS=2 MKL_NUM_THREADS=2
WORKDIR /app
COPY --from=node /usr/local/bin/node /usr/local/bin/node
RUN apt-get update && apt-get install -y --no-install-recommends libsndfile1 libgomp1 libstdc++6 libatomic1 ca-certificates \
    && rm -rf /var/lib/apt/lists/*
COPY deploy/livekit/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir torch==2.9.1 --index-url https://download.pytorch.org/whl/cpu \
    && pip install --no-cache-dir -r /tmp/requirements.txt
COPY backend ./backend
COPY deploy/livekit ./deploy/livekit
COPY --from=models /models /app/models
# inference.py now builds the backbone from the pinned backend/AI Deepfake Pipeline/architecture/config.json
# and model_integrity.py verifies detector_config.json byte for byte, so the config must NOT be rewritten
# here (the old base_model rewrite changed its SHA-256 and would make the detector fail to load).
RUN useradd --uid 10001 --create-home appuser \
    && python -m compileall -q backend deploy
USER appuser
CMD ["python", "deploy/livekit/cloud_agent.py", "start"]
