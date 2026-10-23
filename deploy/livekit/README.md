# CAC hosted inference deployment

This deploys the existing `CA_KKXaPczWhqpE` worker as `scam-guard`. It runs
the released real deepfake model, local Vosk, caller-only JEV V2 and the Node
connector inside the cloud container. The Mac and app are not required to run
these services. Native phone answering still requires an audio participant.

The Docker build downloads exact checksum-verified releases. `prepare.py` uses
the repository's read token to obtain short-lived model download redirects.
Only those expiring URLs go to LiveKit's build service, never the GitHub token.
They are present only in the intermediate model build stage, which is not copied
into the final image. The final image contains the verified model files and a
cached backbone architecture config; no model downloads occur during a call.

The model server binds only to loopback. Jobs use its real deepfake endpoint,
so the large weights are shared across calls instead of duplicated for each job.
Startup checks require deepfake warm-up, real JEV inference through the connector,
and a successful Vosk load before the worker starts registering. A crashed model
service terminates the worker so LiveKit can restart it. Audio recording is off.

The image also bundles a mono 16 kHz PCM announcement, generated at build time with
eSpeak NG and SoX: **"This call is being recorded."** Startup and image checks reject
a missing, silent or invalid clip. Immediately after the senior answers, the worker
publishes that clip into the call room and waits for playback to finish before it
opens the caller's analysis/recording stream. If playback fails, analysis and recording
stay off for that call while the normal call and hang-up supervisor continue.
The disclosure does not itself collect consent or enable audio storage. Verify both
phones hear the full sentence on a real PSTN test; the backend inference probe skips it.

## Deploy

1. Authorize the deployment environment for project **CAC** using `lk cloud auth`.
   This creates a project API key; approval is required before granting that access.
2. For the GitHub deployment workflow, configure repository Actions secrets
   `LIVEKIT_URL`, `LIVEKIT_API_KEY`, and `LIVEKIT_API_SECRET` for that project.
   These are used only for deployment/probing; the hosted container receives its
   own LiveKit credentials automatically. Do not commit any keys.
3. Merge the reviewed workflow/code and run **LiveKit real models** from Actions
   with **deploy=true**. It first builds and exercises actual models, then submits
   a fresh build context to LiveKit, updates the existing worker and runs an audio
   probe against the deployed worker. A test failure must block the deployment.
4. Verify the new version's commit in LiveKit, inspect startup logs for all
   readiness checks, and require **BACKEND PROBE PASSED** from the deployed probe.
   The probe sends the checked-in speech fixture through the actual cloud job and
   requires both a real voice risk update and fresh transcript probability.
   Right after a deploy the previous version can still take jobs for a short time and
   never answers the probe, so the workflow retries with a fresh room (up to 6 x 90 s).
   To re-test production without rebuilding or redeploying, run the workflow with
   **probe_only=true**.

The cloud validation job also runs on this PR without deployment credentials.
It uses the existing repository-scoped GitHub Actions token to read release assets.
Neither the tests nor a successful image build alone prove a deployment occurred.

Manual equivalent from a configured checkout:

```sh
python3 deploy/livekit/prepare.py --output .cloud-context
lk --project CAC agent deploy .cloud-context --id CA_KKXaPczWhqpE --deployment production \
  --secrets DETECTOR=remote --secrets TRANSCRIPT_ENABLED=1 --secrets RECORD_CALLER_AUDIO=0
python3 deploy/livekit/probe.py ios/ScamTranscriptTests/Fixtures/bank.wav
```

`prepare.py` needs a temporary `GH_TOKEN` with read access to this repository's
release assets. The deployment CLI needs the authorized CAC project credentials.
Delete `.cloud-context` after use; it is ignored by Git and contains expiring links.
The cloud builder must be able to reach GitHub release assets, PyPI, PyTorch,
Hugging Face (architecture config only) and the Vosk model host. If a build fails,
the previous version continues serving; do not report the new models as deployed.

## Probe isolation and limits

Only a room whose name begins `backend-probe-` and whose API-created dispatch
metadata is exactly `cac-backend-probe-v1` uses the diagnostic path. It waits for
`backend-probe-caller` and skips senior-app ringing. Normal phone calls still
require a SIP caller and use the existing ring/hang-up supervisor. The probe
deletes only its own randomly named room and never sends app invitations.

CPU latency, concurrency and memory must be checked against the deployment plan
using the real model test and deployed probe. A finite score proves that inference
ran, not model accuracy or threshold calibration. A real incoming PSTN call is
still needed to validate telephone routing/audio with the eventual app.

