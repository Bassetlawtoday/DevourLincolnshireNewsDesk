import sqlite3
from pathlib import Path


DATABASE = Path(__file__).resolve().parent.parent / "data" / "newsdesk.db"


PLANNING_COLUMNS = (
    "reference",
    "alt_reference",
    "planning_authority",
    "planning_source_key",
    "address",
    "proposal",
    "status",
    "decision",
    "received_date",
    "validated_date",
    "decision_date",
    "appeal_status",
    "appeal_decision",
    "category",
    "score",
    "notes",
    "url",
    "imported",
)


REQUIRED_COLUMNS = {
    "alt_reference": "TEXT",
    "planning_authority": "TEXT",
    "planning_source_key": "TEXT",
    "status": "TEXT",
    "received_date": "TEXT",
    "validated_date": "TEXT",
    "appeal_status": "TEXT",
    "appeal_decision": "TEXT",
    "notes": "TEXT",
    "url": "TEXT",
    "imported": "TIMESTAMP",
}


def get_connection():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn


def _create_planning_table(cur):
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS planning(
            reference TEXT NOT NULL,
            alt_reference TEXT,
            planning_authority TEXT,
            planning_source_key TEXT NOT NULL DEFAULT 'legacy_bassetlaw',
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
            url TEXT,
            imported TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY(planning_source_key, reference)
        )
        """
    )


def create_database():
    DATABASE.parent.mkdir(parents=True, exist_ok=True)

    conn = get_connection()
    cur = conn.cursor()

    _create_planning_table(cur)

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

    cur.execute("PRAGMA table_info(planning)")
    table_info = cur.fetchall()
    primary_key_columns = [
        row["name"]
        for row in sorted(table_info, key=lambda row: row["pk"])
        if row["pk"]
    ]

    if primary_key_columns == ["reference"]:
        legacy_columns = {row["name"] for row in table_info}
        cur.execute("ALTER TABLE planning RENAME TO planning_legacy")
        _create_planning_table(cur)
        column_list = ", ".join(PLANNING_COLUMNS)
        selected_columns = ", ".join(
            "COALESCE(NULLIF(planning_source_key, ''), 'legacy_bassetlaw')"
            if column == "planning_source_key"
            else column if column in legacy_columns
            else "CURRENT_TIMESTAMP" if column == "imported"
            else f"NULL AS {column}"
            for column in PLANNING_COLUMNS
        )
        cur.execute(
            f"INSERT OR REPLACE INTO planning ({column_list}) "
            f"SELECT {selected_columns} FROM planning_legacy"
        )
        cur.execute("DROP TABLE planning_legacy")

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
            planning_authority,
            planning_source_key,
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
            notes,
            url
        )
        VALUES(
            ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
        )
        """,
        (
            app.reference,
            app.alt_reference,
            getattr(app, "planning_authority", ""),
            getattr(app, "planning_source_key", "") or "legacy_bassetlaw",
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
            getattr(app, "url", ""),
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
