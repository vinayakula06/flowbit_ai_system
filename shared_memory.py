# shared_memory.py
import sqlite3
import json
from datetime import datetime
from typing import Dict, Any, List

class SharedMemory:
    def __init__(self, db_path="shared_memory.db"):
        self.db_path = db_path
        self._initialize_db()

    def _initialize_db(self):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS interactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT,
                input_metadata TEXT,
                classification TEXT,
                agent_outputs TEXT,
                chained_actions TEXT,
                decision_traces TEXT
            )
        """)
        conn.commit()
        conn.close()

    def write_interaction(
        self,
        input_metadata: Dict[str, Any],
        classification: Dict[str, str],
        agent_outputs: Dict[str, Any],
        chained_actions: List[str],
        decision_traces: List[str]
    ):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        timestamp = self.get_current_timestamp()
        cursor.execute(
            """
            INSERT INTO interactions (timestamp, input_metadata, classification, agent_outputs, chained_actions, decision_traces)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                timestamp,
                json.dumps(input_metadata),
                json.dumps(classification),
                json.dumps(agent_outputs),
                json.dumps(chained_actions),
                json.dumps(decision_traces)
            )
        )
        conn.commit()
        conn.close()

    def read_latest_interaction(self) -> Dict[str, Any]:
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM interactions ORDER BY id DESC LIMIT 1")
        row = cursor.fetchone()
        conn.close()
        if row:
            # Assuming the order of columns as in CREATE TABLE
            return {
                "id": row[0],
                "timestamp": row[1],
                "input_metadata": json.loads(row[2]),
                "classification": json.loads(row[3]),
                "agent_outputs": json.loads(row[4]),
                "chained_actions": json.loads(row[5]),
                "decision_traces": json.loads(row[6])
            }
        return {}

    def clear_memory(self):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM interactions")
        conn.commit()
        conn.close()

    @staticmethod
    def get_current_timestamp():
        return datetime.now().isoformat()