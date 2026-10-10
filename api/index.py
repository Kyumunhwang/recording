"""FastAPI Serverless Application for Vercel Deployment."""
import os
import json
import base64
import time
import urllib.request
from typing import Optional
from datetime import datetime
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

app = FastAPI(title="Meeting Summary Serverless API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Vercel entrypoint handler
try:
    from mangum import Mangum
    handler = Mangum(app)
except ImportError:
    handler = app

GEMINI_MODEL = "gemini-3.8-flash"
SESSIONS_CACHE = {}

def get_gemini_api_key():
    return os.environ.get("GEMINI_API_KEY", "").strip()

def get_gas_webhook_url():
    return os.environ.get("GAS_WEBHOOK_URL", "").strip()

def upload_audio_to_gemini_file_api(audio_bytes: bytes, mime_type: str = "audio/mp4", display_name: str = "audio.m4a"):
    api_key = get_gemini_api_key()
    if not api_key:
        raise ValueError("GEMINI_API_KEY_NOT_FOUND")

    file_size = len(audio_bytes)
    start_url = f"https://generativelanguage.googleapis.com/upload/v1beta/files?key={api_key}"
    headers = {
        "X-Goog-Upload-Protocol": "resumable",
        "X-Goog-Upload-Command": "start",
        "X-Goog-Upload-Header-Content-Length": str(file_size),
        "X-Goog-Upload-Header-Content-Type": mime_type,
        "Content-Type": "application/json"
    }
    meta_body = json.dumps({"file": {"displayName": display_name}}).encode("utf-8")
    req = urllib.request.Request(start_url, data=meta_body, headers=headers, method="POST")

    with urllib.request.urlopen(req, timeout=30) as res:
        upload_url = res.headers.get("X-Goog-Upload-URL")

    if not upload_url:
        raise RuntimeError("Failed to retrieve resumable upload URL from Gemini File API")

    upload_headers = {
        "Content-Length": str(file_size),
        "X-Goog-Upload-Offset": "0",
        "X-Goog-Upload-Command": "upload, finalize"
    }
    upload_req = urllib.request.Request(upload_url, data=audio_bytes, headers=upload_headers, method="POST")

    with urllib.request.urlopen(upload_req, timeout=180) as upload_res:
        upload_resp = json.loads(upload_res.read().decode("utf-8"))
        file_info = upload_resp.get("file", {})
        file_uri = file_info.get("uri")
        file_name = file_info.get("name")

    poll_url = f"https://generativelanguage.googleapis.com/v1beta/{file_name}?key={api_key}"
    for _ in range(30):
        with urllib.request.urlopen(poll_url, timeout=10) as poll_res:
            poll_info = json.loads(poll_res.read().decode("utf-8"))
            if poll_info.get("state") == "ACTIVE":
                return file_uri
            elif poll_info.get("state") == "FAILED":
                raise RuntimeError(f"Gemini File processing failed: {poll_info.get('error')}")
        time.sleep(2)

    return file_uri

def call_gemini_api(contents_parts, system_instruction=None):
    api_key = get_gemini_api_key()
    if not api_key:
        raise ValueError("GEMINI_API_KEY_NOT_FOUND")

    url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent?key={api_key}"
    payload = {
        "contents": [{"parts": contents_parts}],
        "generationConfig": {"temperature": 0.2}
    }
    if system_instruction:
        payload["systemInstruction"] = {"parts": [{"text": system_instruction}]}

    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})

    with urllib.request.urlopen(req, timeout=180) as response:
        res_json = json.loads(response.read().decode("utf-8"))
        candidates = res_json.get("candidates", [])
        if candidates:
            text_parts = candidates[0].get("content", {}).get("parts", [])
            if text_parts:
                return text_parts[0].get("text", "")
        return "응답을 파싱하지 못했습니다."

@app.get("/api/status")
def get_status():
    return {
        "hasKey": bool(get_gemini_api_key()),
        "model": GEMINI_MODEL,
        "hasGas": bool(get_gas_webhook_url()),
        "gasUrl": get_gas_webhook_url()
    }

