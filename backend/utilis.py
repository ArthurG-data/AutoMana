from psycopg2.extensions import connection
from backend.dependancies import cursorDep
from fastapi import Request


def desactivate_expired(conn : connection =  cursorDep):
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE sessions SET active = FALSE
            WHERE active = TRUE
            AND EXPIRES_at < now();
            """
        )

        cur.execute(
            """
            UPDATE refresh_tokens
            SET revoked = TRUE
            WHERE revoved = FALSE
            AND refresh_token_expired_at < now();
            """
        )
        conn.commit()

