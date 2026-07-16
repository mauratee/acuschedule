import os
import uuid
from flask import Blueprint, request, jsonify, render_template
import Adyen
from .db import db
from .models import Practitioner

payments = Blueprint("payments", __name__)

adyen = Adyen.Adyen()
ADYEN_API_KEY = os.environ.get("ADYEN_API_KEY")
adyen.client.xapikey = ADYEN_API_KEY
adyen.client.platform = "test"

MERCHANT_ACCOUNT = os.environ.get("ADYEN_MERCHANT_ACCOUNT")
CLIENT_KEY = os.environ.get("ADYEN_CLIENT_KEY")
PLATFORM_BALANCE_ACCOUNT_ID = os.environ.get("PLATFORM_BALANCE_ACCOUNT_ID")


@payments.route("/")
def index():
    """Render the checkout page."""
    return render_template("checkout.html", client_key=CLIENT_KEY)


@payments.route("/result")
def result():
    """Render the payment result page."""
    session_id = request.args.get("sessionId")
    result_code = request.args.get("resultCode")
    return render_template("result.html", session_id=session_id, result_code=result_code)


@payments.route("/api/sessions", methods=["POST"])
def create_session():
    """Create an Adyen payment session for a verified practitioner."""
    data = request.get_json()

    # TODO: restore practitioner lookup before demo
    # practitioner_id = data.get("practitionerId")
    # practitioner = db.session.get(Practitioner, practitioner_id)
    # if not practitioner:
    #     return jsonify({"error": "Practitioner not found"}), 404
    # if not practitioner.is_active():
    #     return jsonify({
    #         "error": "Practitioner is not verified",
    #         "status": practitioner.status
    #     }), 403
    
    amount_value = data.get("amount", 10000)  # default $100.00 in cents

    body = {
        "merchantAccount": MERCHANT_ACCOUNT,
        "amount": {
            "value": amount_value,
            "currency": "USD"
        },
        "reference": f"order-{uuid.uuid4()}",
        "returnUrl": "http://localhost:8080/result",
        "countryCode": "US",
        "shopperLocale": "en-US",
        "channel": "Web",
    }

    # Add splits if platform balance account is configured
    # if PLATFORM_BALANCE_ACCOUNT_ID and practitioner.balance_account_id:
    #     platform_fee = int(amount_value * 0.05)  # 5% platform commission
    #     practitioner_amount = amount_value - platform_fee

    #     body["splits"] = [
    #         {
    #             "account": practitioner.balance_account_id,
    #             "type": "BalanceAccount",
    #             "amount": {
    #                 "value": practitioner_amount,
    #                 "currency": "USD"
    #             },
    #             "description": f"Payment to {practitioner.first_name} {practitioner.last_name}"
    #         },
    #         {
    #             "account": PLATFORM_BALANCE_ACCOUNT_ID,
    #             "type": "BalanceAccount",
    #             "amount": {
    #                 "value": platform_fee,
    #                 "currency": "USD"
    #             },
    #             "description": "AcuSchedule platform fee"
    #         }
    #     ]

    if not ADYEN_API_KEY or not MERCHANT_ACCOUNT:
        return jsonify({
            "error": "Adyen credentials are not configured. Set ADYEN_API_KEY and ADYEN_MERCHANT_ACCOUNT in the environment before using checkout."
        }), 500

    try:
        result = adyen.checkout.payments_api.sessions(request=body)
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500

    return jsonify(result.message)
