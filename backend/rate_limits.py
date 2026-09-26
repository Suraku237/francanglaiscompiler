import sqlite3
import time


class RateLimitExceeded(Exception):
    def __init__(self, retry_after: int):
        super().__init__("Too many requests. Please try again later.")
        self.retry_after = retry_after


def throttle(db: sqlite3.Connection, key: str, maximum: int, seconds: int) -> None:
    now = time.time()
    db.execute("BEGIN IMMEDIATE")
    db.execute("DELETE FROM limits WHERE expires <= ?", (now,))
    row = db.execute("SELECT count,expires FROM limits WHERE key=?", (key,)).fetchone()
    if row and row[0] >= maximum:
        raise RateLimitExceeded(max(1, int(row[1] - now)))
    db.execute(
        "INSERT INTO limits VALUES (?,1,?) ON CONFLICT(key) DO UPDATE SET count=count+1",
        (key, now + seconds),
    )
