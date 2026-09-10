from sqlalchemy import inspect, text

from tutor_bot.db.models import Base

_TOPIC_COLUMNS = {
    "theory_kind": "ALTER TABLE topics ADD COLUMN theory_kind VARCHAR(16) NOT NULL DEFAULT 'text'",
    "theory_image_path": "ALTER TABLE topics ADD COLUMN theory_image_path VARCHAR(512) NULL",
    "assessment_required": "ALTER TABLE topics ADD COLUMN assessment_required INT NOT NULL DEFAULT 3",
}

_PROBLEM_COLUMNS = {
    "difficulty": "ALTER TABLE problems ADD COLUMN difficulty INT NOT NULL DEFAULT 1",
    "needs_review": "ALTER TABLE problems ADD COLUMN needs_review TINYINT(1) NOT NULL DEFAULT 0",
}


def apply_schema(sync_conn) -> None:
    Base.metadata.create_all(sync_conn)
    inspector = inspect(sync_conn)
    tables = set(inspector.get_table_names())
    if "topics" in tables:
        existing = {col["name"] for col in inspector.get_columns("topics")}
        for name, ddl in _TOPIC_COLUMNS.items():
            if name not in existing:
                sync_conn.execute(text(ddl))
    if "problems" in tables:
        existing = {col["name"] for col in inspector.get_columns("problems")}
        for name, ddl in _PROBLEM_COLUMNS.items():
            if name not in existing:
                sync_conn.execute(text(ddl))
    _backfill_editions(sync_conn)


def _backfill_editions(sync_conn) -> None:
    inspector = inspect(sync_conn)
    tables = set(inspector.get_table_names())
    if "topic_theories" in tables and "topics" in tables:
        sync_conn.execute(
            text(
                """
                INSERT INTO topic_theories (topic_id, edition, edition_count, body, kind, image_path)
                SELECT t.id, 1, 1, IFNULL(t.theory, ''), IFNULL(t.theory_kind, 'text'), t.theory_image_path
                FROM topics t
                WHERE NOT EXISTS (
                    SELECT 1 FROM topic_theories x WHERE x.topic_id = t.id
                )
                  AND (
                    (t.theory IS NOT NULL AND t.theory <> '')
                    OR t.theory_image_path IS NOT NULL
                  )
                """
            )
        )
    if "problem_hints" in tables and "problems" in tables:
        sync_conn.execute(
            text(
                """
                INSERT INTO problem_hints (problem_id, edition, edition_count, body)
                SELECT p.id, 1, 1, p.hint
                FROM problems p
                WHERE NOT EXISTS (
                    SELECT 1 FROM problem_hints x WHERE x.problem_id = p.id
                )
                  AND p.hint IS NOT NULL AND p.hint <> ''
                """
            )
        )
    if "problem_solutions" in tables and "problems" in tables:
        sync_conn.execute(
            text(
                """
                INSERT INTO problem_solutions (problem_id, edition, edition_count, body)
                SELECT p.id, 1, 1, p.solution
                FROM problems p
                WHERE NOT EXISTS (
                    SELECT 1 FROM problem_solutions x WHERE x.problem_id = p.id
                )
                  AND p.solution IS NOT NULL AND p.solution <> ''
                """
            )
        )
