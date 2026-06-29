A scheduling and payments platform for acupuncturists, built on [Adyen for Platforms](https://docs.adyen.com/platforms).

---

## Tech stack

- Python 3.x / Flask
- SQLAlchemy + SQLite (dev) / PostgreSQL (production)
- Adyen Python API Library v12.5+
- Adyen Web Drop-in v5.68

---

## Requirements

- Python 3.6+
- An Adyen test account — [sign up here](https://www.adyen.com/signup)
- API key, Client key, and Merchant account from your [Customer Area](https://ca-test.adyen.com/)
- Balance Platform access and HMAC key (configured in Customer Area under `Developers → Webhooks`)

---

## Local setup

```bash
git clone https://github.com/mauratee/acuschedule
cd acuschedule
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

Copy `.env.example` to `.env` and fill in your credentials:

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

`http://localhost:8080`.

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
├── requirements.txt
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