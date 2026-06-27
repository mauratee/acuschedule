from flask import Flask
from dotenv import load_dotenv
from .db import init_db

load_dotenv()

def create_app():
    """Create and configure the Flask application."""
    app = Flask(__name__)

    init_db(app)

    from .routes_onboard import onboard
    from .routes_payments import payments
    from .routes_webhooks import webhooks

    app.register_blueprint(onboard)
    app.register_blueprint(payments)
    app.register_blueprint(webhooks)

    return app
