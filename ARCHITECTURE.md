# AcuSchedule — Adyen platform integration

Demo project built to explore Adyen for Platforms — sub-merchant onboarding, split payments, and webhook-driven KYC state management.

AcuSchedule is a fictional scheduling and payments platform for acupuncturists. It demonstrates Adyen for Platforms: each acupuncturist is a sub-merchant who onboards via the Balance Platform API, and patient payments are split at authorization between the practitioner's balance account and the platform.

---

## Why this architecture

This project is intentionally scoped to demonstrate two things an implementation engineer needs to understand deeply:

1. The difference between a direct merchant integration and a platform/PayFac integration
2. That a platform's payment system is event-driven, not request-response — KYC verification and payment outcomes both arrive asynchronously via webhook, which means local state is required

The naive approach (stateless Flask routes that call Adyen and return responses) breaks down because:
- KYC verification can take up to 48 hours — you can't block a signup request waiting for it
- An account holder's capability status can change at any time (periodic data reviews, risk flags, document expiry), not just at signup
- Without local state, you cannot enforce "only allow payments for verified sub-merchants"
- Without local state, you have no practitioner dashboard, no audit trail, nothing

The solution is to model each practitioner as a local entity with an explicit status field, and let webhooks drive all state transitions.

---

## Tech stack

| Layer | Choice | Notes |
|---|---|---|
| Language | Python 3.x | |
| Framework | Flask | Lightweight, matches Adyen's Python example repo |
| ORM | SQLAlchemy | Clean model layer, easy swap from SQLite to Postgres |
| Database | SQLite (dev) / PostgreSQL (deployed) | SQLite for local; Railway/Render add-on for deploy |
| Adyen library | adyen-python-api-library v12.5+ | `pip install Adyen` |
| Frontend | Vanilla HTML/JS + Adyen Web Drop-in v5.68 | No framework needed |
| Config | python-dotenv | `.env` file, never committed |
| Deployment | Railway or Render | Required for live webhooks — ngrok acceptable for local dev |

---

## Two-layer architecture

### Layer 1 — Balance Platform API (onboarding)

Handles sub-merchant onboarding and KYC. Called when an acupuncturist signs up.

Three sequential API calls:

```
POST /legalEntities          → returns legalEntityId
POST /accountHolders         → returns accountHolderId
POST /balanceAccounts        → returns balanceAccountId
```

All three IDs are stored locally on the `practitioners` table. KYC then runs asynchronously at Adyen. Your app listens for the result via webhook.

### Onboarding approach: API-driven vs Hosted

Adyen offers two onboarding paths. AcuSchedule uses **API-driven onboarding** — the platform makes explicit calls to `/legalEntities`, `/accountHolders`, and `/balanceAccounts` and owns the UI at every step.

The alternative is **Hosted Onboarding** — the platform redirects the sub-merchant to an Adyen-hosted KYC form, Adyen handles all data collection and document upload, and webhooks the result back when complete. This is what Adyen recommends for most platforms and is what the official `adyen-afp-sample` reference implementation uses.

| | API-driven (this project) | Hosted Onboarding |
|---|---|---|
| UI ownership | Platform builds and controls the form | Adyen hosts the form |
| Code complexity | Higher — three sequential API calls, state management | Lower — redirect URL + webhook handler |
| Compliance surface | Higher — platform handles data collection | Lower — Adyen handles data collection |
| UX control | Full control over look, feel, pre-population | Limited to Adyen's hosted UI |
| Best for | Platforms with specific UX needs or existing user data to pre-populate | Most platforms — faster to build, less risk |

**Why API-driven for this demo:** It exposes the full data model and sequencing dependencies — legal entity → account holder → balance account — making the architecture explicit and easy to reason about. In a production recommendation for most platforms, Hosted Onboarding would be the right default, with API-driven reserved for platforms that need full UX control or need to pre-populate KYC data from an existing user profile.

### Layer 2 — Checkout API (payments)

Handles patient payments. Called when a patient books and pays.

One API call, with a `splits` field:

```
POST /sessions               → returns sessionId + sessionData
```

The splits field routes funds at authorization:
- Sub-merchant's balance account gets the treatment fee (e.g. $85)
- Platform's balance account gets the commission (e.g. $5)
- Remainder covers Adyen processing fees

Payment outcome arrives via `AUTHORISATION` webhook.

---

## Data model

