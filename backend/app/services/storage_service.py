"""Service for local file storage and session persistence."""
import json
from datetime import datetime
from typing import List, Optional
from pathlib import Path

from app.core.config import settings
from app.models.schemas import SessionRecord, SessionCreate, SessionStatus

class StorageService:
    """Manages saving, retrieving, and updating counseling sessions on local disk."""

    def __init__(self):
        self.sessions_dir: Path = settings.SESSIONS_DIR
        self.recordings_dir: Path = settings.RECORDINGS_DIR

    def generate_session_id(self) -> str:
        """Generate a unique timestamped session ID."""
        now = datetime.now()
        return f"CS-{now.strftime('%Y%m%d-%H%M%S')}"

    def save_session(self, data: SessionCreate, audio_filename: Optional[str] = None) -> SessionRecord:
        """Save a new 1st-stage session record to disk immediately."""
        session_id = self.generate_session_id()
        audio_path = str(self.recordings_dir / audio_filename) if audio_filename else None
        
        record = SessionRecord(
            sessionId=session_id,
            status=SessionStatus.SAVED_LOCAL,
            audioFilePath=audio_path,
            createdAt=datetime.now().isoformat(),
            updatedAt=datetime.now().isoformat(),
            **data.model_dump(exclude={"audioFileName"})
        )

        file_path = self.sessions_dir / f"{session_id}.json"
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(record.model_dump(), f, ensure_ascii=False, indent=2)

        return record

    def get_session(self, session_id: str) -> Optional[SessionRecord]:
        """Load a session record by its ID."""
        file_path = self.sessions_dir / f"{session_id}.json"
        if not file_path.exists():
            return None
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            return SessionRecord(**data)

    def list_sessions(self) -> List[SessionRecord]:
        """List all sessions ordered by creation date descending."""
        sessions = []
        for file_path in self.sessions_dir.glob("*.json"):
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    sessions.append(SessionRecord(**data))
            except Exception:
                continue
        sessions.sort(key=lambda s: s.createdAt, reverse=True)
        return sessions

    def update_session(self, record: SessionRecord) -> SessionRecord:
        """Update an existing session with updated status or AI outputs."""
        record.updatedAt = datetime.now().isoformat()
        file_path = self.sessions_dir / f"{record.sessionId}.json"
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(record.model_dump(), f, ensure_ascii=False, indent=2)
        return record

storage_service = StorageService()
