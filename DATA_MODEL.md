```mermaid
erDiagram
    PRACTITIONERS {
        uuid id PK
        string first_name
        string last_name
        string email
        string legal_entity_id "nullable — from Adyen POST /legalEntities"
        string account_holder_id "nullable — from Adyen POST /accountHolders"
        string balance_account_id "nullable — from Adyen POST /balanceAccounts"
        enum status "pending_kyc | active | suspended"
        timestamp created_at
        timestamp updated_at
    }

    LEGAL_ENTITY {
        string id PK "Adyen-generated"
    }

    ACCOUNT_HOLDER {
        string id PK "Adyen-generated"
    }

    BALANCE_ACCOUNT {
        string id PK "Adyen-generated"
    }

    PRACTITIONERS ||--o| LEGAL_ENTITY : "legal_entity_id stores"
    PRACTITIONERS ||--o| ACCOUNT_HOLDER : "account_holder_id stores"
    PRACTITIONERS ||--o| BALANCE_ACCOUNT : "balance_account_id stores"
```

## Status transitions

```mermaid
stateDiagram-v2
    [*] --> pending_kyc : practitioner signs up
    pending_kyc --> active : KYC webhook — receivePayments enabled
    active --> suspended : risk webhook or periodic review fails
    suspended --> active : KYC remediated
```

## Notes

- The three Adyen ID columns are nullable because they are populated sequentially during the three-step onboarding flow
- `status` is the only field that drives payment eligibility — checked in `routes_payments.py` before calling Adyen
- `status` is only ever updated by `routes_webhooks.py` — never by onboarding routes directly
- `updated_at` is auto-updated by SQLAlchemy on every write, useful for debugging webhook delivery timing