> See [DATA_MODEL.md](./DATA_MODEL.md) for the full ER diagram and state machine diagram in Mermaid format.

```
practitioners
─────────────────────────────────────────
id                  uuid  (primary key)
name                string
email               string
legal_entity_id     string   ← from Adyen POST /legalEntities
account_holder_id   string   ← from Adyen POST /accountHolders
balance_account_id  string   ← from Adyen POST /balanceAccounts
status              enum     ← pending_kyc | active | suspended
created_at          timestamp
updated_at          timestamp
```

### Status state machine

```
[signup submitted]
        ↓
  pending_kyc     ← local record created, Adyen IDs stored
        ↓
  KYC webhook fires: balancePlatform.accountHolder.updated
        ↓
  active           ← receivePayments capability confirmed
        ↓
  suspended        ← risk webhook fires, or periodic review fails
```

The `status` field is the single source of truth for whether a practitioner can accept payments. It is only ever updated by the KYC webhook handler, never by the onboarding route directly.

---

## Routes

### Onboarding (`routes_onboard.py`)

```
GET  /signup                          → signup form
POST /api/onboard/legal-entity        → POST /legalEntities to Adyen
POST /api/onboard/account-holder      → POST /accountHolders to Adyen
POST /api/onboard/balance-account     → POST /balanceAccounts to Adyen
```

These three are called in sequence from the frontend after the practitioner submits the signup form. Each stores the returned Adyen ID on the local practitioner record.

### Payments (`routes_payments.py`)

```
GET  /checkout                        → checkout page (requires active practitioner)
POST /api/sessions                    → POST /sessions to Adyen, with splits
GET  /result                          → payment result page
```

The `/api/sessions` route guards on `practitioner.status == "active"` before calling Adyen. Returns 403 if not verified.

### Webhooks (`routes_webhooks.py`)

```
POST /api/webhooks/kyc                → handles balancePlatform.accountHolder.updated
POST /api/webhooks/notifications      → handles AUTHORISATION payment events
```

Both routes verify the HMAC signature before processing. The KYC handler drives the status state machine. The notifications handler logs the payment outcome and updates any local order record.

---

## File structure

```
acuschedule/
├── app/
│   ├── __init__.py              Flask app factory
│   ├── models.py                Practitioner model, status enum
│   ├── db.py                    SQLAlchemy setup, helper queries
│   ├── routes_onboard.py        Signup + Balance Platform API calls
│   ├── routes_payments.py       Sessions + result page
│   ├── routes_webhooks.py       KYC + AUTHORISATION webhook handlers
│   └── templates/
│       ├── signup.html          Practitioner signup form
│       ├── checkout.html        Drop-in UI, calls /api/sessions
│       └── result.html          Payment confirmation page
├── .env                         Never committed
├── .gitignore
├── requirements.txt
├── ruff.toml
├── run.py                       Entry point, port 8080
├── ARCHITECTURE.md              Technical design rationale
├── DATA_MODEL.md                ER diagram and state machine (Mermaid)
└── README.md
```

---

## Environment variables

```bash
ADYEN_API_KEY=                     # ws@ credential — Checkout API (server-side only)
ADYEN_CLIENT_KEY=                  # client-side key — Drop-in UI (safe to expose in browser)
ADYEN_MERCHANT_ACCOUNT=            # e.g. MauraMauraStudioECOM
ADYEN_HMAC_KEY=                    # webhook HMAC signing key
ADYEN_BALANCE_PLATFORM_API_KEY=    # ws@BalancePlatform credential — Configuration API
ADYEN_LEM_API_KEY=                 # ws@Scope credential — Legal Entity Management API
ADYEN_BALANCE_PLATFORM_ID=         # from ws credential username — requires Balance Platform access
PLATFORM_BALANCE_ACCOUNT_ID=       # your platform's own liable balance account for commission
DATABASE_URL=                      # sqlite:///dev.db or postgresql://...
```

---

## Deployment

### Local dev with ngrok

Webhooks require a public URL. For local development:

```bash
ngrok http 8080
# copy the https URL → set as webhook URL in Adyen Customer Area
```

### Production deploy (Railway or Render)

Both support Flask + PostgreSQL with minimal config:

1. Push repo to GitHub
2. Create new project on Railway or Render, connect repo
3. Add PostgreSQL add-on → copy `DATABASE_URL` into env vars
4. Add all other env vars
5. Deploy
6. Update webhook URL in Adyen Customer Area to the live domain

