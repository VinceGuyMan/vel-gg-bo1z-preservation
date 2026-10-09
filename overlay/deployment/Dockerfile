# syntax=docker/dockerfile:1
# REVIEW TEMPLATE ONLY. Build context: this file, .dockerignore, and the exact
# reviewed signaling.py plus ws_relay.py/ws_wire.py/ws-transport.js. Never use the original archive as a build context.
ARG PYTHON_IMAGE=python:3.12-slim
FROM ${PYTHON_IMAGE}
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY --chown=65532:65532 signaling.py ws_relay.py ws_wire.py ws-transport.js /app/
USER 65532:65532
EXPOSE 8768
# Current service catches KeyboardInterrupt; preserve its clean shutdown path.
STOPSIGNAL SIGINT
HEALTHCHECK --interval=20s --timeout=3s --start-period=5s --retries=3 CMD ["python", "-c", "import json,urllib.request; r=json.load(urllib.request.urlopen('http://127.0.0.1:8768/coop/health',timeout=2)); assert r.get('ok') is True and r.get('service')=='bo1z-local-signaling' and r.get('transportProtocol')=='bo1z-native-rtc-resume-v2' and r.get('gameAssets') is False"]
ENTRYPOINT ["python", "-u", "/app/signaling.py", "--bind", "0.0.0.0", "--port", "8768", "--require-invite"]
# These are the browser GAME page origins, not the public signaling URL.
# Supplying runtime arguments replaces CMD; repeat every intended origin.
CMD ["--allow-origin", "http://127.0.0.1:8767", "--allow-origin", "http://localhost:8767"]
