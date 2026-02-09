"""
Database module for Sunny Research Assistant
Manages SQLite storage for papers, notes, experiments, and research tasks
"""

import sqlite3
import json
import os
from datetime import datetime
from typing import Dict, List, Optional, Any
from pathlib import Path
from contextlib import contextmanager


class ResearchDatabase:
    """SQLite database for storing research data with transaction support"""
    
    def __init__(self, db_path: str = None):
        """Initialize database connection and create tables if needed"""
        if db_path is None:
            db_path = Path(__file__).parent.parent / "research_data.db"
        
        self.db_path = db_path
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row  # Return rows as dictionaries
        # Enable foreign keys
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.create_tables()
        self.ensure_default_paper()
    
    @contextmanager
    def transaction(self):
        """Context manager for database transactions with automatic rollback on error"""
        try:
            yield self.conn
            self.conn.commit()
        except Exception as e:
            self.conn.rollback()
            print(f"[Database Error] Transaction rolled back: {e}")
            raise
    
    def create_tables(self):
        """Create all necessary tables"""
        cursor = self.conn.cursor()
        
        # Papers table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS papers (
                paper_id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                authors TEXT,  -- JSON array
                year INTEGER,
                first_seen TEXT NOT NULL,
                last_viewed TEXT,
                summary TEXT,
                screenshot_path TEXT,
                metadata TEXT  -- JSON for additional fields
            )
        """)
        
        # Notes table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS notes (
                note_id TEXT PRIMARY KEY,
                paper_id TEXT,
                content TEXT NOT NULL,
                section TEXT,
                timestamp TEXT NOT NULL,
                thought_signature TEXT,  -- AI's reasoning process
                note_type TEXT,  -- 'user' or 'ai_critique'
                FOREIGN KEY (paper_id) REFERENCES papers(paper_id)
            )
        """)
        
        # Experiments table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS experiments (
                experiment_id TEXT PRIMARY KEY,
                paper_id TEXT,
                figure_reference TEXT,
                code TEXT NOT NULL,
                output TEXT,
                plots TEXT,  -- JSON array of base64 images
                status TEXT NOT NULL,  -- 'success', 'failed', 'running'
                match_score REAL,
                error_message TEXT,
                timestamp TEXT NOT NULL,
                thought_signature TEXT,
                FOREIGN KEY (paper_id) REFERENCES papers(paper_id)
            )
        """)
        
        # Research tasks table (for deep research)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS research_tasks (
                task_id TEXT PRIMARY KEY,
                query TEXT NOT NULL,
                findings TEXT,
                related_papers TEXT,  -- JSON array
                search_strategy TEXT,
                status TEXT NOT NULL,  -- 'completed', 'running', 'failed'
                timestamp TEXT NOT NULL
            )
        """)
        
        # Relationships table (for paper connections)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS relationships (
                relationship_id INTEGER PRIMARY KEY AUTOINCREMENT,
                from_paper_id TEXT,
                to_paper_id TEXT,
                relationship_type TEXT,  -- 'cites', 'contradicts', 'confirms', 'extends'
                confidence REAL,
                source TEXT,  -- 'deep_research', 'user_note', 'experiment_comparison'
                timestamp TEXT NOT NULL,
                FOREIGN KEY (from_paper_id) REFERENCES papers(paper_id),
                FOREIGN KEY (to_paper_id) REFERENCES papers(paper_id)
            )
        """)
        
        # Conversation history table (NEW - for persistent context)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS conversation_history (
                message_id INTEGER PRIMARY KEY AUTOINCREMENT,
                paper_id TEXT,
                role TEXT NOT NULL,  -- 'user' or 'assistant'
                content TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                session_id TEXT,  -- To group messages by session
                FOREIGN KEY (paper_id) REFERENCES papers(paper_id)
            )
        """)
        
        # Memory entries table (NEW - for persistent memory)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS memory_entries (
                memory_id INTEGER PRIMARY KEY AUTOINCREMENT,
                paper_id TEXT,
                detail TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                session_id TEXT,  -- To group memories by session
                FOREIGN KEY (paper_id) REFERENCES papers(paper_id)
            )
        """)
        
        self.conn.commit()
    
    def ensure_default_paper(self):
        """Ensure a default 'unknown' paper exists for experiments without paper context"""
        try:
            cursor = self.conn.cursor()
            # Check if unknown paper already exists
            cursor.execute("SELECT paper_id FROM papers WHERE paper_id = ?", ("unknown",))
            if not cursor.fetchone():
                # Create default unknown paper
                cursor.execute("""
                    INSERT INTO papers 
                    (paper_id, title, authors, year, first_seen, last_viewed, summary, screenshot_path, metadata)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    "unknown",
                    "Unknown/Unsourced Code",
                    json.dumps([]),
                    None,
                    datetime.now().isoformat(),
                    datetime.now().isoformat(),
                    "Default paper for experiments run without analyzing a source paper",
                    None,
                    json.dumps({})
                ))
                self.conn.commit()
                print("[Database] Created default 'unknown' paper for uncategorized experiments")
        except Exception as e:
            print(f"[Warning] Could not create default paper: {e}")
    
    # ========== PAPERS ==========
    
    def add_paper(self, paper_data: Dict[str, Any]) -> str:
        """Add a new paper to the database"""
        cursor = self.conn.cursor()
        
        paper_id = paper_data.get('paper_id', f"paper_{datetime.now().strftime('%Y%m%d_%H%M%S')}")
        
        cursor.execute("""
            INSERT OR REPLACE INTO papers 
            (paper_id, title, authors, year, first_seen, last_viewed, summary, screenshot_path, metadata)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            paper_id,
            paper_data.get('title', 'Untitled'),
            json.dumps(paper_data.get('authors', [])),
            paper_data.get('year'),
            paper_data.get('first_seen', datetime.now().isoformat()),
            datetime.now().isoformat(),
            paper_data.get('summary'),
            paper_data.get('screenshot_path'),
            json.dumps(paper_data.get('metadata', {}))
        ))
        
        self.conn.commit()
        return paper_id
    
    def get_paper(self, paper_id: str) -> Optional[Dict]:
        """Get a paper by ID"""
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM papers WHERE paper_id = ?", (paper_id,))
        row = cursor.fetchone()
        
        if row:
            return dict(row)
        return None
    
    def get_all_papers(self) -> List[Dict]:
        """Get all papers"""
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM papers ORDER BY last_viewed DESC")
        return [dict(row) for row in cursor.fetchall()]
    
    def update_paper_last_viewed(self, paper_id: str):
        """Update the last viewed timestamp for a paper"""
        cursor = self.conn.cursor()
        cursor.execute("""
            UPDATE papers SET last_viewed = ? WHERE paper_id = ?
        """, (datetime.now().isoformat(), paper_id))
        self.conn.commit()
    
    # ========== NOTES ==========
    
    def add_note(self, note_data: Dict[str, Any]) -> str:
        """Add a note (user or AI critique)"""
        cursor = self.conn.cursor()
        
        note_id = note_data.get('note_id', f"note_{datetime.now().strftime('%Y%m%d_%H%M%S%f')}")
        
        cursor.execute("""
            INSERT INTO notes 
            (note_id, paper_id, content, section, timestamp, thought_signature, note_type)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            note_id,
            note_data.get('paper_id'),
            note_data.get('content'),
            note_data.get('section'),
            note_data.get('timestamp', datetime.now().isoformat()),
            note_data.get('thought_signature'),
            note_data.get('note_type', 'user')
        ))
        
        self.conn.commit()
        return note_id
    
    def get_notes_for_paper(self, paper_id: str) -> List[Dict]:
        """Get all notes for a specific paper"""
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM notes WHERE paper_id = ? ORDER BY timestamp ASC", (paper_id,))
        return [dict(row) for row in cursor.fetchall()]
    
    def get_all_notes(self) -> List[Dict]:
        """Get all notes"""
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM notes ORDER BY timestamp DESC")
        return [dict(row) for row in cursor.fetchall()]
    
    # ========== EXPERIMENTS ==========
    
    def add_experiment(self, exp_data: Dict[str, Any]) -> str:
        """Add an experiment record"""
        cursor = self.conn.cursor()
        
        exp_id = exp_data.get('experiment_id', f"exp_{datetime.now().strftime('%Y%m%d_%H%M%S')}")
        
        cursor.execute("""
            INSERT INTO experiments 
            (experiment_id, paper_id, figure_reference, code, output, plots, 
             status, match_score, error_message, timestamp, thought_signature)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            exp_id,
            exp_data.get('paper_id'),
            exp_data.get('figure_reference'),
            exp_data.get('code'),
            exp_data.get('output'),
            json.dumps(exp_data.get('plots', [])),
            exp_data.get('status', 'running'),
            exp_data.get('match_score'),
            exp_data.get('error_message'),
            exp_data.get('timestamp', datetime.now().isoformat()),
            exp_data.get('thought_signature')
        ))
        
        self.conn.commit()
        return exp_id
    
    def update_experiment_status(self, exp_id: str, status: str, output: str = None, 
                                 error_message: str = None, match_score: float = None):
        """Update experiment status and results"""
        cursor = self.conn.cursor()
        cursor.execute("""
            UPDATE experiments 
            SET status = ?, output = ?, error_message = ?, match_score = ?
            WHERE experiment_id = ?
        """, (status, output, error_message, match_score, exp_id))
        self.conn.commit()
    
    def get_experiments_for_paper(self, paper_id: str) -> List[Dict]:
        """Get all experiments for a specific paper"""
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM experiments WHERE paper_id = ? ORDER BY timestamp DESC", (paper_id,))
        return [dict(row) for row in cursor.fetchall()]
    
    def get_all_experiments(self) -> List[Dict]:
        """Get all experiments"""
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM experiments ORDER BY timestamp DESC")
        return [dict(row) for row in cursor.fetchall()]
    
    def get_running_experiments(self) -> List[Dict]:
        """Get all currently running experiments"""
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM experiments WHERE status = 'running' ORDER BY timestamp ASC")
        return [dict(row) for row in cursor.fetchall()]
    
    # ========== RESEARCH TASKS ==========
    
    def add_research_task(self, task_data: Dict[str, Any]) -> str:
        """Add a research task"""
        cursor = self.conn.cursor()
        
        task_id = task_data.get('task_id', f"task_{datetime.now().strftime('%Y%m%d_%H%M%S')}")
        
        cursor.execute("""
            INSERT INTO research_tasks 
            (task_id, query, findings, related_papers, search_strategy, status, timestamp)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            task_id,
            task_data.get('query'),
            task_data.get('findings'),
            json.dumps(task_data.get('related_papers', [])),
            task_data.get('search_strategy'),
            task_data.get('status', 'running'),
            task_data.get('timestamp', datetime.now().isoformat())
        ))
        
        self.conn.commit()
        return task_id
    
    def update_research_task(self, task_id: str, findings: str, related_papers: List[Dict], status: str = 'completed'):
        """Update research task with findings"""
        cursor = self.conn.cursor()
        cursor.execute("""
            UPDATE research_tasks 
            SET findings = ?, related_papers = ?, status = ?
            WHERE task_id = ?
        """, (findings, json.dumps(related_papers), status, task_id))
        self.conn.commit()
    
    def get_research_task(self, task_id: str) -> Optional[Dict]:
        """Get a research task by ID"""
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM research_tasks WHERE task_id = ?", (task_id,))
        row = cursor.fetchone()
        
        if row:
            return dict(row)
        return None
    
    # ========== RELATIONSHIPS ==========
    
    def add_relationship(self, from_paper: str, to_paper: str, rel_type: str, 
                        confidence: float, source: str):
        """Add a relationship between papers"""
        cursor = self.conn.cursor()
        cursor.execute("""
            INSERT INTO relationships 
            (from_paper_id, to_paper_id, relationship_type, confidence, source, timestamp)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (from_paper, to_paper, rel_type, confidence, source, datetime.now().isoformat()))
        self.conn.commit()
    
    def get_relationships_for_paper(self, paper_id: str) -> List[Dict]:
        """Get all relationships involving a paper"""
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT * FROM relationships 
            WHERE from_paper_id = ? OR to_paper_id = ?
            ORDER BY confidence DESC
        """, (paper_id, paper_id))
        return [dict(row) for row in cursor.fetchall()]
    
    # ========== UTILITY ==========
    
    def get_stats(self) -> Dict[str, int]:
        """Get database statistics"""
        cursor = self.conn.cursor()
        
        stats = {}
        stats['total_papers'] = cursor.execute("SELECT COUNT(*) FROM papers").fetchone()[0]
        stats['total_notes'] = cursor.execute("SELECT COUNT(*) FROM notes").fetchone()[0]
        stats['total_experiments'] = cursor.execute("SELECT COUNT(*) FROM experiments").fetchone()[0]
        stats['successful_experiments'] = cursor.execute(
            "SELECT COUNT(*) FROM experiments WHERE status = 'success'"
        ).fetchone()[0]
        stats['failed_experiments'] = cursor.execute(
            "SELECT COUNT(*) FROM experiments WHERE status = 'failed'"
        ).fetchone()[0]
        stats['running_experiments'] = cursor.execute(
            "SELECT COUNT(*) FROM experiments WHERE status = 'running'"
        ).fetchone()[0]
        
        return stats
    
    # ========== CONVERSATION HISTORY ==========
    
    def add_conversation_message(self, paper_id: str, role: str, content: str, session_id: str = None) -> int:
        """Add a message to conversation history"""
        cursor = self.conn.cursor()
        
        cursor.execute("""
            INSERT INTO conversation_history (paper_id, role, content, timestamp, session_id)
            VALUES (?, ?, ?, ?, ?)
        """, (paper_id, role, content, datetime.now().isoformat(), session_id))
        
        self.conn.commit()
        return cursor.lastrowid
    
    def get_conversation_history(self, paper_id: str = None, limit: int = 20) -> List[Dict]:
        """Get conversation history for a paper or all"""
        cursor = self.conn.cursor()
        
        if paper_id:
            cursor.execute("""
                SELECT message_id, paper_id, role, content, timestamp, session_id
                FROM conversation_history
                WHERE paper_id = ?
                ORDER BY timestamp DESC
                LIMIT ?
            """, (paper_id, limit))
        else:
            cursor.execute("""
                SELECT message_id, paper_id, role, content, timestamp, session_id
                FROM conversation_history
                ORDER BY timestamp DESC
                LIMIT ?
            """, (limit,))
        
        return [dict(row) for row in cursor.fetchall()]
    
    def clear_conversation_history(self, paper_id: str = None):
        """Clear conversation history"""
        cursor = self.conn.cursor()
        
        if paper_id:
            cursor.execute("DELETE FROM conversation_history WHERE paper_id = ?", (paper_id,))
        else:
            cursor.execute("DELETE FROM conversation_history")
        
        self.conn.commit()
    
    # ========== MEMORY ENTRIES ==========
    
    def add_memory(self, paper_id: str, detail: str, session_id: str = None) -> int:
        """Add a memory entry"""
        cursor = self.conn.cursor()
        
        cursor.execute("""
            INSERT INTO memory_entries (paper_id, detail, timestamp, session_id)
            VALUES (?, ?, ?, ?)
        """, (paper_id, detail, datetime.now().isoformat(), session_id))
        
        self.conn.commit()
        return cursor.lastrowid
    
    def get_memory(self, paper_id: str = None, limit: int = 10) -> List[Dict]:
        """Get memory entries for a paper or all"""
        cursor = self.conn.cursor()
        
        if paper_id:
            cursor.execute("""
                SELECT memory_id, paper_id, detail, timestamp, session_id
                FROM memory_entries
                WHERE paper_id = ?
                ORDER BY timestamp DESC
                LIMIT ?
            """, (paper_id, limit))
        else:
            cursor.execute("""
                SELECT memory_id, paper_id, detail, timestamp, session_id
                FROM memory_entries
                ORDER BY timestamp DESC
                LIMIT ?
            """, (limit,))
        
        return [dict(row) for row in cursor.fetchall()]
    
    def close(self):
        """Close database connection"""
        self.conn.close()
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()


# Singleton instance
_db_instance = None

def get_database() -> ResearchDatabase:
    """Get or create the database singleton instance"""
    global _db_instance
    if _db_instance is None:
        _db_instance = ResearchDatabase()
    return _db_instance
