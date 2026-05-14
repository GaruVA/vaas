"""VAAS web application — Flask application factory and initialization."""
from __future__ import annotations

import queue
import sqlite3
import threading

from flask import Flask, g

from src.config import DB_PATH, HARDWARE_MODE as _DEFAULT_HW_MODE, SECRET_KEY


class SSEBroker:
    """Fan-out pub/sub broker for Server-Sent Events.

    Each call to ``subscribe()`` returns a ``queue.Queue`` that will receive
    every event dict published via ``publish()``.  Call ``unsubscribe(q)``
    when the SSE client disconnects to stop filling its queue.
    """

    def __init__(self) -> None:
        self._lock: threading.Lock = threading.Lock()
        self._queues: list[queue.Queue] = []

    def subscribe(self) -> queue.Queue:
        q: queue.Queue = queue.Queue(maxsize=50)
        with self._lock:
            self._queues.append(q)
        return q

    def unsubscribe(self, q: queue.Queue) -> None:
        with self._lock:
            try:
                self._queues.remove(q)
            except ValueError:
                pass

    def publish(self, event: dict) -> None:
        with self._lock:
            subscribers = list(self._queues)
        for q in subscribers:
            try:
                q.put_nowait(event)
            except queue.Full:
                pass  # slow/stale client — drop the event rather than block


def create_app(config_overrides: dict | None = None, hardware_mode: str | None = None, start_overstay_monitor: bool = False) -> Flask:
    """Create and configure the VAAS Flask application.
    
    Args:
        config_overrides: Optional dict to override Flask config settings.
        hardware_mode: Optional hardware mode (LIVE or MOCK); passed to config if provided.
        start_overstay_monitor: Whether to start the overstay monitoring thread (not yet implemented).
        
    Returns:
        Configured Flask application with all blueprints registered.
    """
    import logging as _logging
    _logger = _logging.getLogger(__name__)

    hw_mode = (hardware_mode or _DEFAULT_HW_MODE).upper()

    app = Flask(__name__, template_folder="templates", static_folder="static")

    # ── SSE event broker ──────────────────────────────────────────────────────
    app.config["VAAS_BROKER"] = SSEBroker()

    # ── Flask session / cookie config ─────────────────────────────────────────
    app.config.update({
        "SECRET_KEY": SECRET_KEY,
        "SESSION_COOKIE_SECURE": False,  # HTTP-only for dev; set True in production HTTPS
        "SESSION_COOKIE_HTTPONLY": True,
        "SESSION_COOKIE_SAMESITE": "Lax",
        "PERMANENT_SESSION_LIFETIME": 8 * 60 * 60,  # 8 hours per BUILD_SPEC
        "HARDWARE_MODE": hw_mode,
        "START_OVERSTAY_MONITOR": start_overstay_monitor,
    })

    # Override config if provided
    if config_overrides:
        app.config.update(config_overrides)

    # ── Persistent engine DB connection ───────────────────────────────────────
    # The camera workers run in background threads and need a long-lived
    # connection separate from the per-request g.db connections.
    from src.database import connect as _db_connect, migrate_db as _migrate_db
    engine_conn = _db_connect(DB_PATH)
    engine_conn.isolation_level = None   # autocommit
    engine_conn.row_factory = sqlite3.Row
    _migrate_db(engine_conn)
    app.config["VAAS_DB"] = engine_conn
    _logger.info("Engine DB connection opened and schema migrated")

    # ── Barrier controller ────────────────────────────────────────────────────
    from src.barrier import BarrierController
    barrier = BarrierController(mode=hw_mode)
    app.config["VAAS_BARRIER"] = barrier
    _logger.info("BarrierController created (mode=%s)", hw_mode)

    # ── Attendance engine ─────────────────────────────────────────────────────
    from src.attendance import AttendanceEngine
    broker = app.config["VAAS_BROKER"]
    # AttendanceEngine calls sse_callback(event_type: str, data: dict).
    # SSEBroker.publish takes a single merged dict, so wrap it here.
    def _sse_callback(event_type: str, data: dict) -> None:
        broker.publish({"type": event_type, **data})
    engine = AttendanceEngine(
        conn=engine_conn,
        barrier=barrier,
        sse_callback=_sse_callback,
    )
    app.config["VAAS_ENGINE"] = engine
    _logger.info("AttendanceEngine created")
    
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
    
    # ── UI routes — serve the static HTML pages at clean top-level URLs ──────
    from flask import redirect, send_from_directory, session, url_for

    UI_DIR = app.static_folder + "/ui"

    def _require_login(next_url: str):
        """Return a redirect to the login page if no session, else None."""
        if "user_id" not in session:
            return redirect(url_for("auth.login", next=next_url))
        return None

    @app.route("/")
    def index():
        guard = _require_login("/VAAS.html")
        if guard:
            return guard
        return redirect("/VAAS.html")

    @app.route("/VAAS.html")
    def ui_hub():
        guard = _require_login("/VAAS.html")
        if guard:
            return guard
        return send_from_directory(UI_DIR, "VAAS.html")

    @app.route("/vaas-fleet.html")
    def ui_fleet():
        guard = _require_login("/vaas-fleet.html")
        if guard:
            return guard
        return send_from_directory(UI_DIR, "vaas-fleet.html")

    @app.route("/vaas-forensic.html")
    def ui_forensic():
        guard = _require_login("/vaas-forensic.html")
        if guard:
            return guard
        return send_from_directory(UI_DIR, "vaas-forensic.html")

    @app.route("/vaas-gateops.html")
    def ui_gateops():
        guard = _require_login("/vaas-gateops.html")
        if guard:
            return guard
        return send_from_directory(UI_DIR, "vaas-gateops.html")

    @app.route("/vaas-manager.html")
    def ui_manager():
        guard = _require_login("/vaas-manager.html")
        if guard:
            return guard
        return send_from_directory(UI_DIR, "vaas-manager.html")

    return app
