import uuid
from .db import db

class Practitioner(db.Model):
    """Represents an acupuncturist sub-merchant on the AcuSchedule platform."""

    __tablename__ = "practitioners"

    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    first_name = db.Column(db.String(100), nullable=False)
    last_name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(255), nullable=False, unique=True)

    # Adyen Balance Platform IDs — populated sequentially during onboarding
    legal_entity_id = db.Column(db.String(100), nullable=True)
    account_holder_id = db.Column(db.String(100), nullable=True)
    balance_account_id = db.Column(db.String(100), nullable=True)

    # Status drives payment eligibility — only updated by webhook handler
    status = db.Column(
        db.Enum("pending_kyc", "active", "suspended", name="practitioner_status"),
        nullable=False,
        default="pending_kyc"
    )

    created_at = db.Column(db.DateTime, default=db.func.now())
    updated_at = db.Column(db.DateTime, default=db.func.now(), onupdate=db.func.now())

    def __repr__(self):
        """Return string representation of Practitioner."""
        return f"<Practitioner {self.first_name} {self.last_name} ({self.status})>"

    def is_active(self):
        """Return True if practitioner is verified and can accept payments."""
        return self.status == "active"
    
    def to_dict(self):
        """Serialize practitioner to dictionary for JSON responses."""
        return {
            "id": self.id,
            "firstName": self.first_name,
            "lastName": self.last_name,
            "email": self.email,
            "status": self.status,
            "legalEntityId": self.legal_entity_id,
            "accountHolderId": self.account_holder_id,
            "balanceAccountId": self.balance_account_id,
        }