@app.post("/api/settings/key")
async def save_settings(data: dict):
    if data.get("geminiApiKey"):
        os.environ["GEMINI_API_KEY"] = data["geminiApiKey"].strip()
    if data.get("gasWebhookUrl"):
        os.environ["GAS_WEBHOOK_URL"] = data["gasWebhookUrl"].strip()
    return {"status": "success", "model": GEMINI_MODEL}

@app.get("/api/sessions/{session_id}")
def get_session(session_id: str):
    record = SESSIONS_CACHE.get(session_id)
    if not record:
        raise HTTPException(status_code=404, detail="Session not found")
    return record

@app.post("/api/sessions/upload-transcribe")
async def upload_transcribe(
    teacherEmail: str = Form("counselor@school.kr"),
    teacherName: str = Form("나경식 교사 (Mr. David Nah)"),
    participants: str = Form("상담교사 나경식(Mr. David Nah), 상담학생: "),
    topic: str = Form("상담주제는 "),
    counselingDate: str = Form(None),
    startTime: str = Form(None),
    audioFile: Optional[UploadFile] = File(None)
):
    now = datetime.now()
    session_id = f"CS-{now.strftime('%Y%m%d-%H%M%S')}"
    counseling_date = counselingDate or now.strftime("%Y-%m-%d")
    start_time = startTime or now.strftime("%H:%M")

    audio_bytes = await audioFile.read() if audioFile else None
    mime_type = "audio/mp4"
    api_key = get_gemini_api_key()
    raw_transcript = ""

    if api_key and audio_bytes and len(audio_bytes) > 1024:
        prompt_text = (
            f"당신은 고등학교 진학 상담 전문 기록원입니다.\n"
            f"첨부된 음성 파일을 듣고, 상담 교사와 학생(또는 학부모)의 대화 내용을 한국어로 충실하게 전사(STT)해 주세요.\n\n"
            f"[상담 정보]\n"
            f"- 참석자: {participants}\n"
            f"- 상담 주제: {topic}\n\n"
            f"[작성 규칙]\n"
            f"1. 목소리와 어조를 분석하여 화자를 분리해 [상담교사], [학생] 등의 형식으로 말머리를 붙이세요.\n"
            f"2. 불필요한 추임새는 다듬되, 대화의 핵심 내용과 맥락은 생략하지 마세요.\n"
            f"3. 입시 용어(세특, 모평, 학종, 전형명, 수능최저 등)를 문맥에 맞게 정확하게 표기해 주세요.\n"
            f"4. 오직 전사된 대화 원문 내용만 출력하세요 (인사말이나 부가 설명 제외)."
        )

        try:
            if len(audio_bytes) > 15 * 1024 * 1024:
                file_uri = upload_audio_to_gemini_file_api(audio_bytes, mime_type, f"{session_id}.m4a")
                contents_parts = [
                    {"fileData": {"mimeType": mime_type, "fileUri": file_uri}},
                    {"text": prompt_text}
                ]
            else:
                b64_audio = base64.b64encode(audio_bytes).decode("utf-8")
                contents_parts = [
                    {"inlineData": {"mimeType": mime_type, "data": b64_audio}},
                    {"text": prompt_text}
                ]

            raw_transcript = call_gemini_api(contents_parts)
        except Exception as e:
            raw_transcript = f"※ [전사 오류: {str(e)}]"
    else:
        raw_transcript = (
            f"[상담교사] 오늘 이야기 나눌 주제인 '{topic}'에 대해 이야기해보자.\n\n"
            f"[학생] 네 선생님, 이번 입시 준비 관련 조언 부탁드립니다."
        )

    record = {
        "sessionId": session_id,
        "teacherEmail": teacherEmail,
        "teacherName": teacherName,
        "participants": participants,
        "topic": topic,
        "counselingDate": counseling_date,
        "startTime": start_time,
        "rawTranscript": raw_transcript,
        "structuredSummary": None,
        "status": "TRANSCRIBED",
        "createdAt": now.isoformat()
    }
    SESSIONS_CACHE[session_id] = record
    return record

@app.post("/api/sessions/{session_id}/transcript")
async def update_transcript(session_id: str, data: dict):
    record = SESSIONS_CACHE.get(session_id, {})
    record["rawTranscript"] = data.get("rawTranscript", "")
    SESSIONS_CACHE[session_id] = record
    return record

