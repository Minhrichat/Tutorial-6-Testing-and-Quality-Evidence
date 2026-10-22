"""Vertical-slice tests. Each test is tagged with its requirement ID for traceability: FR-ONB-01..04."""
import pytest

import db
from app import create_app


@pytest.fixture
def client(tmp_path):
    app = create_app(str(tmp_path / "test.db"))
    app.config["TESTING"] = True
    return app.test_client()


def make_emp(client, email="a@pizzahut.vn", role="CREW"):
    return client.post("/api/employees", json={
        "full_name": "Nguyen Van A", "email": email, "role_code": role, "store_code": "PH-001"})


def complete(client, emp, module, score):
    return client.post(f"/api/employees/{emp}/modules/{module}/complete", json={"score": score})


def test_health(client):
    assert client.get("/health").get_json() == {"status": "ok"}


def test_fr_onb_02_create_assigns_plan_by_role(client):
    r = make_emp(client, role="CREW")
    assert r.status_code == 201
    body = r.get_json()
    assert [m["code"] for m in body["modules"]] == ["M01", "M02", "M04", "M05"]
    assert body["progress_percent"] == 0
    assert body["employee"]["onboarding_status"] == "IN_PROGRESS"
    chef = make_emp(client, "b@pizzahut.vn", "CHEF").get_json()
    assert [m["code"] for m in chef["modules"]] == ["M01", "M02", "M03"]


@pytest.mark.parametrize("patch,msg", [
    ({"email": "sai-email"}, "email"),
    ({"full_name": "A"}, "full_name"),
    ({"store_code": "HN-1"}, "store_code"),
    ({"role_code": "BOSS"}, "role_code"),
])
def test_fr_onb_01_validation_errors(client, patch, msg):
    payload = {"full_name": "Nguyen Van A", "email": "a@pizzahut.vn", "role_code": "CREW", "store_code": "PH-001"}
    payload.update(patch)
    r = client.post("/api/employees", json=payload)
    assert r.status_code == 400
    assert msg in r.get_json()["error"]["message"]


def test_fr_onb_01_duplicate_email_conflict(client):
    make_emp(client)
    assert make_emp(client).status_code == 409


def test_fr_onb_03_pass_updates_progress(client):
    emp = make_emp(client).get_json()["employee"]["id"]
    r = complete(client, emp, 1, 90)
    assert r.status_code == 200
    body = r.get_json()
    assert body["attempt"]["passed"] is True
    assert body["progress_percent"] == 25  # 1/4 module


def test_fr_onb_03_fail_keeps_assigned_and_counts_attempt(client):
    emp = make_emp(client).get_json()["employee"]["id"]
    body = complete(client, emp, 1, 50).get_json()
    m1 = body["modules"][0]
    assert body["attempt"]["passed"] is False
    assert m1["status"] == "ASSIGNED" and m1["attempts"] == 1 and m1["best_score"] == 50
    body = complete(client, emp, 1, 75).get_json()  # successful retry (pass_mark=70)
    assert body["modules"][0]["status"] == "PASSED" and body["modules"][0]["attempts"] == 2


def test_fr_onb_03_prerequisite_order_enforced(client):
    emp = make_emp(client).get_json()["employee"]["id"]
    r = complete(client, emp, 2, 95)  # M01 not completed yet
    assert r.status_code == 409
    assert "first" in r.get_json()["error"]["message"]


def test_fr_onb_03_cannot_resubmit_passed_module(client):
    emp = make_emp(client).get_json()["employee"]["id"]
    complete(client, emp, 1, 80)
    assert complete(client, emp, 1, 100).status_code == 409


@pytest.mark.parametrize("bad", [-1, 101, "90", None, 3.5, True])
def test_fr_onb_03_invalid_score(client, bad):
    emp = make_emp(client).get_json()["employee"]["id"]
    assert complete(client, emp, 1, bad).status_code == 400


def test_fr_onb_03_unknown_employee_and_unassigned_module(client):
    assert complete(client, 999, 1, 80).status_code == 404
    emp = make_emp(client).get_json()["employee"]["id"]
    assert complete(client, emp, 6, 90).status_code == 404  # M06 is only for SHIFT_MGR


def test_fr_onb_04_full_flow_completes_onboarding(client):
    emp = make_emp(client, role="CREW").get_json()["employee"]["id"]
    for module, score in [(1, 70), (2, 80), (4, 100), (5, 90)]:
        body = complete(client, emp, module, score).get_json()
    assert body["progress_percent"] == 100
    assert body["employee"]["onboarding_status"] == "COMPLETED"


def test_migrate_and_seed_are_idempotent(tmp_path):
    conn = db.connect(str(tmp_path / "x.db"))
    assert db.migrate(conn) == ["001_init.sql"]
    db.seed(conn)
    assert db.migrate(conn) == []
    db.seed(conn)
    assert conn.execute("SELECT COUNT(*) FROM training_modules").fetchone()[0] == 6
    assert conn.execute("SELECT COUNT(*) FROM roles").fetchone()[0] == 3
