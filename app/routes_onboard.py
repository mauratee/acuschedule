import os
import uuid
from flask import Blueprint, request, jsonify, render_template
import Adyen
from .db import db
from .models import Practitioner

onboard = Blueprint("onboard", __name__)

adyen = Adyen.Adyen()
adyen.client.xapikey = os.environ.get("ADYEN_API_KEY")
adyen.client.platform = "test"

BALANCE_PLATFORM_ID = os.environ.get("ADYEN_BALANCE_PLATFORM_ID", "")


@onboard.route("/signup")
def signup():
    """Render the practitioner signup form."""
    return render_template("signup.html")


@onboard.route("/api/onboard/legal-entity", methods=["POST"])
def create_legal_entity():
    """Create a legal entity in Adyen for a new practitioner."""
    data = request.get_json()

    body = {
        "type": "soleProprietorship",
        "individual": {
            "name": {
                "firstName": data["firstName"],
                "lastName": data["lastName"]
            },
            "email": data["email"],
            "phone": {
                "number": data["phone"],
                "type": "mobile"
            },
            "address": {
                "street": data["street"],
                "city": data["city"],
                "stateOrProvince": data["state"],
                "postalCode": data["postalCode"],
                "country": "US"
            }
        }
    }

    result = adyen.balancePlatform.legal_entities_api.create_legal_entity(body)
    legal_entity_id = result.message["id"]

    practitioner = Practitioner(
        id=str(uuid.uuid4()),
        first_name=data["firstName"],
        last_name=data["lastName"],
        email=data["email"],
        legal_entity_id=legal_entity_id,
        status="pending_kyc"
    )
    db.session.add(practitioner)
    db.session.commit()

    return jsonify({
        "legalEntityId": legal_entity_id,
        "practitionerId": practitioner.id
    })


@onboard.route("/api/onboard/account-holder", methods=["POST"])
def create_account_holder():
    """Create an account holder in Adyen and link to local practitioner."""
    data = request.get_json()
    practitioner_id = data["practitionerId"]
    legal_entity_id = data["legalEntityId"]

    body = {
        "legalEntityId": legal_entity_id,
        "balancePlatform": BALANCE_PLATFORM_ID,
        "description": data.get("description", "AcuSchedule practitioner"),
        "reference": practitioner_id
    }

    result = adyen.balancePlatform.account_holders_api.create_account_holder(body)
    account_holder_id = result.message["id"]

    practitioner = db.session.get(Practitioner, practitioner_id)
    practitioner.account_holder_id = account_holder_id
    db.session.commit()

    return jsonify({"accountHolderId": account_holder_id})


@onboard.route("/api/onboard/balance-account", methods=["POST"])
def create_balance_account():
    """Create a balance account for the practitioner."""
    data = request.get_json()
    practitioner_id = data["practitionerId"]
    account_holder_id = data["accountHolderId"]

    body = {
        "accountHolderId": account_holder_id,
        "description": "Primary balance account",
        "reference": f"{practitioner_id}-balance",
        "defaultCurrencyCode": "USD"
    }

    result = adyen.balancePlatform.balance_accounts_api.create_balance_account(body)
    balance_account_id = result.message["id"]

    practitioner = db.session.get(Practitioner, practitioner_id)
    practitioner.balance_account_id = balance_account_id
    db.session.commit()

    return jsonify({
        "balanceAccountId": balance_account_id,
        "status": practitioner.status
    })
