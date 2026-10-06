from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3

from .models import Vacancy, VacancyStatus, utc_now


class JobsRepository:
    def __init__(self, path: str | Path = Path("data") / "jobs_desk.sqlite") -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialise()

    @contextmanager
    def _connect(self):
        connection = sqlite3.connect(self.path, timeout=20)
        connection.row_factory = sqlite3.Row
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _initialise(self) -> None:
        with self._connect() as connection:
            connection.executescript("""
                CREATE TABLE IF NOT EXISTS vacancies (
                    vacancy_id TEXT PRIMARY KEY,
                    publication_key TEXT NOT NULL,
                    status TEXT NOT NULL,
                    apply_token TEXT NOT NULL UNIQUE,
                    metricool_id TEXT NOT NULL DEFAULT '',
                    closing_date TEXT NOT NULL DEFAULT '',
                    submitted_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    payload_json TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_jobs_queue
                    ON vacancies(publication_key,status,submitted_at DESC);
                CREATE TABLE IF NOT EXISTS vacancy_audit (
                    audit_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    vacancy_id TEXT NOT NULL,
                    action TEXT NOT NULL,
                    actor TEXT NOT NULL DEFAULT '',
                    detail TEXT NOT NULL DEFAULT '',
                    occurred_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS apply_clicks_daily (
                    vacancy_id TEXT NOT NULL,
                    click_date TEXT NOT NULL,
                    click_count INTEGER NOT NULL DEFAULT 0,
                    PRIMARY KEY(vacancy_id,click_date)
                );
            """)

    def save(self, vacancy: Vacancy, *, action: str, actor: str = "", detail: str = "") -> None:
        vacancy.updated_at = utc_now()
        payload = json.dumps(vacancy.to_dict(), ensure_ascii=False)
        with self._connect() as connection:
            connection.execute(
                """INSERT INTO vacancies(vacancy_id,publication_key,status,apply_token,
                   metricool_id,closing_date,submitted_at,updated_at,payload_json)
                   VALUES(?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(vacancy_id) DO UPDATE SET publication_key=excluded.publication_key,
                   status=excluded.status,apply_token=excluded.apply_token,
                   metricool_id=excluded.metricool_id,closing_date=excluded.closing_date,
                   updated_at=excluded.updated_at,payload_json=excluded.payload_json""",
                (vacancy.vacancy_id, vacancy.publication_key, vacancy.status,
                 vacancy.apply_token, vacancy.metricool_id, vacancy.closing_date,
                 vacancy.submitted_at, vacancy.updated_at, payload),
            )
            connection.execute(
                "INSERT INTO vacancy_audit(vacancy_id,action,actor,detail,occurred_at) VALUES(?,?,?,?,?)",
                (vacancy.vacancy_id, action, actor, detail, utc_now()),
            )

    def get(self, vacancy_id: str) -> Vacancy | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT payload_json FROM vacancies WHERE vacancy_id=?", (vacancy_id,)
            ).fetchone()
        return Vacancy.from_dict(json.loads(row["payload_json"])) if row else None

    def by_apply_token(self, token: str) -> Vacancy | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT payload_json FROM vacancies WHERE apply_token=?", (token,)
            ).fetchone()
        return Vacancy.from_dict(json.loads(row["payload_json"])) if row else None

    def list(self, publication_key: str, *, statuses: tuple[str, ...] = ()) -> list[Vacancy]:
        sql = "SELECT payload_json FROM vacancies WHERE publication_key=?"
        values: list[str] = [publication_key]
        if statuses:
            sql += f" AND status IN ({','.join('?' for _ in statuses)})"
            values.extend(statuses)
        sql += " ORDER BY submitted_at DESC"
        with self._connect() as connection:
            rows = connection.execute(sql, values).fetchall()
        return [Vacancy.from_dict(json.loads(row["payload_json"])) for row in rows]

    def record_apply_click(self, vacancy_id: str, *, occurred_at: datetime | None = None) -> None:
        day = (occurred_at or datetime.now(timezone.utc)).date().isoformat()
        with self._connect() as connection:
            connection.execute(
                """INSERT INTO apply_clicks_daily(vacancy_id,click_date,click_count)
                   VALUES(?,?,1) ON CONFLICT(vacancy_id,click_date)
                   DO UPDATE SET click_count=click_count+1""",
                (vacancy_id, day),
            )

    def click_total(self, vacancy_id: str) -> int:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT COALESCE(SUM(click_count),0) total FROM apply_clicks_daily WHERE vacancy_id=?",
                (vacancy_id,),
            ).fetchone()
        return int(row["total"])

    def click_totals(self, publication_key: str) -> dict[str, int]:
        with self._connect() as connection:
            rows = connection.execute(
                """SELECT v.vacancy_id,COALESCE(SUM(c.click_count),0) total
                   FROM vacancies v LEFT JOIN apply_clicks_daily c
                   ON c.vacancy_id=v.vacancy_id
                   WHERE v.publication_key=? GROUP BY v.vacancy_id""",
                (publication_key,),
            ).fetchall()
        return {str(row["vacancy_id"]): int(row["total"]) for row in rows}

    def expire_closed(self, *, today: str) -> int:
        changed = 0
        live = (VacancyStatus.APPROVED.value, VacancyStatus.SENT_TO_METRICOOL.value)
        for publication in self._publication_keys():
            for vacancy in self.list(publication, statuses=live):
                if vacancy.closing_date and vacancy.closing_date < today:
                    vacancy.status = VacancyStatus.EXPIRED.value
                    self.save(vacancy, action="expired", actor="system")
                    changed += 1
        return changed

    def _publication_keys(self) -> list[str]:
        with self._connect() as connection:
            return [row[0] for row in connection.execute(
                "SELECT DISTINCT publication_key FROM vacancies"
            ).fetchall()]
