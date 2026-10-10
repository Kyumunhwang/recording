"""Data models and schemas for counseling sessions."""
from datetime import datetime
from typing import List, Optional
from enum import Enum
from pydantic import BaseModel, Field

class SessionStatus(str, Enum):
    SAVED_LOCAL = "SAVED_LOCAL"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"

class TranscriptSegment(BaseModel):
    speaker: str = Field(..., description="Speaker identifier, e.g. 상담교사 김진학 or 학생 김민준")
    timestamp: str = Field(..., description="Timestamp of the utterance, e.g. 00:15")
    text: str = Field(..., description="Transcribed spoken text")
    tags: Optional[List[str]] = Field(default_factory=list, description="Extracted keywords or domain terms")

class CounselingSummary(BaseModel):
    overallReview: str = Field(..., description="Overall analysis and guidance conclusion")
    keyTopics: List[str] = Field(default_factory=list, description="Bullet points of key issues discussed")
    actionItems: List[str] = Field(default_factory=list, description="Actionable next steps for teacher and student")

class SessionBase(BaseModel):
    teacherEmail: str = Field(..., description="Teacher's Google account email for folder routing")
    teacherName: str = Field(default="상담교사", description="Teacher name")
    studentName: str = Field(..., description="Student and parent identity entered by teacher")
    topic: str = Field(..., description="Main topic or target major of consultation")
    counselingDate: str = Field(..., description="Session date YYYY-MM-DD")
    startTime: str = Field(..., description="Start time HH:MM:SS")
    endTime: str = Field(..., description="End time HH:MM:SS")
    durationSeconds: int = Field(..., description="Total elapsed seconds")
    durationFormatted: str = Field(..., description="Formatted duration e.g. 00:18:42")

class SessionCreate(SessionBase):
    audioFileName: Optional[str] = None

class SessionRecord(SessionBase):
    sessionId: str
    status: SessionStatus = SessionStatus.SAVED_LOCAL
    audioFilePath: Optional[str] = None
    transcript: Optional[List[TranscriptSegment]] = None
    summary: Optional[CounselingSummary] = None
    cloudDocUrl: Optional[str] = None
    cloudAudioUrl: Optional[str] = None
    createdAt: str = Field(default_factory=lambda: datetime.now().isoformat())
    updatedAt: str = Field(default_factory=lambda: datetime.now().isoformat())
