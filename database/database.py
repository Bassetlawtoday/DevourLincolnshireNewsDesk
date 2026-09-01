import sqlite3
from pathlib import Path


DATABASE = Path(__file__).resolve().parent.parent / "data" / "newsdesk.db"


REQUIRED_COLUMNS = {
    "alt_reference": "TEXT",
    "status": "TEXT",
    "received_date": "TEXT",
    "validated_date": "TEXT",
    "appeal_status": "TEXT",
    "appeal_decision": "TEXT",
    "notes": "TEXT",
    "imported": "TIMESTAMP",
}


def get_connection():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn


def create_database():
    DATABASE.parent.mkdir(parents=True, exist_ok=True)

    conn = get_connection()
    cur = conn.cursor()

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS planning(
            reference TEXT PRIMARY KEY,
            alt_reference TEXT,
            address TEXT,
            proposal TEXT,
            status TEXT,
            decision TEXT,
            received_date TEXT,
            validated_date TEXT,
            decision_date TEXT,
            appeal_status TEXT,
            appeal_decision TEXT,
            category TEXT,
            score INTEGER,
            notes TEXT,
            imported TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )

    cur.execute("PRAGMA table_info(planning)")
    existing_columns = {
        row["name"] for row in cur.fetchall()
    }

    for column_name, column_type in REQUIRED_COLUMNS.items():
        if column_name not in existing_columns:
            cur.execute(
                f"ALTER TABLE planning "
                f"ADD COLUMN {column_name} {column_type}"
            )

    conn.commit()
    conn.close()


def save_planning_application(app):
    conn = get_connection()
    cur = conn.cursor()

    cur.execute(
        """
        INSERT OR REPLACE INTO planning(
            reference,
            alt_reference,
            address,
            proposal,
            status,
            decision,
            received_date,
            validated_date,
            decision_date,
            appeal_status,
            appeal_decision,
            category,
            score,
            notes
        )
        VALUES(
            ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
        )
        """,
        (
            app.reference,
            app.alt_reference,
            app.address,
            app.proposal,
            app.status,
            app.decision,
            app.received_date,
            app.validated_date,
            app.decision_date,
            app.appeal_status,
            app.appeal_decision,
            app.category,
            app.score,
            app.notes,
        ),
    )

    conn.commit()
    conn.close()


def get_all_planning():
    conn = get_connection()
    cur = conn.cursor()

    cur.execute(
        """
        SELECT *
        FROM planning
        ORDER BY score DESC
        """
    )

    rows = cur.fetchall()
    conn.close()

    return rows


def get_newsworthy(minimum_score=25):
    conn = get_connection()
    cur = conn.cursor()

    cur.execute(
        """
        SELECT *
        FROM planning
        WHERE score >= ?
        ORDER BY score DESC
        """,
        (minimum_score,),
    )

    rows = cur.fetchall()
    conn.close()

    return rows


def application_exists(reference):
    conn = get_connection()
    cur = conn.cursor()

    cur.execute(
        """
        SELECT reference
        FROM planning
        WHERE reference = ?
        """,
        (reference,),
    )

    row = cur.fetchone()
    conn.close()

    return row is not None


def total_applications():
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("SELECT COUNT(*) FROM planning")

    total = cur.fetchone()[0]
    conn.close()

    return total


def delete_all():
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("DELETE FROM planning")

    conn.commit()
    conn.close()


create_database()