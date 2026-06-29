
A scheduling and payments platform for acupuncturists, built on [Adyen for Platforms](https://docs.adyen.com/platforms).

---

## How it works

### Practitioner onboarding

When an acupuncturist signs up, the platform makes three sequential calls to Adyen's Balance Platform API to create their legal entity, account holder, and balance account. Their local record is created with status `pending_kyc`.

KYC verification runs asynchronously at Adyen. When it completes, Adyen sends a `balancePlatform.accountHolder.updated` webhook. The platform updates the practitioner's status to `active` (or `suspended` if verification fails). Only `active` practitioners can accept payments.

### Patient payments

When a patient pays for a session, the platform creates an Adyen payment session with a `splits` field that routes funds at authorization:

- Practitioner's balance account receives the treatment fee
- Platform's balance account receives the commission
- Remainder covers Adyen processing fees

The patient completes payment via Adyen's Drop-in UI. The platform receives an `AUTHORISATION` webhook confirming the outcome.

---

## Tech stack

- Python 3.x / Flask
- SQLAlchemy + SQLite (dev) / PostgreSQL (production)
- Adyen Python API Library v12.5+
- Adyen Web Drop-in v5.68

---

## Requirements

- Python 3.6+
- An Adyen test account — [sign up here](https://www.adyen.com/signup)
- API key, Client key, and Merchant account from your [Customer Area](https://ca-test.adyen.com/)
- Balance Platform access and HMAC key (configured in Customer Area under `Developers → Webhooks`)

---

## Local setup

```bash
git clone https://github.com/mauratee/acuschedule
cd acuschedule
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

Copy `.env.example` to `.env` and fill in your credentials:

```bash
cp .env.example .env
```

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

Run the app:

```bash
python run.py
```

Visit `http://localhost:8080` in your browser.

### Webhooks (local dev)

Adyen webhooks require a public URL. Use [ngrok](https://ngrok.com) to expose your local server:

```bash
ngrok http 8080
```

Copy the `https://` URL and set it as your webhook endpoint in the Customer Area under `Developers → Webhooks`. You need two webhooks:

| Type | Path | Events |
|---|---|---|
| Standard webhook | `/api/webhooks/notifications` | AUTHORISATION |
| Balance Platform webhook | `/api/webhooks/kyc` | balancePlatform.accountHolder.updated |

---

## GitHub Codespaces

You can run AcuSchedule entirely in GitHub Codespaces without any local setup.

**1. Add allowed origin in Customer Area**

Before launching, go to `Developers → API credentials → Client settings → Allowed origins` and add:
```
https://*.github.dev
```

**2. Set Codespaces secrets**

In your forked repo go to `Settings → Secrets and variables → Codespaces` and add:
- `ADYEN_API_KEY`
- `ADYEN_CLIENT_KEY`
- `ADYEN_MERCHANT_ACCOUNT`
- `ADYEN_HMAC_KEY`

**3. Launch the Codespace**

Click the **Code** button on the repo → **Codespaces** → **Create codespace on main**.

**4. Configure the webhook URL**

Once running, go to the **Ports** tab in VS Code, copy the forwarded address for port 8080, and set your webhook URL in the Customer Area to:
```
https://<your-codespace-name>-8080.preview.app.github.dev/api/webhooks/notifications
```

Make sure the port visibility is set to **Public** in the Ports tab, otherwise Adyen can't reach it.

Full instructions: [Adyen examples Codespaces guide](https://github.com/adyen-examples/.github/blob/main/pages/codespaces-instructions.md)

---

## Deployment

To deploy your own instance:

1. Fork this repo
2. Create a new project on [Railway](https://railway.app) or [Render](https://render.com)
3. Add a PostgreSQL add-on and set `DATABASE_URL` in env vars
4. Add all other env vars from `.env.example`
5. Deploy and update your webhook URLs in the Customer Area

---

## Test payments

Use [Adyen's test card numbers](https://docs.adyen.com/development-resources/testing/test-card-numbers):

| Card | Number | Result |
|---|---|---|
| Visa | 4111 1111 1111 1111 | Authorised |
| Mastercard | 5500 0000 0000 0004 | Authorised |
| Refused | 4000 0000 0000 0002 | Refused |

Any future expiry date, any 3-digit CVC.

---

## Project structure

```
acuschedule/
├── app/
│   ├── __init__.py              Flask app factory
│   ├── models.py                Practitioner model, status enum
│   ├── db.py                    SQLAlchemy setup
│   ├── routes_onboard.py        Signup + Balance Platform API
│   ├── routes_payments.py       Sessions flow + result page
│   ├── routes_webhooks.py       KYC + payment webhook handlers
│   └── templates/
│       ├── signup.html
│       ├── checkout.html
│       └── result.html
├── .env.example
├── DATA_MODEL.md                ER diagram and state machine (Mermaid)
├── LICENSE
├── requirements.txt
├── ruff.toml
├── run.py
└── ARCHITECTURE.md              Full design rationale and decision log
```

---

## Resources

- [Adyen for Platforms docs](https://docs.adyen.com/platforms)
- [Sessions flow integration guide](https://docs.adyen.com/online-payments/build-your-integration/sessions-flow)
- [Split payments at authorization](https://docs.adyen.com/platforms/online-payments/split-transactions/split-payments-at-authorization)
- [Adyen Python API library](https://github.com/Adyen/adyen-python-api-library)
- [adyen-examples/adyen-python-online-payments](https://github.com/adyen-examples/adyen-python-online-payments)
