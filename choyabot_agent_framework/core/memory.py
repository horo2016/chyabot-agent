from typing import Optional, List
#!/usr/bin/env python3
import sqlite3
import json
import time
from typing import List, Dict, Optional
from dataclasses import dataclass
from pathlib import Path


@dataclass
class MemoryEntry:
    id: Optional[int]
    session_id: str
    role: str
    content: str
    metadata: Dict
    timestamp: float


class MemoryStore:
    def __init__(self, db_path: str = "memory/conversation.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()
        
    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS conversations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    metadata TEXT,
                    timestamp REAL NOT NULL
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_session ON conversations(session_id, timestamp)")
            
    def add(self, entry: MemoryEntry):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT INTO conversations (session_id, role, content, metadata, timestamp) VALUES (?, ?, ?, ?, ?)",
                (entry.session_id, entry.role, entry.content, json.dumps(entry.metadata), entry.timestamp)
            )
            
    def get_recent(self, session_id: str, limit: int = 20) -> List[MemoryEntry]:
        with sqlite3.connect(self.db_path) as conn:
            cur = conn.execute(
                "SELECT id, session_id, role, content, metadata, timestamp FROM conversations "
                "WHERE session_id = ? ORDER BY timestamp DESC LIMIT ?",
                (session_id, limit)
            )
            rows = cur.fetchall()
        return [MemoryEntry(r[0], r[1], r[2], r[3], json.loads(r[4]), r[5]) for r in reversed(rows)]