Set `DATABASE_URL` to the Postgres connection string and SQLAlchemy will switch automatically — no code changes needed.

---

## Webhook setup in Customer Area

Two webhooks required, both under `Developers → Webhooks`:

| Type | URL | Events |
|---|---|---|
| Standard webhook | `/api/webhooks/notifications` | AUTHORISATION |
| Balance Platform webhook | `/api/webhooks/kyc` | balancePlatform.accountHolder.updated |

Enable HMAC signing on both. Copy the HMAC keys into `.env`.

The full Balance Platform webhook surface is larger than just these two. Your webhook handler should acknowledge (return `[accepted]`, 202) any event it receives, even ones it doesn't process, so Adyen doesn't retry them. Relevant events to be aware of:

| Webhook | When it fires |
|---|---|
| `balancePlatform.accountHolder.created` | Account holder created |
| `balancePlatform.accountHolder.updated` | KYC capability status changed ← your state machine trigger |
| `balancePlatform.balanceAccount.created` | Balance account created |
| `balancePlatform.balanceAccount.updated` | Balance account updated |
| `balancePlatform.transfer.created` | Fund movement initiated |
| `balancePlatform.transfer.updated` | Fund movement status updated |
| `balancePlatform.transaction.created` | Transaction recorded on a balance account |

For the demo, only `balancePlatform.accountHolder.updated` drives state transitions. The rest should be logged and acknowledged.

---

## Complete onboarding sequence (production)

The three-step API sequence (legal entity → account holder → balance account) is the minimum for a sandbox demo. A production-complete onboarding flow has additional steps from the LEM API:

```
1. POST /legalEntities              → create legal entity, get legalEntityId
2. POST /businessLines              → define business type (required for KYC)
3. POST /transferInstruments        → add bank account for payouts
4. POST /accountHolders             → create account holder, link legal entity
5. POST /balanceAccounts            → create balance account
6. POST /legalEntities/{id}/termsOfService   → get Adyen ToS document
7. PATCH /legalEntities/{id}/termsOfService  → accept ToS (required before go-live)
8. POST /documents                  → upload verification documents if requested
   ↓
   KYC runs asynchronously
   ↓
9. balancePlatform.accountHolder.updated webhook → status flips to active
10. POST /balanceAccounts/{id}/sweeps → configure payout schedule
```

Steps 2, 3, 6, 7, and 8 are omitted from the demo for scope. They should be noted in the README as production completion steps.

---

## Payouts — how sub-merchants actually get paid

Payouts from a practitioner's balance account to their bank are handled via **sweeps** — scheduled rules configured on the balance account after onboarding completes.

```python
# POST /balanceAccounts/{balanceAccountId}/sweeps
{
    "counterparty": {
        "transferInstrumentId": "SE5721111111111111"  # their bank account
    },
    "currency": "USD",
    "schedule": {
        "type": "weekly",
        "dayOfWeek": "FRIDAY"
    },
    "type": "pull",
    "description": "Weekly payout to practitioner"
}
```

This means: every Friday, sweep the practitioner's available balance to their bank account. Adyen fires `balancePlatform.transfer.created` and `balancePlatform.transfer.updated` webhooks as the payout processes.

For the demo, sweeps are not implemented — practitioners accumulate a balance but no payout is triggered. This is worth documenting explicitly in the README as a known gap.

---

## Test cards

Use Adyen's test card numbers to simulate payments:

| Card | Number | Result |
|---|---|---|
| Visa (success) | 4111 1111 1111 1111 | Authorised |
| Mastercard (success) | 5500 0000 0000 0004 | Authorised |
| Any card (refused) | 4000 0000 0000 0002 | Refused |

Any future expiry date, any CVC.

---

## Design rationale

**Why platform over direct merchant?**
AcuSchedule models the PayFac pattern — a platform that enables sub-merchants to accept payments rather than processing payments directly. This requires two separate API layers: Balance Platform for sub-merchant onboarding and account management, and Checkout API for payment sessions with split routing. A direct merchant integration (single merchant account, no splits) would be simpler but wouldn't demonstrate the platform architecture.

**Why a state machine for practitioner status?**
KYC is asynchronous and capability status can change at any time — not just at signup, but during periodic reviews, risk flag events, or document expiry. Without local state you cannot enforce payment eligibility or build any practitioner-facing UI. The state machine is the minimum correct model for an async compliance system.

