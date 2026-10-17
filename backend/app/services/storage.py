"""SQLite persistence for the plan ledger and audit log."""
from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime, timezone
from typing import Optional

from ..core.audit import log_event
from ..models.plan import Filter, Outcome, Plan, ResultRow, Task, TaskStatus

SCHEMA = """
CREATE TABLE IF NOT EXISTS plans(
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    text TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'draft',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    task_count INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS tasks(
    id TEXT NOT NULL,
    plan_id TEXT NOT NULL,
    title TEXT NOT NULL,
    body TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'pending',
    "order" INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY(plan_id, id)
);
CREATE TABLE IF NOT EXISTS outcomes(
    task_id TEXT PRIMARY KEY,
    plan_id TEXT NOT NULL,
    passed INTEGER NOT NULL,
    label TEXT NOT NULL,
    confidence REAL NOT NULL,
    agreement TEXT NOT NULL,
    exit_code INTEGER,
    duration_ms INTEGER NOT NULL,
    last_line TEXT NOT NULL,
    head TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS audit(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    actor TEXT NOT NULL,
    action TEXT NOT NULL,
    detail TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_outcomes_plan ON outcomes(plan_id);
CREATE INDEX IF NOT EXISTS idx_outcomes_label ON outcomes(label);
CREATE INDEX IF NOT EXISTS idx_tasks_plan ON tasks(plan_id);
"""

_TASK_COLS = "id,plan_id,title,body,status,\"order\""
_LIKE_ESCAPE = str.maketrans({"%": r"\%", "_": r"\_"})


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _escape_like(term: str) -> str:
    return term.translate(_LIKE_ESCAPE)


