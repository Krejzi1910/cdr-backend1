"""
SQLite layer for Color Dice Rigged Backend.

Schema:
  rolls (token TEXT PRIMARY KEY, combo_key TEXT NOT NULL, count INT, colors TEXT, ts INT)
  INDEX rolls_combo_key on (combo_key, ts DESC)

Constants:
  combo_key = f"{count}|{','.join(colors)}"  e.g. "4|Red,Blue,Green,Yellow"
"""

import sqlite3
import time
import os
from typing import Optional, Dict, Any
from threading import RLock

COMBO_COUNTS = {2: 36, 3: 216, 4: 1296, 5: 7776, 6: 46656}


class DB:
    def __init__(self, path: str):
        self.path = path
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        # check_same_thread=False because FastAPI may call from different threads
        # but we serialize writes with a RLock anyway
        self._conn = sqlite3.connect(path, check_same_thread=False, isolation_level=None)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL;")
        self._conn.execute("PRAGMA synchronous=NORMAL;")
        self._lock = RLock()

    def init_schema(self):
        with self._lock:
            self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS rolls (
              token TEXT PRIMARY KEY,
              combo_key TEXT NOT NULL,
              count INTEGER NOT NULL,
              colors TEXT NOT NULL,
              ts INTEGER NOT NULL
            );
            CREATE INDEX IF NOT EXISTS rolls_combo_key_idx ON rolls(combo_key, ts DESC);
            CREATE INDEX IF NOT EXISTS rolls_count_idx ON rolls(count);
            """)

    def insert_roll(self, token: str, combo_key: str, count: int, colors: list, ts: Optional[int] = None) -> bool:
        if ts is None:
            ts = int(time.time())
        with self._lock:
            try:
                self._conn.execute(
                    "INSERT OR IGNORE INTO rolls (token, combo_key, count, colors, ts) VALUES (?,?,?,?,?)",
                    (token, combo_key, count, ",".join(colors), ts),
                )
                return True
            except sqlite3.Error:
                return False

    def find_token(self, combo_key: str, max_age_sec: Optional[int] = None) -> Optional[Dict[str, Any]]:
        with self._lock:
            if max_age_sec is None:
                row = self._conn.execute(
                    "SELECT token, ts FROM rolls WHERE combo_key = ? ORDER BY ts DESC LIMIT 1",
                    (combo_key,),
                ).fetchone()
            else:
                cutoff = int(time.time()) - max_age_sec
                row = self._conn.execute(
                    "SELECT token, ts FROM rolls WHERE combo_key = ? AND ts >= ? ORDER BY ts DESC LIMIT 1",
                    (combo_key, cutoff),
                ).fetchone()
            return dict(row) if row else None

    def total_count(self) -> int:
        with self._lock:
            return self._conn.execute("SELECT COUNT(*) FROM rolls").fetchone()[0]

    def coverage(self) -> Dict[int, float]:
        with self._lock:
            out = {}
            for n in (2, 3, 4, 5, 6):
                row = self._conn.execute(
                    "SELECT COUNT(DISTINCT combo_key) FROM rolls WHERE count = ?", (n,)
                ).fetchone()
                distinct = row[0] if row else 0
                out[n] = round(distinct / COMBO_COUNTS[n], 4)
            return out

    def last_token(self) -> Optional[str]:
        with self._lock:
            row = self._conn.execute("SELECT token FROM rolls ORDER BY ts DESC LIMIT 1").fetchone()
            return row["token"] if row else None
