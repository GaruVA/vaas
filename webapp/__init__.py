"""VAAS web application — Flask application factory and initialization."""
from __future__ import annotations

import sqlite3
from pathlib import Path

from flask import Flask, g

from src.config import DB_PATH, SECRET_KEY


def create_app(config_overrides: dict | None = None, hardware_mode: str | None = None, start_overstay_monitor: bool = False) -> Flask:
    """Create and configure the VAAS Flask application.
    
    Args:
        config_overrides: Optional dict to override Flask config settings.
        hardware_mode: Optional hardware mode (LIVE or MOCK); passed to config if provided.
        start_overstay_monitor: Whether to start the overstay monitoring thread (not yet implemented).
        
    Returns:
        Configured Flask application with all blueprints registered.
    """
    app = Flask(__name__, template_folder="templates", static_folder="static")
    
    # Configuration
    app.config.update({
        "SECRET_KEY": SECRET_KEY,
        "SESSION_COOKIE_SECURE": False,  # HTTP-only for dev; set True in production HTTPS
        "SESSION_COOKIE_HTTPONLY": True,
        "SESSION_COOKIE_SAMESITE": "Lax",
        "PERMANENT_SESSION_LIFETIME": 8 * 60 * 60,  # 8 hours per BUILD_SPEC
        "HARDWARE_MODE": hardware_mode or "MOCK",
        "START_OVERSTAY_MONITOR": start_overstay_monitor,
    })
    
    # Override config if provided
    if config_overrides:
        app.config.update(config_overrides)
    
    # Database connection (per-request via Flask's g object for thread safety)
    @app.before_request
    def ensure_db():
        """Ensure database connection is available for each request."""
        if "db" not in g:
            g.db = sqlite3.connect(str(DB_PATH))
            g.db.isolation_level = None  # autocommit
            g.db.row_factory = sqlite3.Row
            g.db.execute("PRAGMA foreign_keys = ON")
    
    @app.teardown_appcontext
    def close_db(error):
        """Close database connection on app teardown."""
        db = g.pop("db", None)
        if db is not None:
            db.close()
    
    # Register blueprints
    from webapp.routes.admin import admin_bp
    from webapp.routes.api import api_bp
    from webapp.routes.manager import manager_bp
    from webapp.routes.operator import operator_bp
    from webapp.auth import auth_bp
    
    app.register_blueprint(auth_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(api_bp)
    app.register_blueprint(manager_bp)
    app.register_blueprint(operator_bp)
    
    # Index route (redirect to operator dashboard)
    @app.route("/")
    def index():
        from flask import redirect, url_for
        return redirect(url_for("operator.dashboard"))
    
    return app
