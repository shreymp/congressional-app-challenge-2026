# callma. manual blocking and reporting

After a call, a user can manually block a number for their own account and optionally report it. The ring worker checks the same persistent database before sending the next incoming-call invite. A block disconnects that incoming LiveKit room without ringing the app. Detector scores never create blocks.

A report stays pending until a separately authorized reviewer decides whether to add the number to the shared block list. Shared blocks apply to every recipient using this database and can be removed. One user's report does not immediately block a number for everyone: caller ID can be spoofed, and a report or model flag can be wrong.

## Configuration

Run `safety_service.py` separately from the voice agent. It uses only the Python standard library.

1. Choose a private persistent database path outside the repository, in a directory accessible only to the service account. Configure `CALLMA_SAFETY_DB` to that same absolute path in the HTTP service and every ring-worker process. A shared/network filesystem is not supported; this is one SQLite-backed deployment, not a distributed block service.
2. Set `CALLMA_SAFETY_TOKENS_JSON` in the HTTP service environment to a JSON object mapping independently generated, random bearer tokens to user IDs. Tokens must have at least 32 characters. A user ID must match that recipient's `SENIOR_IDENTITY`, currently `senior` in the existing single-recipient setup. The service does not derive identity from a submitted request body.
3. Optionally set an independent `CALLMA_SAFETY_ADMIN_TOKEN` in the HTTP service only. Never ship this token to the app. It authorizes human-reviewed shared blocks; ordinary user tokens cannot write that list.
4. Start the service: `python safety_service.py --db /private/persistent/callma-safety.sqlite3`. The default listener is `127.0.0.1:8010`. Put it behind an authenticated HTTPS-capable reverse proxy for a real device; no deployment or TLS certificate is created by this change.
5. Provision the native app's `CALLSHIELD_SAFETY_BASE_URL` and per-user `CALLSHIELD_SAFETY_TOKEN` through its build configuration and Info.plist. These are separate from LiveKit credentials.

The database file is set to owner read/write permissions. Back it up and protect the containing directory. Do not put the database, tokens, or report notes in Git. No audio or transcript is accepted or stored by this service.

## HTTP contract

All `/v1/` routes require `Authorization: Bearer <token>`. Responses use JSON and `Cache-Control: no-store`. Numbers must include an international country code, for example `+15551234567`; harmless formatting punctuation is removed, but a country is never guessed.

| Method and path | Request | Result |
|---|---|---|
| `GET /v1/blocks` | none | `{blocks:[{number,scope,createdAt,reason}],reports:[{id,number,category,status,createdAt}]}` |
| `POST /v1/blocks` | `{number,reason?,report?:false,category?:"scam"}` | `201 {block:{...},report:{...}\|null}`; personal manual block, optional pending report |
| `DELETE /v1/blocks/{encodedNumber}` | none | `200 {removed:true\|false}`; removes only that user's personal block |
| `POST /v1/reports` | `{number,category?:"scam",notes?:""}` | `201 {report:{...}}`; report alone never blocks |
| `POST /v1/admin/shared-blocks` | `{number,reason,reportId?}` | `201 {block:{...}}`; separate admin token and nonempty review reason required |
| `DELETE /v1/admin/shared-blocks/{encodedNumber}` | none | `200 {removed:true\|false}`; separate admin token required |

`scope` is `personal` or `shared`; `status` is `pending` or `reviewed`; `category` is `scam`, `spam`, or `other`. `createdAt` is Unix seconds. The list contains only the authenticated user's reports, plus the shared and personal blocks that affect them. Repeating a pending report for the same number/category returns its existing ID. A combined block/report request rolls back completely when validation fails.

Use `%2B15551234567` for the example number in a DELETE path. User mutations are limited to 30 per minute, personal blocks to 1,000 per user, and request bodies to 4 KB. Invalid data returns 400, missing/incorrect credentials 401, excessive body size 413, a mutation rate limit 429, and a temporary store failure 503. `/health` is public and contains only `{ok:true}`.

## Incoming-call behavior and limits

- Missing configuration leaves existing ringing behavior unchanged. Anonymous/invalid caller IDs do not match any wildcard.
- Lookup errors or timeouts allow ringing, with a diagnostic message that includes no number or token. A service failure must not silently reject an ordinary call.
- An explicit block prevents the invite and retries room deletion at most three times. A failed disconnect is reported as `cleanup_failed`; it is not claimed successful.
- Blocking takes effect on the next incoming call; it does not end the call during which the user saw a warning.
- This deployment cannot independently prove caller identity. A shared list needs human review, correction, removal, and a deployment-specific abuse process before broad use.
- No guardian notification queue, SMS provider, or push service is implemented here. The native app's user-controlled message composer can prepare a guardian notice; no real message was sent during implementation or testing.

## Verification

`python -m unittest -v test_safety_service.py` exercises persistence, user isolation, pending reports, shared review/removal, validation, transaction rollback, and the real loopback HTTP contract. `python test_senior_ring.py` includes personal/shared database-to-ring enforcement, blocked-call cleanup, and lookup-failure recovery using a fake call transport. These are automated checks, not live telephone-carrier or deployed-server validation.
