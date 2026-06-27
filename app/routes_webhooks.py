import os
import hmac
import hashlib
import base64
import json
from flask import Blueprint, request, jsonify
from .db import db
from .models import Practitioner

webhooks = Blueprint("webhooks", __name__)

HMAC_KEY = os.environ.get("ADYEN_HMAC_KEY")

def verify_hmac(notification, hmac_key):
    """Verify the HMAC signature of an incoming webhook notification.
 
    Common mistake #1: getting the field order wrong.
    Adyen's HMAC spec requires these exact fields in this exact order.
    Adding, removing, or reordering any field produces a different signature
    and all webhooks will fail verification silently.
 
    Common mistake #2: using == instead of hmac.compare_digest.
    String equality (==) is vulnerable to timing attacks — an attacker can
    measure how long the comparison takes to infer how many characters match.
    compare_digest runs in constant time regardless of where the mismatch is.
    """
    hmac_key_bytes = bytes.fromhex(hmac_key)

    fields = [
        notification.get("pspReference", ""),
        notification.get("originalReference", ""),
        notification.get("merchantAccountCode", ""),
        notification.get("merchantReference", ""),
        str(notification.get("amount", {}).get("value", "")),
        notification.get("amount", {}).get("currency", ""),
        notification.get("eventCode", ""),
        str(notification.get("success", "")),
    ]

    data = ":".join(fields)
    mac = hmac.new(hmac_key_bytes, data.encode("utf-8"), hashlib.sha256)
    expected = base64.b64encode(mac.digest()).decode("utf-8")
    received = notification.get("additionalData", {}).get("hmacSignature", "")

    return hmac.compare_digest(expected, received)


@webhooks.route("/api/webhooks/notifications", methods=["POST"])
def payment_webhook():
    """Handle standard Adyen payment webhooks (AUTHORISATION and others).
 
    Common mistake #3: trusting the frontend result instead of this webhook.
    The Drop-in UI calls onPaymentCompleted with a resultCode, but that result
    comes from the client and can be tampered with. The AUTHORISATION webhook
    is the authoritative payment outcome — always update your order system here,
    never in the frontend callback.
 
    Common mistake #4: doing slow work before returning 200.
    Adyen expects a 200 response within a few seconds. If your handler is slow
    (database writes, external API calls), Adyen will retry the webhook — which
    means you may process the same event multiple times. Return [accepted] first,
    then do the slow work. In production, use a task queue (Celery + Redis) so
    the webhook handler just enqueues a job and returns immediately.
    """
    payload = request.get_json()

    if not payload:
        return "[accepted]", 200

    for item in payload.get("notificationItems", []):
        notification = item.get("NotificationRequestItem", {})

        if HMAC_KEY:
            if not verify_hmac(notification, HMAC_KEY):
                print("[WEBHOOK] HMAC verification failed — rejecting")
                return "Invalid HMAC", 401
            
        event_code = notification.get("eventCode")
        success = notification.get("success") == "true"
        reference = notification.get("merchantReference", "")
        psp_reference = notification.get("pspReference", "")
        merchant_account = notification.get("merchantAccountCode", "")

        print(f"[WEBHOOK] {event_code} | success={success} | ref={reference} | psp={psp_reference} | merchant={merchant_account}")

        # Common mistake #5: only handling AUTHORISATION and ignoring other events.
        # In production you need to handle CAPTURE, REFUND, CANCELLATION, CHARGEBACK
        # at minimum. Each has a different effect on your order state machine.
        if event_code == "AUTHORISATION":
            if success:
                print(f"[WEBHOOK] Payment authorised — {psp_reference}")
                # TODO: update order status to AUTHORISED in your orders table
                # use psp_reference as your idempotency key (see mistake #6 below)
            else:
                reason = notification.get("reason", "unknown")
                print(f"[WEBHOOK] Payment refused — reason={reason}")
                # TODO: update order status to REFUSED

    # Common mistake #4 (continued): always return [accepted] for events you
    # receive, even ones you don't process. Returning 4xx or 5xx causes retries.
    return "[accepted]", 200


@webhooks.route("/api/webhooks/kyc", methods=["POST"])
def kyc_webhook():
    """Handle Balance Platform webhooks — drives practitioner status state machine.
 
    Common mistake #7: treating KYC as binary (pass/fail).
    There are three meaningful states: active (enabled=True), suspended
    (enabled=False AND verificationStatus=invalid/rejected), and pending_kyc
    (enabled=False for any other reason — still in progress, needs more docs).
    Collapsing pending and suspended into one state means practitioners who
    just need to upload a document get incorrectly marked as rejected.
 
    Common mistake #8: not matching the webhook to your local record.
    Adyen sends accountHolderId in the webhook payload. You set this as the
    reference when creating the account holder, so you can look it up locally.
    If you don't store it, you have no way to know which practitioner the
    webhook refers to.
    """
    payload = request.get_json()

    if not payload:
        return "[accepted]", 200

    event_type = payload.get("type")
    print(f"[KYC WEBHOOK] Received event: {event_type}")

    if event_type == "balancePlatform.accountHolder.updated":
        account_holder = payload.get("data", {}).get("accountHolder", {})
        account_holder_id = account_holder.get("id")
        capabilities = account_holder.get("capabilities", {})

        receive_payments = capabilities.get("receivePayments", {})
        enabled = receive_payments.get("enabled", False)
        verification_status = receive_payments.get("verificationStatus", "unknown")

        print(f"[KYC WEBHOOK] accountHolderId={account_holder_id} | receivePayments.enabled={enabled} | verificationStatus={verification_status}")

         # Common mistake #6: not using an idempotency key.
        # Adyen may deliver the same webhook more than once (retries, at-least-once
        # delivery). Without an idempotency check you risk processing the same
        # status transition twice. In production, store processed webhook IDs
        # and skip duplicates. For this demo we rely on the status being the same
        # on repeat delivery (idempotent by nature), but a real implementation
        # should track processed event IDs.
        practitioner = Practitioner.query.filter_by(
            account_holder_id=account_holder_id
        ).first()

        if practitioner:
            old_status = practitioner.status

            if enabled:
                practitioner.status = "active"
            else:
                 # Common mistake #7: collapsing these two cases into one
                if verification_status in ("invalid", "rejected"):
                    practitioner.status = "suspended"
                else:
                     # Still in progress — not a permanent failure
                    practitioner.status = "pending_kyc"

            db.session.commit()
            print(f"[KYC WEBHOOK] Practitioner {practitioner.id} status: {old_status} → {practitioner.status}")
        else:
            print(f"[KYC WEBHOOK] No practitioner found for accountHolderId={account_holder_id}")

    else:
        # Acknowledge all other Balance Platform events without processing
        # Common mistake #4 (applies here too): never return non-200 for
        # unhandled event types — that causes unnecessary retries.
        print(f"[KYC WEBHOOK] Unhandled event type: {event_type} — acknowledged")

    return "[accepted]", 200
