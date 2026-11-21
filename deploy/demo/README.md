# Hosting the NAACL demo

The demo is a standard-library Python server with no database. By default it calls no model and
needs no key; an optional, capped live writer is described below.
Every request replays at most twelve events, so it keeps no state between requests and any
number of copies can run side by side. It serves the conversation at `/` (also `/study`) and the
evidence inspector at `/inspector`.

## Google Cloud Run (recommended)

Cloud Run's free tier covers a demo like this, it scales to zero between visits, and a cold start
for this image takes about a second. You need a Google Cloud project with billing enabled and the
`gcloud` CLI, signed in (`gcloud auth login`, `gcloud config set project <project>`).

From the repository root (no local Docker needed; Cloud Build builds the image):

```bash
REGION=us-central1; PROJECT=$(gcloud config get project)
gcloud services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com  # once
gcloud artifacts repositories create demo --repository-format=docker --location=$REGION            # once
gcloud builds submit --config deploy/demo/cloudbuild.yaml --substitutions _REGION=$REGION .
gcloud run deploy finbot-demo --image $REGION-docker.pkg.dev/$PROJECT/demo/finbot-demo \
  --region $REGION --allow-unauthenticated --max-instances 3 --concurrency 32 --memory 256Mi
```

With Docker installed you can instead `docker build -f deploy/demo/Dockerfile -t <image> .`
and `docker push` it before the deploy step.

The first deploy prints the service URL, for example `https://finbot-demo-abc123-uc.a.run.app`.
Until the server knows that hostname it refuses every request (403), so set it and redeploy:

```bash
gcloud run services update finbot-demo --region $REGION \
  --set-env-vars FINBOT_DEMO_PUBLIC_HOST=finbot-demo-abc123-uc.a.run.app
```

Cloud Run gives a service two addresses (`...-<project number>.<region>.run.app` and `...-<hash>-uc.a.run.app`); to accept both, pass them comma-separated, quoting the value as `^;^FINBOT_DEMO_PUBLIC_HOST=host1,host2` because gcloud splits on commas. Then open `https://<that host>/study`. `--max-instances 3` caps cost if the link is shared widely.

## Optional live writer (capped)

By default the demo uses a scripted writer and calls no model. To let visitors switch on a live
model for the answer about the confirmed record, give the service an OpenAI-compatible endpoint
and key. Use a separate key with its own spending limit (for OpenRouter: Settings, API Keys,
Create Key, set a credit limit), so the provider stops it at that limit whatever the server does.
Store the key in Secret Manager rather than as a plain variable:

```bash
printf '%s' 'sk-or-...' | gcloud secrets create finbot-demo-openrouter --data-file=-   # once
PROJECT_NUMBER=$(gcloud projects describe $PROJECT --format='value(projectNumber)')
gcloud secrets add-iam-policy-binding finbot-demo-openrouter \
  --member serviceAccount:$PROJECT_NUMBER-compute@developer.gserviceaccount.com \
  --role roles/secretmanager.secretAccessor
gcloud run services update finbot-demo --region $REGION \
  --update-secrets FINBOT_OPENAI_API_KEY=finbot-demo-openrouter:latest \
  --update-env-vars FINBOT_DEMO_WRITER=live,FINBOT_LLM_PROVIDER=openai,FINBOT_MODEL=meta-llama/llama-3.3-70b-instruct,FINBOT_OPENAI_BASE_URL=https://openrouter.ai/api/v1,FINBOT_DEMO_LIVE_NAME=Llama\ 3.3\ 70B,FINBOT_DEMO_LIVE_DAILY=100,FINBOT_DEMO_LIVE_PER_CLIENT=5
```

The server also caps live answers itself: `FINBOT_DEMO_LIVE_DAILY` per UTC day per instance
(default 100; with `--max-instances 3` at most three times that) and `FINBOT_DEMO_LIVE_PER_CLIENT`
per visitor per hour (default 5), with at most 400 output tokens per call and repeated requests
served from a cache. These counts live in memory and restart with an instance, so the key's
credit limit is the hard ceiling. When a cap is reached or the provider fails, the scripted writer answers and
the page says so. To turn the live writer off again:
`gcloud run services update finbot-demo --region $REGION --update-env-vars FINBOT_DEMO_WRITER=scripted`.

## Any other container host

Fly.io, Render, Railway and similar hosts work the same way: build `deploy/demo/Dockerfile`,
let the host set `PORT`, and set `FINBOT_DEMO_PUBLIC_HOST` to the public HTTPS hostname. The host
must terminate TLS; the server sends HSTS when a public hostname is set and accepts only
`https://<public host>` as the request origin.

## What the public mode changes

- `--host` / `FINBOT_DEMO_BIND` chooses the interface (the image uses `0.0.0.0`).
- `--public-host` / `FINBOT_DEMO_PUBLIC_HOST` adds one HTTPS origin to the two loopback ones.
  Other Host headers and cross-site origins are still refused, which keeps DNS-rebinding
  protection.
- More than 32 requests in flight at once get `503` with `Retry-After` instead of piling up threads.
- Everything else is unchanged: synthetic data only, 8 KB request limit, strict CSP.
