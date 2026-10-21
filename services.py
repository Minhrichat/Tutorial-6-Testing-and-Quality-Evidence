"""Business logic for the vertical slice FR-ONB-03: complete a training module and update onboarding progress."""
import re
import sqlite3


class AppError(Exception):
    status = 400
    code = "BAD_REQUEST"

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


class ValidationError(AppError):
    status, code = 400, "VALIDATION_ERROR"


class NotFound(AppError):
    status, code = 404, "NOT_FOUND"


class Conflict(AppError):
    status, code = 409, "CONFLICT"


EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
STORE_RE = re.compile(r"^PH-\d{3}$")  # e.g. PH-001
MAX_NAME, MAX_EMAIL = 100, 254
UNSAFE_CHARS = re.compile(r"[<>]")  # DEF-02: block HTML/script characters in names


def list_roles(conn):
    return [dict(r) for r in conn.execute("SELECT role_code, name FROM roles ORDER BY role_code")]


def list_employees(conn):
    rows = conn.execute(
        "SELECT id, full_name, email, role_code, store_code, onboarding_status FROM employees ORDER BY id"
    )
    return [dict(r) for r in rows]


def create_employee(conn: sqlite3.Connection, data: dict) -> dict:
    """FR-ONB-01/02: create a new employee and automatically assign the training plan for their role."""
    full_name = (data.get("full_name") or "").strip()
    email = (data.get("email") or "").strip().lower()
    role_code = (data.get("role_code") or "").strip()
    store_code = (data.get("store_code") or "").strip().upper()

    if len(full_name) < 2 or len(full_name) > MAX_NAME:
        raise ValidationError(f"full_name must be between 2 and {MAX_NAME} characters")
    if UNSAFE_CHARS.search(full_name):
        raise ValidationError("full_name contains invalid characters (< or >)")
    if len(email) > MAX_EMAIL or not EMAIL_RE.match(email):
        raise ValidationError("email is invalid")
    if not STORE_RE.match(store_code):
        raise ValidationError("store_code must match the format PH-001")
    if not conn.execute("SELECT 1 FROM roles WHERE role_code=?", (role_code,)).fetchone():
        raise ValidationError("role_code does not exist")
    if conn.execute("SELECT 1 FROM employees WHERE email=?", (email,)).fetchone():
        raise Conflict("email is already registered")

    cur = conn.execute(
        "INSERT INTO employees(full_name,email,role_code,store_code) VALUES (?,?,?,?)",
        (full_name, email, role_code, store_code),
    )
    emp_id = cur.lastrowid
    conn.execute(
        "INSERT INTO assignments(employee_id, module_id) "
        "SELECT ?, module_id FROM role_module_plan WHERE role_code=?",
        (emp_id, role_code),
    )
    conn.commit()
    return get_progress(conn, emp_id)


def get_progress(conn: sqlite3.Connection, emp_id: int) -> dict:
    emp = conn.execute("SELECT * FROM employees WHERE id=?", (emp_id,)).fetchone()
    if not emp:
        raise NotFound("employee not found")
    rows = conn.execute(
        "SELECT m.id AS module_id, m.code, m.title, m.seq, m.pass_mark, m.is_mandatory, "
        "a.status, a.best_score, a.attempts "
        "FROM assignments a JOIN training_modules m ON m.id=a.module_id "
        "WHERE a.employee_id=? ORDER BY m.seq",
        (emp_id,),
    ).fetchall()
    modules = [dict(r) for r in rows]
    passed = sum(1 for m in modules if m["status"] == "PASSED")
    total = len(modules)
    return {
        "employee": {
            "id": emp["id"], "full_name": emp["full_name"], "email": emp["email"],
            "role_code": emp["role_code"], "store_code": emp["store_code"],
            "onboarding_status": emp["onboarding_status"],
        },
        "modules": modules,
        "passed_count": passed,
        "total_count": total,
        "progress_percent": round(100 * passed / total) if total else 0,
    }


def complete_module(conn: sqlite3.Connection, emp_id: int, module_id: int, score) -> dict:
    """FR-ONB-03: record a module quiz score.

    Business rules:
      BR1  score is an integer 0..100
      BR2  the module must be assigned to the employee
      BR3  a PASSED module cannot be resubmitted (409)
      BR4  all mandatory modules with a lower seq must be PASSED first (409)
      BR5  score >= pass_mark -> PASSED, otherwise stays ASSIGNED (attempt is recorded)
      BR6  when all mandatory modules are PASSED -> onboarding_status = COMPLETED
    """
    if isinstance(score, bool) or not isinstance(score, int) or not 0 <= score <= 100:
        raise ValidationError("score must be an integer between 0 and 100")

    conn.execute("BEGIN IMMEDIATE")  # DEF-06: take the write lock before reading to prevent concurrent double submits
    try:
        return _complete_locked(conn, emp_id, module_id, score)
    except Exception:
        if conn.in_transaction:
            conn.rollback()
        raise


def _complete_locked(conn, emp_id, module_id, score):
    emp = conn.execute("SELECT id FROM employees WHERE id=?", (emp_id,)).fetchone()
    if not emp:
        raise NotFound("employee not found")

    a = conn.execute(
        "SELECT a.id, a.status, a.best_score, m.seq, m.pass_mark, m.title "
        "FROM assignments a JOIN training_modules m ON m.id=a.module_id "
        "WHERE a.employee_id=? AND a.module_id=?",
        (emp_id, module_id),
    ).fetchone()
    if not a:
        raise NotFound("module is not assigned to this employee")
    if a["status"] == "PASSED":
        raise Conflict("module has already been passed")

    blocker = conn.execute(
        "SELECT m.title FROM assignments x JOIN training_modules m ON m.id=x.module_id "
        "WHERE x.employee_id=? AND m.is_mandatory=1 AND m.seq < ? AND x.status != 'PASSED' "
        "ORDER BY m.seq LIMIT 1",
        (emp_id, a["seq"]),
    ).fetchone()
    if blocker:
        raise Conflict(f"complete module '{blocker['title']}' first")

    passed = score >= a["pass_mark"]
    try:
        conn.execute("INSERT INTO attempts(assignment_id, score, passed) VALUES (?,?,?)",
                     (a["id"], score, int(passed)))
        conn.execute(
            "UPDATE assignments SET attempts = attempts + 1, "
            "best_score = MAX(COALESCE(best_score,0), ?), "
            "status = CASE WHEN ? THEN 'PASSED' ELSE status END, "
            "completed_at = CASE WHEN ? THEN CURRENT_TIMESTAMP ELSE completed_at END "
            "WHERE id=?",
            (score, int(passed), int(passed), a["id"]),
        )
        remaining = conn.execute(
            "SELECT COUNT(*) FROM assignments x JOIN training_modules m ON m.id=x.module_id "
            "WHERE x.employee_id=? AND m.is_mandatory=1 AND x.status!='PASSED'",
            (emp_id,),
        ).fetchone()[0]
        if remaining == 0:
            conn.execute(
                "UPDATE employees SET onboarding_status='COMPLETED', completed_at=CURRENT_TIMESTAMP WHERE id=?",
                (emp_id,),
            )
        conn.commit()
    except Exception:
        conn.rollback()
        raise

    result = get_progress(conn, emp_id)
    result["attempt"] = {"module_id": module_id, "score": score, "passed": passed}
    return result