@app.post("/api/sessions/{session_id}/summarize")
async def summarize_session(session_id: str):
    record = SESSIONS_CACHE.get(session_id, {})
    topic = record.get("topic", "진학 상담")
    counseling_date = record.get("counselingDate", datetime.now().strftime("%Y-%m-%d"))
    participants = record.get("participants", "상담교사, 학생")
    raw_text = record.get("rawTranscript", "")
    api_key = get_gemini_api_key()

    system_instruction = (
        "당신은 전문 비즈니스 기록원입니다.\n"
        "음성 인식 오류(오탈자, 불완전한 문장, 추임새 등)를 자연스럽게 보정하고, 아래 양식에 맞추어 명확하고 구조화된 '상담일지'형식으로 정리해 주세요.\n\n"
        "[정리 가이드라인]\n"
        "1. 단순 나열을 지양하고, 주제별로 그룹화하여 핵심 내용을 개조식(-, •)으로 작성할 것.\n"
        "2. 대화 중 확정된 결정 사항과 향후 진행할 액션 아이템을 명확히 구분할 것.\n"
        "3. 구어체는 명확한 문어체(~함, ~하기로 함)로 변환할 것."
    )

    prompt = (
        f"다음 상담 정보와 수정된 최종 대화 원문을 바탕으로 지정된 마크다운 양식 그대로 상담일지를 작성해 주세요.\n\n"
        f"[상담 정보]\n"
        f"- 안건 주제: {topic}\n"
        f"- 일시: {counseling_date} {record.get('startTime', '')}\n"
        f"- 참석자: {participants}\n\n"
        f"[대화 원문]\n"
        f"{raw_text}\n\n"
        f"[반드시 준수할 출력 양식]\n"
        f"# [{topic}]\n"
        f"- 일시: {counseling_date} {record.get('startTime', '')}\n"
        f"- 참석자: {participants}\n\n"
        f"## 1. 핵심 요약 (3줄 이내)\n"
        f"- [핵심 요약 1]\n"
        f"- [핵심 요약 2]\n"
        f"- [핵심 요약 3]\n\n"
        f"## 2. 주요 논의 내용 (주제별 정리)\n"
        f"### [주제 A]\n"
        f"- 대화 배경:\n"
        f"- 주요 대화 및 논점:\n\n"
        f"### [주제 B]\n"
        f"- 대화 배경:\n"
        f"- 주요 대화 및 논점:\n\n"
        f"## 3. 최종 결정 사항 (Decisions)\n"
        f"- \n\n"
        f"## 4. 후속 조치 및 진학 지도시 기록할 내용\n"
        f"| 상담 내용 | 학생명 | 요구사항/조언 | 비고 |\n"
        f"| :--- | :--- | :--- | :--- |\n"
        f"| ... | ... | ... | ... |\n"
    )

    try:
        formatted_summary = call_gemini_api([{"text": prompt}], system_instruction=system_instruction)
    except Exception as e:
        formatted_summary = "요약 처리 실패"

    record["structuredSummary"] = formatted_summary
    record["status"] = "SUMMARIZED"
    SESSIONS_CACHE[session_id] = record
    return record

@app.post("/api/sessions/{session_id}/sync-google")
async def sync_google(session_id: str):
    record = SESSIONS_CACHE.get(session_id, {})
    gas_url = get_gas_webhook_url()

    if not gas_url:
        return {
            "status": "success",
            "docUrl": f"https://docs.google.com/document/d/preview-{session_id}",
            "folderUrl": "https://drive.google.com"
        }

    payload = {
        "action": "SYNC_COUNSELING_RECORD",
        "teacherEmail": record.get("teacherEmail"),
        "teacherName": record.get("teacherName"),
        "session": {
            "sessionId": session_id,
            "participants": record.get("participants"),
            "topic": record.get("topic"),
            "counselingDate": record.get("counselingDate"),
            "startTime": record.get("startTime")
        },
        "rawTranscript": record.get("rawTranscript", ""),
        "structuredSummary": record.get("structuredSummary", "")
    }
    req = urllib.request.Request(gas_url, data=json.dumps(payload).encode("utf-8"), headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as gas_res:
        return json.loads(gas_res.read().decode("utf-8"))