**Why split routes_webhooks.py out separately?**
Webhooks are the only place state transitions happen. Keeping them in a dedicated module makes it obvious where the system's source of truth lives, and makes it easy to add retry logic, dead-letter handling, or a task queue later without touching payment or onboarding routes.

**Why deploy rather than localhost?**
Webhooks require a public URL. Deploying means the KYC async flow and AUTHORISATION confirmation actually work end-to-end — the state machine is live, not mocked. ngrok is acceptable for local development but the URL changes on every restart, which makes it impractical for sustained testing.

**Why Sessions flow over Advanced flow?**
AcuSchedule payments are straightforward — fixed appointment fee, no manipulation needed between payment steps, Drop-in UI is acceptable, and 3DS2 native flow is sufficient. Sessions flow is Adyen's recommended default and handles 3DS2 automatically. Advanced flow would be appropriate if the platform needed redirect 3DS2, custom UI via Components, or server-side control at each payment step.

**Why API-driven onboarding over Hosted Onboarding?**
See the onboarding approach comparison table above. API-driven exposes the full data model and sequencing dependencies explicitly. Hosted Onboarding is the right production default for most platforms — it reduces compliance surface and development time.

**Production upgrade path:**
- SQLite → PostgreSQL (change DATABASE_URL)
- Synchronous webhook handling → Celery + Redis task queue (so slow DB writes don't block webhook ACK to Adyen)
- Single Flask process → gunicorn with multiple workers

---

## Scaling to 20x

"Design for 20x" is an Adyen Formula principle — build systems that can handle 20 times current load without fundamental redesign. The demo is explicitly not designed for 20x, with a clear upgrade path documented below.

### What is NOT 20x-ready in the demo

**Synchronous webhook handling** — the most critical gap. The webhook handler currently processes the event, writes to the database, and then returns 200 to Adyen in the same request. At 20x load, slow database writes cause Adyen timeouts and retries, which compound the load further. Every retry adds another event to process, making the problem worse under pressure.

**SQLite** — single-writer database. Handles one write at a time. Falls over under any real concurrency. Already flagged as a known gap.

**Single Flask process** — `python run.py` runs one thread. A single slow request blocks all others.

**No idempotency store** — at 20x load, duplicate webhook delivery becomes likely. Without a processed event log, the same payment confirmation could be processed twice.

**No connection pooling** — SQLAlchemy's default pool is sized for low traffic. Under load, connection exhaustion causes requests to queue or fail.

### What IS 20x-ready

The state machine architecture is sound at scale:
- Webhook-driven — the app never polls Adyen, it only reacts
- Status transitions are idempotent by nature — processing the same KYC webhook twice has no bad effect
- The data model is normalized — no denormalized state that gets inconsistent under concurrent writes
- Routes are separated by concern — scaling the webhook handler independently of the payment routes is straightforward

### The upgrade path to 20x

**Step 1 — Task queue in front of webhook handlers**

Return 200 immediately, process asynchronously:

```python
# Current (synchronous — blocks until DB write completes)
@webhooks.route("/api/webhooks/kyc", methods=["POST"])
def kyc_webhook():
    process_kyc_event(request.get_json())  # slow
    return "[accepted]", 202

# 20x-ready (enqueue immediately, process in background worker)
@webhooks.route("/api/webhooks/kyc", methods=["POST"])
def kyc_webhook():
    celery_app.send_task("tasks.process_kyc_event", args=[request.get_json()])
    return "[accepted]", 202  # Adyen gets this in milliseconds
```

**Step 2 — Idempotency store**

```python
# Before processing any webhook event, check if already handled
def process_kyc_event(payload):
    event_id = payload.get("data", {}).get("id")
    if ProcessedEvent.query.filter_by(event_id=event_id).first():
        return  # already handled — skip
    # process...
    db.session.add(ProcessedEvent(event_id=event_id))
    db.session.commit()
```

**Step 3 — PostgreSQL with connection pooling**

```python
# SQLAlchemy pool config for production
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
    "pool_size": 10,
    "pool_timeout": 30,
    "pool_recycle": 1800,
    "max_overflow": 20,
}
```

**Step 4 — gunicorn with multiple workers**

```bash
gunicorn "app:create_app()" --workers 4 --bind 0.0.0.0:8080
```

**Step 5 — Separate worker process for Celery**

```bash
celery -A tasks worker --loglevel=info --concurrency=4
```

---

## Go-live checklist

Source: https://docs.adyen.com/online-payments/go-live-checklist

**Important:** Test Customer Area settings are not copied to live — everything below must be reconfigured in the live Customer Area at `ca-live.adyen.com`.

### Account
- Create additional merchant accounts if needed
- Create separate users for each team member with appropriate roles
- Set up Customer Area notifications for chargebacks and fraud
- Enable two-factor authentication

### Finance
- Add bank account details for Adyen payouts
- Set up automatic report generation for reconciliation
- Use the Settlement details report for transaction-level reconciliation
- Consider setting up a Reserve for refunds and operational expenses

### Risk and compliance
- Review and customize your risk profile
- Set up notifications for Fraudulent Payments (NOF) and Chargebacks (NOC)
- Include required risk fields in payment requests
- Complete PCI DSS requirements
- Protect against card testing / BIN attacks
- Confirm 3DS2 support for PSD2 SCA compliance
- Note: Mastercard 3DS enrollment can take up to 12 hours after live activation

### API communication
- Generate a new API key in the live Customer Area
- Update all Adyen endpoints from test to live endpoints
- Verify API credentials have required permissions
- Configure `additionalData` settings to match test environment

### Webhooks
- Re-create webhooks in the live Customer Area
- Verify webhook acknowledgement returns 200/202 promptly
- Confirm all required webhook event types are configured
- Note: use 202 (not just 200) to prevent events being queued

### End-to-end testing with real payments
- Test on real iOS and Android devices — browser emulation does not simulate real touch events
- Use `http://127.0.0.1` or `http://localhost` for local testing (treated as secure by browsers)
- For each payment method: make a successful payment with real details
- Test a refused payment (incorrect card details)
- Test a fraud-triggered refusal (risk score above 100)
- Test a refund and partial refund
- Test redirect payment method edge cases: wait 5+ min, cancel, close browser
- Test 3DS2 success and failed challenge scenarios
- If using manual capture: test capture and cancel flows
- If using tokenization: test token creation, token payment, and zero-auth

---

## Testing (nice to have)

Aligns with the Adyen Formula principle of engineer ownership — build, test, and on-call are the same person. Even a small test suite signals production awareness.

### Planned test file structure

```
tests/
├── conftest.py          Flask test client + DB setup/teardown
├── test_sessions.py     POST /api/sessions — happy path, unverified practitioner
├── test_onboard.py      POST /api/onboard/* — request shape validation
└── test_webhooks.py     POST /api/webhooks/kyc — status transitions
```

### Install

```bash
pip install pytest pytest-flask
pip freeze > requirements.txt
```

### Key test cases

**`test_sessions.py`**
- Verified practitioner (`status=active`) → sessions route calls Adyen, returns `sessionId` and `sessionData`
- Unverified practitioner (`status=pending_kyc`) → sessions route returns 403 before touching Adyen
- Unknown practitioner ID → returns 404

**`test_webhooks.py`**
- Valid KYC webhook with `receivePayments.enabled=true` → practitioner status flips to `active`
- Valid KYC webhook with `receivePayments.enabled=false` → practitioner status flips to `suspended`
- Webhook with invalid HMAC → returns 401, no state change

**`test_onboard.py`**
- Missing required fields → returns 400
- Valid request body shape → correct structure passed to Adyen (mock Adyen client)

### Running tests

```bash
pytest tests/ -v
```

### Mocking Adyen

Use `unittest.mock.patch` to mock the Adyen client so tests don't make real API calls:

```python
from unittest.mock import patch, MagicMock

def test_sessions_active_practitioner(client, active_practitioner):
    mock_result = MagicMock()
    mock_result.message = {"id": "CS123", "sessionData": "Ab02b4c.."}

    with patch("app.routes_payments.adyen.checkout.payments_api.sessions",
               return_value=mock_result):
        response = client.post("/api/sessions",
                               json={"practitionerId": active_practitioner.id})
        assert response.status_code == 200
        assert "sessionData" in response.get_json()
```

### Priority order

Build tests after the core integration is working, not before. Priority:
1. `test_webhooks.py` — highest value, tests the state machine which is the core architectural decision
2. `test_sessions.py` — tests the payment eligibility guard
3. `test_onboard.py` — lowest priority, mostly validates request shape
