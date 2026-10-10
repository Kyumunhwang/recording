"""FastAPI application entry point providing endpoints for audio recording, 1st-stage saving, and AI processing."""
from typing import List
from pathlib import Path
from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.core.config import settings
from app.models.schemas import SessionRecord, SessionCreate, SessionStatus
from app.services.storage_service import storage_service
from app.services.stt_service import stt_service
from app.services.llm_summarizer import llm_summarizer
from app.services.gas_client import gas_client

app = FastAPI(title=settings.APP_NAME, debug=settings.DEBUG)

# Enable CORS for local and web client access
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 1. First-Stage Quick Save Endpoint (Save audio & metadata immediately)
@app.post("/api/sessions/quick-save", response_model=SessionRecord)
async def quick_save_session(
    teacherEmail: str = Form(...),
    teacherName: str = Form("상담교사"),
    studentName: str = Form(...),
    topic: str = Form(...),
    counselingDate: str = Form(...),
    startTime: str = Form(...),
    endTime: str = Form(...),
    durationSeconds: int = Form(...),
    durationFormatted: str = Form(...),
    audioFile: UploadFile = File(None)
):
    """
    1차 즉시 저장 API:
    녹음 종료 즉시 호출되어 오디오 파일과 교사가 입력한 메타데이터를 로컬 디스크에 저장합니다.
    AI 요약을 기다리지 않고 즉시 반환하여 다음 상담을 바로 진행할 수 있도록 합니다.
    """
    audio_filename = None
    if audioFile:
        safe_ext = Path(audioFile.filename).suffix or ".m4a"
        audio_filename = f"REC_{counselingDate}_{startTime.replace(':', '')}_{studentName[:4]}{safe_ext}"
        dest_path = settings.RECORDINGS_DIR / audio_filename
        with open(dest_path, "wb") as f:
            content = await audioFile.read()
            f.write(content)

    session_create = SessionCreate(
        teacherEmail=teacherEmail,
        teacherName=teacherName,
        studentName=studentName,
        topic=topic,
        counselingDate=counselingDate,
        startTime=startTime,
        endTime=endTime,
        durationSeconds=durationSeconds,
        durationFormatted=durationFormatted,
        audioFileName=audio_filename
    )

    record = storage_service.save_session(session_create, audio_filename)
    return record

# 2. List all sessions (for pending summary queue & history)
@app.get("/api/sessions", response_model=List[SessionRecord])
def list_sessions():
    """Returns all consultation sessions (local records, pending, completed)."""
    return storage_service.list_sessions()

# 3. Get single session detail
@app.get("/api/sessions/{session_id}", response_model=SessionRecord)
def get_session(session_id: str):
    record = storage_service.get_session(session_id)
    if not record:
        raise HTTPException(status_code=404, detail="Session not found")
    return record

# 4. Process AI Summary & Sync with Google Drive (Triggered anytime later)
@app.post("/api/sessions/{session_id}/process-ai", response_model=SessionRecord)
async def process_session_ai(session_id: str):
    """
    2단계 AI 요약 및 클라우드 동기화 API:
    교사가 원할 때 버튼을 클릭하여 STT 원문 생성 -> LLM 요약 -> Google Drive(GAS) 저장을 순차 실행합니다.
    """
    record = storage_service.get_session(session_id)
    if not record:
        raise HTTPException(status_code=404, detail="Session not found")

    record.status = SessionStatus.PROCESSING
    storage_service.update_session(record)

    try:
        # Step A: STT Transcription
        audio_path = record.audioFilePath or ""
        transcript = await stt_service.transcribe(audio_path, record.studentName, record.topic)
        record.transcript = transcript

        # Step B: LLM Summarization
        summary = await llm_summarizer.summarize(record.studentName, record.topic, transcript)
        record.summary = summary

        # Step C: Google Apps Script Webhook Sync
        sync_result = await gas_client.sync_session(record)
        if sync_result.get("status") == "success":
            record.cloudDocUrl = sync_result.get("docUrl")
            record.cloudAudioUrl = sync_result.get("audioUrl")

        record.status = SessionStatus.COMPLETED
    except Exception as e:
        record.status = SessionStatus.FAILED
        raise HTTPException(status_code=500, detail=f"Processing failed: {str(e)}")
    finally:
        storage_service.update_session(record)

    return record

# Mount static files for the web interface
web_dir = Path(__file__).resolve().parent.parent.parent / "web"
if web_dir.exists():
    app.mount("/", StaticFiles(directory=str(web_dir), html=True), name="static")
