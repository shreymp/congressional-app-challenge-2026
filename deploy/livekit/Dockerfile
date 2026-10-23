FROM node:22-bookworm-slim AS node
FROM python:3.11-slim-bookworm AS models
WORKDIR /build
COPY deploy/livekit/download_models.py ./
COPY model-sources.json ./
RUN python download_models.py model-sources.json /models

FROM python:3.11-slim-bookworm AS announcement
RUN apt-get update && apt-get install -y --no-install-recommends espeak-ng sox \
    && rm -rf /var/lib/apt/lists/*
COPY deploy/livekit/generate_recording_notice.py /generate_recording_notice.py
COPY ["backend/AI Deepfake Pipeline/LiveKit Setup/recording_notice.py", "/recording_notice.py"]
RUN python /generate_recording_notice.py --output /recording_notice.wav \
    && python -c "from pathlib import Path; from recording_notice import read_notice; read_notice(Path('/recording_notice.wav'))"

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
COPY --from=announcement ["/recording_notice.wav", "./backend/AI Deepfake Pipeline/LiveKit Setup/assets/recording_notice.wav"]
COPY deploy/livekit ./deploy/livekit
COPY --from=models /models /app/models
# Cache only the backbone architecture config, never untrained backbone weights.
RUN HF_HUB_OFFLINE=0 python -c "from transformers import Wav2Vec2Config; Wav2Vec2Config.from_pretrained('facebook/wav2vec2-xls-r-300m').save_pretrained('/app/models/backbone')" \
    && python -c "import json,pathlib; p=pathlib.Path('/app/models/deepfake/detector_config.json'); d=json.loads(p.read_text()); d['base_model']='/app/models/backbone'; p.write_text(json.dumps(d))" \
    && useradd --uid 10001 --create-home appuser \
    && python -m compileall -q backend deploy
USER appuser
CMD ["python", "deploy/livekit/cloud_agent.py", "start"]
