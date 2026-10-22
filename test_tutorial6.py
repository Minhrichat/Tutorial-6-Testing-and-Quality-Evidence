"""Tutorial 6 - Test cases with TC IDs, linked to requirement / risk / defect."""
import re
import threading
import pathlib

import pytest

import db
from app import create_app

ROOT = pathlib.Path(__file__).resolve().parent.parent


@pytest.fixture
def app(tmp_path):
    a = create_app(str(tmp_path / "t6.db"))
    a.config["TESTING"] = True
    return a


@pytest.fixture
def client(app):
    return app.test_client()


def emp(client, email="a@pizzahut.vn", role="CREW", name="Nguyen Van A", store="PH-001"):
    return client.post("/api/employees", json={
        "full_name": name, "email": email, "role_code": role, "store_code": store})


def done(client, e, m, s):
    return client.post(f"/api/employees/{e}/modules/{m}/complete", json={"score": s})


# ---------------- POSITIVE ----------------
def test_tc01_create_crew_assigns_4_modules(client):                      # FR-ONB-01/02
    r = emp(client)
    assert r.status_code == 201 and r.get_json()["total_count"] == 4


def test_tc02_pass_first_module_gives_25_percent(client):                  # FR-ONB-03
    e = emp(client).get_json()["employee"]["id"]
    assert done(client, e, 1, 90).get_json()["progress_percent"] == 25


def test_tc03_full_flow_completed(client):                                 # FR-ONB-04
    e = emp(client).get_json()["employee"]["id"]
    for m, s in [(1, 70), (2, 80), (4, 70), (5, 70)]:
        body = done(client, e, m, s).get_json()
    assert body["employee"]["onboarding_status"] == "COMPLETED"


# ---------------- NEGATIVE ----------------
def test_tc04_invalid_email_rejected(client):                              # FR-ONB-01
    assert emp(client, email="abc").status_code == 400


def test_tc05_duplicate_email_case_insensitive(client):                    # FR-ONB-01
    emp(client, email="a@pizzahut.vn")
    assert emp(client, email="A@PizzaHut.VN").status_code == 409


def test_tc06_prerequisite_order(client):                                  # FR-ONB-03 BR4
    e = emp(client).get_json()["employee"]["id"]
    assert done(client, e, 2, 95).status_code == 409


def test_tc07_invalid_score_types(client):                                 # FR-ONB-03 BR1
    e = emp(client).get_json()["employee"]["id"]
    for bad in (-1, 101, "90", None, 3.5, True):
        assert done(client, e, 1, bad).status_code == 400, bad


def test_tc08_malformed_json_returns_json_error(client):                   # NFR error handling
    r = client.post("/api/employees", data="not json", content_type="application/json")
    assert r.status_code == 400 and "error" in r.get_json()
    assert "Traceback" not in r.get_data(as_text=True)


# ---------------- EDGE / BOUNDARY ----------------
def test_tc09_score_equals_pass_mark_passes_and_below_fails(client):       # BR5 (M01 pass=70)
    e = emp(client).get_json()["employee"]["id"]
    assert done(client, e, 1, 69).get_json()["attempt"]["passed"] is False
    assert done(client, e, 1, 70).get_json()["attempt"]["passed"] is True


def test_tc10_score_bounds_0_and_100_accepted(client):                     # BR1
    e = emp(client).get_json()["employee"]["id"]
    assert done(client, e, 1, 0).status_code == 200
    assert done(client, e, 1, 100).status_code == 200


def test_tc11_full_name_length_boundaries(client):                         # FR-ONB-01
    assert emp(client, email="1@x.vn", name="A").status_code == 400
    assert emp(client, email="2@x.vn", name="An").status_code == 201
    assert emp(client, email="3@x.vn", name="A" * 100).status_code == 201
    assert emp(client, email="4@x.vn", name="A" * 10000).status_code == 400   # DEF-01


# ---------------- SECURITY / RISK ----------------
def test_tc12_sql_injection_stored_literally(client, app):                 # RISK-SEC-01
    r = emp(client, email="x';DROP--@a.com", name="Robert'); DROP TABLE employees;--")
    assert r.status_code == 201
    assert client.get("/api/employees").status_code == 200
    with db.connect(app.config["DB_FILE"]) as c:
        assert c.execute("SELECT COUNT(*) FROM employees").fetchone()[0] == 1


def test_tc13_script_in_name_rejected(client):                             # RISK-SEC-02 (XSS) DEF-02
    assert emp(client, name="<script>alert(1)</script>").status_code == 400


def test_tc14_ui_escapes_dynamic_text():                                   # RISK-SEC-02 DEF-02
    html = (ROOT / "templates" / "index.html").read_text(encoding="utf-8")
    assert "function esc(" in html
    assert "${p.employee.full_name}" not in html


def test_tc15_errors_are_json_for_unknown_routes_and_methods(client):      # NFR API consistency DEF-03
    for method, path in [("get", "/api/nope"), ("get", "/api/employees/abc/progress"), ("delete", "/api/employees")]:
        r = getattr(client, method)(path)
        assert r.is_json and "error" in r.get_json(), (method, path, r.status_code)


def test_tc16_security_headers_present(client):                            # RISK-SEC-03 DEF-04
    r = client.get("/")
    assert r.headers.get("X-Content-Type-Options") == "nosniff"
    assert r.headers.get("X-Frame-Options") == "DENY"


def test_tc17_no_secret_files_or_hardcoded_secrets():                      # RISK-SEC-04
    assert not (ROOT / ".env").exists() or ".env" in (ROOT / ".gitignore").read_text()
    pat = re.compile(r"(api[_-]?key|secret|password)\s*=\s*['\"]?[A-Za-z0-9]{8,}", re.I)
    for f in ROOT.glob("*.py"):
        assert not pat.search(f.read_text(encoding="utf-8")), f.name


@pytest.mark.xfail(reason="DEF-05: no authentication/authorization yet - planned for the next slice (FR-SEC)", strict=True)
def test_tc18_endpoints_require_authentication(client):                    # RISK-SEC-05 DEF-05 (known gap)
    assert client.get("/api/employees").status_code == 401


# ---------------- CONCURRENCY ----------------
def test_tc19_concurrent_double_submit_counts_once(app):                   # RISK-DATA-01 DEF-06 
    c = app.test_client()
    e = emp(c).get_json()["employee"]["id"]
    codes, lock = [], threading.Lock()

    def go():
        r = app.test_client().post(f"/api/employees/{e}/modules/1/complete", json={"score": 90})
        with lock:
            codes.append(r.status_code)

    ts = [threading.Thread(target=go) for _ in range(8)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    with db.connect(app.config["DB_FILE"]) as conn:
        attempts = conn.execute("SELECT attempts FROM assignments WHERE employee_id=? AND module_id=1", (e,)).fetchone()[0]
    assert sorted(codes) == [200] + [409] * 7, codes
    assert attempts == 1
