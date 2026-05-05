"""Flask application factory for VAAS (§5.7)."""
from __future__ import annotations

import logging
import os
import queue
import threading
from datetime import timedelta
from pathlib import Path
from typing import Optional

from flask import Flask

from src.attendance import AttendanceEngine
from src.barrier import BarrierController
from src.config import (
    ARDUINO_BAUD, ARDUINO_PORT, DB_PATH, HARDWARE_MODE,
    SECRET_KEY, SESSION_TIMEOUT_HOURS,
)
from src.database import connect, migrate_schema

logger = logging.getLogger(__name__)


class SSEBroker:
    """Fan-out queue broker for Server-Sent Events."""

    def __init__(self) -> None:
        self._listeners: list[queue.Queue] = []
        self._lock = threading.Lock()

    def subscribe(self) -> queue.Queue:
        q: queue.Queue = queue.Queue(maxsize=200)
        with self._lock:
            self._listeners.append(q)
        return q

    def unsubscribe(self, q: queue.Queue) -> None:
        with self._lock:
            self._listeners.discard(q) if hasattr(self._listeners, "discard") \
                else (self._listeners.remove(q) if q in self._listeners else None)

    def publish(self, event: dict) -> None:
        with self._lock:
            for q in list(self._listeners):
                try:
                    q.put_nowait(event)
                except queue.Full:
                    pass


def create_app(config_overrides: Optional[dict] = None,
               db_path: Optional[Path] = None,
               hardware_mode: Optional[str] = None,
               start_overstay_monitor: bool = False) -> Flask:
    """Create and configure the Flask application.

    Args:
        config_overrides: Extra Flask config key-value pairs (used by tests).
        db_path: Override the SQLite path (tests inject a temp file).
        hardware_mode: 'LIVE' or 'MOCK'. Defaults to HARDWARE_MODE from config.
        start_overstay_monitor: Launch overstay-check background thread.
    """
    app = Flask(__name__)
    app.secret_key = SECRET_KEY
    app.permanent_session_lifetime = timedelta(hours=SESSION_TIMEOUT_HOURS)

    if SECRET_KEY == "vaas-dev-secret-change-me":
        logger.warning(
            "VAAS_SECRET_KEY is not set — using insecure default. "
            "Set the environment variable before going to production."
        )

    if config_overrides:
        app.config.update(config_overrides)

    # Database
    path = db_path or DB_PATH
    conn = connect(path)
    migrate_schema(conn)   # safe on fresh and existing databases alike

    # SSE broker
    broker = SSEBroker()

    # Barrier controller — LIVE in production, MOCK only in tests / overrides
    mode = hardware_mode or HARDWARE_MODE
    if mode == "LIVE":
        try:
            barrier = BarrierController(
                mode="LIVE",
                port=os.environ.get("VAAS_ARDUINO_PORT", ARDUINO_PORT),
                baud=ARDUINO_BAUD,
            )
        except Exception as exc:
            logger.error(
                "Arduino not available on %s (%s) — falling back to MOCK barrier",
                ARDUINO_PORT, exc,
            )
            barrier = BarrierController(mode="MOCK")
    else:
        barrier = BarrierController(mode="MOCK")

    # Attendance engine
    engine = AttendanceEngine(
        conn,
        barrier=barrier,
        sse_publish=broker.publish,
    )

    if start_overstay_monitor:
        engine.start_overstay_monitor()

    # Stash on app config so blueprints can access via current_app.config
    app.config["VAAS_DB"] = conn
    app.config["VAAS_ENGINE"] = engine
    app.config["VAAS_BROKER"] = broker
    app.config["VAAS_BARRIER"] = barrier
    app.config["VAAS_HW_MODE"] = mode

    # Blueprints
    from webapp.auth import auth_bp
    from webapp.routes.admin import admin_bp
    from webapp.routes.api import api_bp
    from webapp.routes.manager import manager_bp
    from webapp.routes.operator import operator_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(operator_bp)
    app.register_blueprint(manager_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(api_bp)

    @app.route("/")
    def index():
        from flask import redirect, session, url_for
        if "user_id" in session:
            role = session.get("role")
            if role == "OPERATOR":
                return redirect(url_for("operator.dashboard"))
            if role == "MANAGER":
                return redirect(url_for("manager.home"))
            return redirect(url_for("admin.home"))
        return redirect(url_for("auth.login"))

    return app
