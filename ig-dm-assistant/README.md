# Instagram DM Assistant

Customer sends an Instagram DM → the system pulls their details from **Apollo.io**
(CRM) and **Shopify** (orders) → **Claude** drafts a reply in your dialect → the
draft appears on your **mobile approval dashboard** (installable PWA with push
notifications) → one tap on ✅ **Approve** sends the reply back through Instagram.

No screenshots, no copy-paste. **Nothing is ever sent without your approval.**

```
Instagram DM ──▶ FastAPI webhook ──▶ Apollo + Shopify lookup (cached 24h)
                                   ──▶ Claude draft (your dialect, JSON out)
                                   ──▶ Dashboard card + Web Push  ──[✅/✏️/⏭]──▶ Meta Send API
```

This implements **Path A (Meta Messaging API, direct)**. To use **Path B
(Respond.io)** instead, swap `app/meta_api.py`: replace `send_text()` with
Respond.io's `POST /contact/{id}/message` and replace the HMAC check with their
webhook token header — everything else is unchanged.

---

## 1. Prerequisites (manual, before deploying)

1. Convert your Instagram account to a **Professional (Business)** account.
2. Link it to a **Facebook Page**.
3. Create a Meta Developer account → create an **App** → add the
   **Messenger API for Instagram** product.
4. Generate a **Page access token** and note the **App Secret**.
5. Request **Advanced Access** for `instagram_manage_messages` and
   `pages_messaging` (App Review — screencast the use case:
   *"human-approved customer support replies"*). Also request the
   **`HUMAN_AGENT`** message tag while you're in review — it lets you reply up
   to 7 days after the customer's last message (the code falls back to it
   automatically when the 24-hour window has closed).
6. Collect API keys: **Anthropic**, **Apollo.io**, **Shopify Admin API token**.

## 2. Configure

```bash
cp .env.example .env
# fill in every value — see comments in the file
python -m app.genkeys   # prints VAPID_PUBLIC_KEY / VAPID_PRIVATE_KEY for Web Push
```

Then edit the two prompt files — **this is what makes the drafts sound like you**:

| File | What goes in it |
|---|---|
| `prompts/business_faq.md` | Business description, product FAQ, refund/shipping policy |
| `prompts/examples.md` | 5–10 real replies you've written (dialect few-shots) |

The app also automatically feeds your 5 most recent **edited** drafts back into
the prompt as corrections, so it keeps getting closer to your voice over time.

## 3. Run

```bash
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Or with Docker: `docker build -t dm-assistant . && docker run --env-file .env -p 8000:8000 -v $(pwd)/data:/app/data dm-assistant`

## 4. Deploy (Railway / Render / any $5 VPS)

- Meta **requires HTTPS** for webhooks — Railway/Render give you TLS for free;
  on a VPS put Caddy or nginx + Let's Encrypt in front.
- Persist the `data/` directory (SQLite lives there) — on Railway/Render attach
  a volume mounted at `/app/data`.
- Set all env vars from `.env.example` in the platform's dashboard.
- Health check endpoint: `GET /healthz`.

### Wire up the Meta webhook

In your Meta App → Messenger API for Instagram → Webhooks:

- **Callback URL**: `https://YOUR-DOMAIN/webhook`
- **Verify token**: the exact value of `META_VERIFY_TOKEN` in your `.env`
- Subscribe to the **`messages`** field.

Meta calls `GET /webhook` once to verify (the app echoes `hub.challenge`), then
POSTs message events. Every POST is verified against `X-Hub-Signature-256`
(HMAC-SHA256 of the raw body with your App Secret) — anything that fails is
rejected with 403. Echoes of our own outbound messages (`is_echo`) are ignored,
and duplicate deliveries are deduplicated by message `mid`.

## 5. The dashboard

Open `https://YOUR-DOMAIN/dashboard`, sign in with `DASHBOARD_PASSWORD`.

- **Inbox** — pending drafts, newest first. Each card: customer name + avatar,
  their message, a 2-line CRM summary (orders, spend, status), Claude's draft.
- **✅ Approve** sends immediately. **✏️ Edit** opens a text box — Send sends
  your version *and logs the correction* (these become future few-shot
  examples). **⏭ Skip** dismisses (you handle it in the IG app).
- **⚠️ flags** — drafts are flagged when the message involves refunds,
  complaints, angry customers, legal topics, amounts above
  `SENSITIVE_REFUND_THRESHOLD`, or whenever Claude isn't confident.
- **Live updates** via SSE — new cards appear without refreshing.
- **History** tab shows sent / edited / skipped drafts.

### Install as an app + push notifications

- **Android/desktop Chrome**: "Install app" from the browser menu, then tap 🔔.
- **iOS**: Share → **Add to Home Screen** first — iOS only allows Web Push for
  PWAs launched from the home screen (iOS 16.4+). Open the installed app, tap
  🔔, allow notifications. Your phone now buzzes when a new draft arrives even
  with the app closed.

## 6. Safety rules (enforced in code)

- Nothing is sent without an explicit Approve/Send tap.
- The system prompt forbids promising refunds, discounts, or delivery dates
  unless the data came from Shopify order records.
- Sensitive topics force the ⚠️ flag via keyword heuristics *in addition to*
  Claude's own judgment — either one is enough to flag.
- Customer message bodies are never logged at info level.

## 7. Milestone map (matches the build plan)

| Milestone | Where it lives |
|---|---|
| M1 webhook + live dashboard | `app/main.py` (`/webhook`), `app/events.py` (SSE) |
| M2 Claude drafting + approve/edit/skip + sending | `app/drafting.py`, `app/main.py` (draft actions), `app/meta_api.py` |
| M3 Apollo + Shopify enrichment | `app/enrichment.py` (24h cache in `customer_cache`) |
| M4 storage, edit-logging, 24h window, ⚠️ flags | `app/db.py`, `drafts` table, `meta_api.send_text`, `drafting.heuristic_flags` |
| M5 auto-approve whitelist (optional, later) | not built — deliberately, per the safety rules |

## 8. Project layout

```
app/
  main.py        FastAPI app: webhook, dashboard API, SSE, static/PWA
  pipeline.py    inbound queue: store → enrich → draft → broadcast → push
  meta_api.py    signature verify, profile lookup, Send API (24h/HUMAN_AGENT)
  enrichment.py  Apollo + Shopify lookups, 24h cache, CRM summary
  drafting.py    Claude call, system prompt assembly, ⚠️ heuristics
  db.py          SQLite: conversations, messages, drafts, cache, push subs
  auth.py        single-user signed-cookie login
  events.py      in-process SSE broadcaster
  push.py        Web Push (VAPID) sender
  genkeys.py     VAPID keypair generator
  static/        dashboard PWA (index.html, app.js, style.css, sw.js, manifest)
prompts/
  business_faq.md   your business info & policies  ← you fill in
  examples.md       your dialect few-shots          ← you fill in
```