class Storage:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._lock = threading.Lock()
        self._local = threading.local()

    def init(self) -> None:
        self._conn()

    @property
    def conn(self) -> sqlite3.Connection:
        return self._conn()

    def _conn(self) -> sqlite3.Connection:
        conn = getattr(self._local, "conn", None)
        if conn is None:
            conn = sqlite3.connect(self.db_path, check_same_thread=False)
            conn.row_factory = sqlite3.Row
            conn.executescript(SCHEMA)
            self._local.conn = conn
        return conn

    def close(self) -> None:
        conn = getattr(self._local, "conn", None)
        if conn is not None:
            conn.close()
            self._local.conn = None

    # ---------- plans ----------
    def create_plan(self, plan: Plan, actor: str = "api") -> Plan:
        with self._lock:
            conn = self._conn()
            now = _utcnow()
            conn.execute(
                "INSERT INTO plans(id,name,text,status,created_at,updated_at,task_count) "
                "VALUES(?,?,?,?,?,?,?)",
                (plan.id, plan.name, plan.text, plan.status.value, now, now, len(plan.tasks)),
            )
            for task in plan.tasks:
                conn.execute(
                    "INSERT INTO tasks(id,plan_id,title,body,status,\"order\") VALUES(?,?,?,?,?,?)",
                    (task.id, plan.id, task.title, task.body, task.status.value, task.order),
                )
            self._audit(conn, actor, "plan.created", {"plan_id": plan.id, "tasks": len(plan.tasks)})
            conn.commit()
        plan.created_at = now
        plan.updated_at = now
        return plan

    def get_plan(self, plan_id: str) -> Optional[Plan]:
        with self._lock:
            conn = self._conn()
            row = conn.execute("SELECT * FROM plans WHERE id=?", (plan_id,)).fetchone()
            if row is None:
                return None
            tasks = self._tasks(conn, plan_id)
            return Plan(
                id=row["id"], name=row["name"], text=row["text"],
                status=PlanStatus(row["status"]), task_count=row["task_count"],
                created_at=row["created_at"], updated_at=row["updated_at"], tasks=tasks,
            )

    def list_plans(self, limit: int = 25, offset: int = 0, name: Optional[str] = None) -> list[Plan]:
        with self._lock:
            conn = self._conn()
            if name:
                rows = conn.execute(
                    "SELECT * FROM plans WHERE name LIKE ? "
                    "ORDER BY created_at DESC LIMIT ? OFFSET ?",
                    (f"%{_escape_like(name)}%", limit, offset),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM plans ORDER BY created_at DESC LIMIT ? OFFSET ?",
                    (limit, offset),
                ).fetchall()
            return [
                Plan(id=r["id"], name=r["name"], text=r["text"], status=PlanStatus(r["status"]),
                     task_count=r["task_count"], created_at=r["created_at"],
                     updated_at=r["updated_at"])
                for r in rows
            ]

    def count_plans(self) -> int:
        with self._lock:
            return int(self._conn().execute("SELECT COUNT(*) FROM plans").fetchone()[0])

    # ---------- tasks ----------
    def get_task(self, task_id: str) -> Optional[Task]:
        with self._lock:
            conn = self._conn()
            row = conn.execute(
                f"SELECT {_TASK_COLS} FROM tasks WHERE id=?", (task_id,)
            ).fetchone()
            if row is None:
                return None
            return Task(id=row["id"], title=row["title"], body=row["body"],
                        status=TaskStatus(row["status"]), order=row["order"])

    def get_task_with_plan(self, task_id: str) -> Optional[tuple[Task, str]]:
        with self._lock:
            conn = self._conn()
            row = conn.execute(
                f"SELECT t.id,t.plan_id,t.title,t.body,t.status,t.\"order\",p.name "
                "FROM tasks t JOIN plans p ON p.id=t.plan_id WHERE t.id=?",
                (task_id,),
            ).fetchone()
            if row is None:
                return None
            task = Task(id=row["id"], title=row["title"], body=row["body"],
                        status=TaskStatus(row["status"]), order=row["order"])
            return task, row["plan_id"]

    def update_task_status(self, task_id: str, status: TaskStatus) -> None:
        with self._lock:
            conn = self._conn()
            conn.execute("UPDATE tasks SET status=? WHERE id=?", (status.value, task_id))
            conn.commit()

    def _tasks(self, conn: sqlite3.Connection, plan_id: str) -> list[Task]:
        rows = conn.execute(
            "SELECT id,title,body,status,\"order\" FROM tasks WHERE plan_id=? ORDER BY \"order\"",
            (plan_id,),
        ).fetchall()
        return [Task(id=r["id"], title=r["title"], body=r["body"],
                     status=TaskStatus(r["status"]), order=r["order"]) for r in rows]

    # ---------- outcomes ----------
    def add_outcome(self, outcome: Outcome, actor: str = "api") -> Outcome:
        with self._lock:
            conn = self._conn()
            conn.execute(
                "INSERT OR REPLACE INTO outcomes(task_id,plan_id,passed,label,confidence,agreement,"
                "exit_code,duration_ms,last_line,head,created_at) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                (outcome.task_id, outcome.plan_id, int(outcome.passed), outcome.label,
                 outcome.confidence, outcome.agreement, outcome.exit_code, outcome.duration_ms,
                 outcome.last_line, outcome.head, outcome.created_at or _utcnow()),
            )
            self._audit(conn, actor, "outcome.recorded",
                        {"task_id": outcome.task_id, "label": outcome.label,
                         "passed": outcome.passed, "exit_code": outcome.exit_code})
            conn.commit()
        if not outcome.created_at:
            outcome.created_at = _utcnow()
        return outcome

    def outcomes_for_task(self, task_id: str) -> Optional[Outcome]:
        with self._lock:
            row = self._conn().execute(
                "SELECT task_id,plan_id,passed,label,confidence,agreement,exit_code,duration_ms,"
                "last_line,head,created_at FROM outcomes WHERE task_id=?", (task_id,)
            ).fetchone()
        if row is None:
            return None
        return Outcome(task_id=row["task_id"], plan_id=row["plan_id"], passed=bool(row["passed"]),
                       label=row["label"], confidence=row["confidence"], agreement=row["agreement"],
                       exit_code=row["exit_code"], duration_ms=row["duration_ms"],
                       last_line=row["last_line"], head=row["head"], created_at=row["created_at"])

    def list_outcomes(self, f: Filter) -> tuple[list[ResultRow], int]:
        with self._lock:
            conn = self._conn()
            params: list = []
            where: list[str] = []
            if f.plan_id:
                where.append("o.plan_id=?")
                params.append(f.plan_id)
            if f.label:
                where.append("o.label=?")
                params.append(f.label)
            if f.q:
                like = f"%{_escape_like(f.q)}%"
                where.append("(o.last_line LIKE ? ESCAPE '\\' OR o.head LIKE ? ESCAPE '\\' OR t.title LIKE ? ESCAPE '\\')")
                params.extend([like, like, like])
            clause = ("WHERE " + " AND ".join(where)) if where else ""
            order = "DESC" if f.order.endswith("desc") else "ASC"
            rows = conn.execute(
                f"SELECT o.task_id,o.plan_id,o.passed,o.label,o.confidence,o.agreement,"
                f"o.exit_code,o.duration_ms,o.last_line,o.head,o.created_at,"
                f"t.title,p.name AS plan_name "
                f"FROM outcomes o JOIN tasks t ON t.id=o.task_id AND t.plan_id=o.plan_id "
                f"JOIN plans p ON p.id=o.plan_id {clause} "
                f"ORDER BY o.created_at {order} LIMIT ? OFFSET ?",
                (*params, f.limit, f.offset),
            ).fetchall()
            total = int(conn.execute(
                f"SELECT COUNT(*) FROM outcomes o JOIN tasks t ON t.id=o.task_id AND t.plan_id=o.plan_id "
                f"{clause}",
                tuple(params),
            ).fetchone()[0])
        result_rows = [
            ResultRow(task_id=r["task_id"], plan_id=r["plan_id"], plan_name=r["plan_name"],
                      title=r["title"], label=r["label"], confidence=r["confidence"],
                      agreement=r["agreement"], exit_code=r["exit_code"],
                      duration_ms=r["duration_ms"], last_line=r["last_line"],
                      head=r["head"], created_at=r["created_at"])
            for r in rows
        ]
        return result_rows, total

    # ---------- audit ----------
    def _audit(self, conn: sqlite3.Connection, actor: str, action: str, detail: dict) -> None:
        conn.execute(
            "INSERT INTO audit(actor,action,detail,created_at) VALUES(?,?,?,?)",
            (actor, action, json.dumps(detail, default=str, sort_keys=True), _utcnow()),
        )
        log_event(action, {"actor": actor, **detail})


from ..models.plan import PlanStatus  # noqa: E402  (avoids import cycle at module load)