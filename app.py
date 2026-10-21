"""Flask API + UI for the Pizza Hut Employee Onboarding & Training Management System."""
import logging
import os

from flask import Flask, g, jsonify, render_template, request
from werkzeug.exceptions import HTTPException

import db
import services
from services import AppError, ValidationError

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("onboarding")


def create_app(db_file: str | None = None) -> Flask:
    app = Flask(__name__)
    app.config["DB_FILE"] = db_file or db.default_db_path()

    with db.connect(app.config["DB_FILE"]) as conn:  # migrate + seed at startup (safe to re-run)
        db.migrate(conn)
        db.seed(conn)

    def get_conn():
        if "conn" not in g:
            g.conn = db.connect(app.config["DB_FILE"])
        return g.conn

    @app.teardown_appcontext
    def close_conn(_exc):
        conn = g.pop("conn", None)
        if conn is not None:
            conn.close()

    @app.errorhandler(AppError)
    def handle_app_error(e: AppError):
        log.warning("%s %s -> %s %s", request.method, request.path, e.status, e.message)
        return jsonify({"error": {"code": e.code, "message": e.message}}), e.status

    @app.errorhandler(HTTPException)  # DEF-03: HTTP errors (404/405...) always return JSON
    def handle_http_error(e: HTTPException):
        return jsonify({"error": {"code": e.name.upper().replace(" ", "_"), "message": e.description}}), e.code

    @app.errorhandler(Exception)
    def handle_unexpected(e: Exception):
        log.exception("unhandled error")
        return jsonify({"error": {"code": "INTERNAL_ERROR", "message": "internal server error"}}), 500

    @app.after_request  # DEF-04: basic security headers
    def security_headers(resp):
        resp.headers["X-Content-Type-Options"] = "nosniff"
        resp.headers["X-Frame-Options"] = "DENY"
        resp.headers["Referrer-Policy"] = "no-referrer"
        return resp

    def json_body() -> dict:
        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            raise ValidationError("request body must be a JSON object")
        return data

    @app.get("/")
    def index():
        return render_template("index.html")

    @app.get("/health")
    def health():
        get_conn().execute("SELECT 1")
        return jsonify({"status": "ok"})

    @app.get("/api/roles")
    def roles():
        return jsonify(services.list_roles(get_conn()))

    @app.get("/api/employees")
    def employees():
        return jsonify(services.list_employees(get_conn()))

    @app.post("/api/employees")
    def create_employee():
        result = services.create_employee(get_conn(), json_body())
        log.info("created employee id=%s", result["employee"]["id"])
        return jsonify(result), 201

    @app.get("/api/employees/<int:emp_id>/progress")
    def progress(emp_id):
        return jsonify(services.get_progress(get_conn(), emp_id))

    @app.post("/api/employees/<int:emp_id>/modules/<int:module_id>/complete")
    def complete(emp_id, module_id):
        body = json_body()
        result = services.complete_module(get_conn(), emp_id, module_id, body.get("score"))
        log.info("emp=%s module=%s score=%s passed=%s", emp_id, module_id,
                 result["attempt"]["score"], result["attempt"]["passed"])
        return jsonify(result)

    return app


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5000"))
    create_app().run(host="127.0.0.1", port=port, debug=os.environ.get("FLASK_DEBUG") == "1")
