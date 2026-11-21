# Public, read-only copy of the NAACL demo (/study and the evidence inspector at /).
# Standard library only: no model, no keys, no network calls, synthetic data only.
# Build from the repository root:
#   docker build -f deploy/demo/Dockerfile -t finbot-demo .
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PORT=8080 FINBOT_DEMO_BIND=0.0.0.0
WORKDIR /app
COPY finbot/ finbot/
COPY LICENSE ./

RUN useradd --uid 10001 --no-create-home demo
USER 10001
EXPOSE 8080

# FINBOT_DEMO_PUBLIC_HOST must be set to the HTTPS hostname visitors use (see deploy/demo/README.md).
CMD ["python", "-m", "finbot.demo"]
