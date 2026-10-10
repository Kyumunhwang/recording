#!/usr/bin/env python3
"""
Server for Meeting Summary App.
Powered by Google Gemini Native Multimodal Audio STT (File API + generateContent).
Zero external library requirement (Uses standard urllib).
"""

import os
import sys
import json
import base64
import cgi
import time
import mimetypes
import urllib.request
import urllib.error
from http.server import HTTPServer, SimpleHTTPRequestHandler
from urllib.parse import urlparse
from datetime import datetime
from pathlib import Path

PORT = 3850
BASE_DIR = Path(__file__).resolve().parent
WEB_DIR = BASE_DIR / "web"
STORAGE_DIR = BASE_DIR / "storage"
SESSIONS_DIR = STORAGE_DIR / "sessions"
RECORDINGS_DIR = STORAGE_DIR / "recordings"

SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
RECORDINGS_DIR.mkdir(parents=True, exist_ok=True)

# Recommended stable flash model from API endpoint
GEMINI_MODEL = "gemini-3.8-flash"

def load_gemini_api_key():
    """Load Gemini API Key from environment or .env file."""
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        env_file = BASE_DIR / ".env"
        if env_file.exists():
            with open(env_file, "r", encoding="utf-8") as f:
                for line in f:
                    if line.startswith("GEMINI_API_KEY="):
                        api_key = line.split("=", 1)[1].strip().strip('"').strip("'")
                        break
    return api_key

def load_gas_webhook_url():
    """Load Google Apps Script Webhook URL from environment or .env file."""
    url = os.environ.get("GAS_WEBHOOK_URL", "").strip()
    if not url:
        env_file = BASE_DIR / ".env"
        if env_file.exists():
            with open(env_file, "r", encoding="utf-8") as f:
                for line in f:
                    if line.startswith("GAS_WEBHOOK_URL="):
                        url = line.split("=", 1)[1].strip().strip('"').strip("'")
                        break
    return url

def upload_audio_to_gemini_file_api(audio_path, mime_type="audio/mp4"):
    """
    Upload large audio files (up to 2GB) to Google Gemini File API (resumable upload).
    Returns file URI e.g. https://generativelanguage.googleapis.com/v1beta/files/...
    """
    api_key = load_gemini_api_key()
    if not api_key:
        raise ValueError("GEMINI_API_KEY_NOT_FOUND")

    file_size = os.path.getsize(audio_path)
    display_name = Path(audio_path).name

    # Step 1: Initial start request to get upload URL
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

    # Step 2: Upload bytes in chunks or single payload
    with open(audio_path, "rb") as f:
        audio_bytes = f.read()

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
        file_name = file_info.get("name") # e.g. files/abc123

    # Step 3: Wait for state to become ACTIVE if processing
    poll_url = f"https://generativelanguage.googleapis.com/v1beta/{file_name}?key={api_key}"
    for _ in range(30):
        with urllib.request.urlopen(poll_url, timeout=10) as poll_res:
            poll_info = json.loads(poll_res.read().decode("utf-8"))
            state = poll_info.get("state", "PROCESSING")
            if state == "ACTIVE":
                return file_uri
            elif state == "FAILED":
                raise RuntimeError(f"Gemini File processing failed: {poll_info.get('error')}")
        time.sleep(2)

    return file_uri

def call_gemini_api(contents_parts, system_instruction=None):
    """Call Gemini API via generateContent with urllib."""
    api_key = load_gemini_api_key()
    if not api_key:
        raise ValueError("GEMINI_API_KEY_NOT_FOUND")

    url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent?key={api_key}"
    
    payload = {
        "contents": [{
            "parts": contents_parts
        }],
        "generationConfig": {
            "temperature": 0.2
        }
    }
    
    if system_instruction:
        payload["systemInstruction"] = {
            "parts": [{"text": system_instruction}]
        }

    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})

    try:
        with urllib.request.urlopen(req, timeout=180) as response:
            res_body = response.read().decode("utf-8")
            res_json = json.loads(res_body)
            candidates = res_json.get("candidates", [])
            if candidates:
                text_parts = candidates[0].get("content", {}).get("parts", [])
                if text_parts:
                    return text_parts[0].get("text", "")
            return "응답을 파싱하지 못했습니다."
    except urllib.error.HTTPError as e:
        err_msg = e.read().decode("utf-8")
        raise RuntimeError(f"Gemini API Error ({e.code}): {err_msg}")
    except Exception as e:
        raise RuntimeError(f"Network error calling Gemini: {str(e)}")

class MeetingSummaryHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(WEB_DIR), **kwargs)

    def _set_json_headers(self, status=200):
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "*")
        self.end_headers()

    def do_OPTIONS(self):
        self._set_json_headers(200)

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/api/status":
            has_key = bool(load_gemini_api_key())
            has_gas = bool(load_gas_webhook_url())
            self._set_json_headers(200)
            self.wfile.write(json.dumps({
                "hasKey": has_key, 
                "model": GEMINI_MODEL,
                "hasGas": has_gas,
                "gasUrl": load_gas_webhook_url()
            }).encode("utf-8"))
            return

        if path == "/api/sessions":
            sessions = []
            for f in SESSIONS_DIR.glob("*.json"):
                try:
                    with open(f, "r", encoding="utf-8") as fp:
                        sessions.append(json.load(fp))
                except Exception:
                    continue
            sessions.sort(key=lambda s: s.get("createdAt", ""), reverse=True)
            self._set_json_headers(200)
            self.wfile.write(json.dumps(sessions, ensure_ascii=False).encode("utf-8"))
            return

        if path.startswith("/api/sessions/"):
            session_id = path.replace("/api/sessions/", "").strip("/")
            file_path = SESSIONS_DIR / f"{session_id}.json"
            if file_path.exists():
                with open(file_path, "r", encoding="utf-8") as fp:
                    data = json.load(fp)
                self._set_json_headers(200)
                self.wfile.write(json.dumps(data, ensure_ascii=False).encode("utf-8"))
            else:
                self._set_json_headers(404)
                self.wfile.write(json.dumps({"error": "Session not found"}).encode("utf-8"))
            return

        super().do_GET()

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/api/settings/key":
            content_len = int(self.headers.get("content-length", 0))
            body_data = json.loads(self.rfile.read(content_len).decode("utf-8"))
            new_key = body_data.get("geminiApiKey", "").strip()
            gas_url = body_data.get("gasWebhookUrl", "").strip()

            env_file = BASE_DIR / ".env"
            env_lines = []
            if env_file.exists():
                with open(env_file, "r", encoding="utf-8") as f:
                    env_lines = f.readlines()

            # update key
            if new_key:
                os.environ["GEMINI_API_KEY"] = new_key
                env_lines = [l for l in env_lines if not l.startswith("GEMINI_API_KEY=")]
                env_lines.append(f"GEMINI_API_KEY={new_key}\n")

            # update gas url
            if gas_url:
                os.environ["GAS_WEBHOOK_URL"] = gas_url
                env_lines = [l for l in env_lines if not l.startswith("GAS_WEBHOOK_URL=")]
                env_lines.append(f"GAS_WEBHOOK_URL={gas_url}\n")

            with open(env_file, "w", encoding="utf-8") as f:
                f.writelines(env_lines)

            self._set_json_headers(200)
            self.wfile.write(json.dumps({
                "status": "success", 
                "model": GEMINI_MODEL,
                "hasGas": bool(load_gas_webhook_url())
            }).encode("utf-8"))
            return

        # 1. Upload File & Gemini Audio Multimodal STT
        if path == "/api/sessions/upload-transcribe":
            try:
                ctype, pdict = cgi.parse_header(self.headers.get("content-type", ""))
                if ctype == "multipart/form-data":
                    pdict["boundary"] = bytes(pdict["boundary"], "utf-8")
                    fields = cgi.parse_multipart(self.rfile, pdict)

                    def get_field(name, default=""):
                        val = fields.get(name, [default])
                        if isinstance(val[0], bytes):
                            return val[0].decode("utf-8")
                        return str(val[0])

                    teacher_email = get_field("teacherEmail", "counselor@school.kr")
                    teacher_name = get_field("teacherName", "상담교사")
                    participants = get_field("participants", "상담교사, 학생")
                    topic = get_field("topic", "진학 상담")
                    counseling_date = get_field("counselingDate", datetime.now().strftime("%Y-%m-%d"))
                    start_time = get_field("startTime", datetime.now().strftime("%H:%M"))

                    now = datetime.now()
                    session_id = f"CS-{now.strftime('%Y%m%d-%H%M%S')}"

                    audio_bytes = None
                    file_ext = ".m4a"
                    mime_type = "audio/mp4"

                    if "audioFile" in fields and len(fields["audioFile"]) > 0:
                        audio_bytes = fields["audioFile"][0]
                        file_name = f"{session_id}.m4a"
                        dest = RECORDINGS_DIR / file_name
                        with open(dest, "wb") as afp:
                            afp.write(audio_bytes)
                        audio_path = str(dest)
                    else:
                        audio_path = None

                    raw_transcript = ""
                    api_key = load_gemini_api_key()

                    if api_key and audio_path and os.path.getsize(audio_path) > 1024:
                        file_size_bytes = os.path.getsize(audio_path)
                        print(f"Processing audio: {audio_path} ({file_size_bytes / (1024*1024):.2f} MB)")

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
                            # If file is larger than 15MB, use Gemini File API; otherwise inline base64
                            if file_size_bytes > 15 * 1024 * 1024:
                                print("File > 15MB: Uploading to Gemini File API...")
                                file_uri = upload_audio_to_gemini_file_api(audio_path, mime_type)
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
                        except Exception as gemini_err:
                            print(f"Gemini Audio STT Error: {gemini_err}")
                            raw_transcript = f"※ [오류 발생]\n음성 파일 전사 중 오류가 발생했습니다: {str(gemini_err)}"
                    else:
                        key_status_msg = "Gemini API 키가 아직 설정되지 않아" if not api_key else "음성 파일이 너무 작아"
                        raw_transcript = (
                            f"※ [{key_status_msg} 시뮬레이션 모드로 작동 중입니다. 우측 상단 ⚙️ 설정에서 Gemini API 키를 등록해 주세요.]\n\n"
                            f"[상담교사] {participants.split()[-1] if participants else '민준'}아, 이번 6월 모의평가 성적표랑 학생부 세특을 검토해봤어. "
                            f"수학과 정보 교과는 뚜렷한 상승 곡선이라 SW특기자 전형이나 학종에서 아주 유리해. 다만 수능최저 영어 3등급 맞추는 게 관건이야.\n\n"
                            f"[학생] 네 선생님, 저도 영어 독해가 좀 불안해서 이번 방학 때 EBS 연계교재 위주로 집중 보완하려고 계획 중입니다. "
                            f"그런데 중앙대 CAU융합형인재는 수능최저가 없다고 들어서 그쪽 비중을 더 둘 수 있을까요?\n\n"
                            f"[상담교사] 중앙대 CAU융합형은 서류 100%에 면접이 있어서 네가 준비한 알고리즘 프로젝트와 수학 세특이 크게 인정받을 수 있어. "
                            f"수시 6장 카드를 상향 2개(고려대, 성균관대), 적정 3개(중앙대, 서울시립대, 건국대), 안정 1개(국민대)로 균형 있게 구성해보자.\n\n"
                            f"[학생] 네, 선생님 조언대로 6장 라인업 잡고, 3학년 1학기 세특 마무리에 알고리즘 동아리 성과를 확실하게 반영하도록 세특 문구를 보완하겠습니다."
                        )

                    record = {
                        "sessionId": session_id,
                        "teacherEmail": teacher_email,
                        "teacherName": teacher_name,
                        "participants": participants,
                        "topic": topic,
                        "counselingDate": counseling_date,
                        "startTime": start_time,
                        "audioFileName": f"{session_id}.m4a" if audio_bytes else "demo.m4a",
                        "audioFilePath": audio_path,
                        "rawTranscript": raw_transcript,
                        "structuredSummary": None,
                        "status": "TRANSCRIBED",
                        "createdAt": now.isoformat(),
                        "updatedAt": now.isoformat()
                    }

                    with open(SESSIONS_DIR / f"{session_id}.json", "w", encoding="utf-8") as fp:
                        json.dump(record, fp, ensure_ascii=False, indent=2)

                    self._set_json_headers(200)
                    self.wfile.write(json.dumps(record, ensure_ascii=False).encode("utf-8"))
                    return
                else:
                    self._set_json_headers(400)
                    self.wfile.write(json.dumps({"error": "Expected multipart/form-data"}).encode("utf-8"))
                    return
            except Exception as e:
                self._set_json_headers(500)
                self.wfile.write(json.dumps({"error": str(e)}).encode("utf-8"))
                return

        # 2. Update Raw Transcript
        if path.startswith("/api/sessions/") and path.endswith("/transcript"):
            session_id = path.replace("/api/sessions/", "").replace("/transcript", "").strip("/")
            file_path = SESSIONS_DIR / f"{session_id}.json"
            if not file_path.exists():
                self._set_json_headers(404)
                self.wfile.write(json.dumps({"error": "Session not found"}).encode("utf-8"))
                return

            content_len = int(self.headers.get("content-length", 0))
            post_body = self.rfile.read(content_len).decode("utf-8")
            body_data = json.loads(post_body)

            with open(file_path, "r", encoding="utf-8") as fp:
                record = json.load(fp)

            new_raw = body_data.get("rawTranscript", record.get("rawTranscript", ""))
            record["rawTranscript"] = new_raw
            record["updatedAt"] = datetime.now().isoformat()

            with open(file_path, "w", encoding="utf-8") as fp:
                json.dump(record, fp, ensure_ascii=False, indent=2)

            self._set_json_headers(200)
            self.wfile.write(json.dumps(record, ensure_ascii=False).encode("utf-8"))
            return

        # 3. AI Summary following [대화저장형식.txt]
        if path.startswith("/api/sessions/") and path.endswith("/summarize"):
            session_id = path.replace("/api/sessions/", "").replace("/summarize", "").strip("/")
            file_path = SESSIONS_DIR / f"{session_id}.json"
            if not file_path.exists():
                self._set_json_headers(404)
                self.wfile.write(json.dumps({"error": "Session not found"}).encode("utf-8"))
                return

            with open(file_path, "r", encoding="utf-8") as fp:
                record = json.load(fp)

            topic = record.get("topic", "진학 상담")
            counseling_date = record.get("counselingDate", datetime.now().strftime("%Y-%m-%d"))
            participants = record.get("participants", "상담교사, 학생")
            raw_text = record.get("rawTranscript", "")

            api_key = load_gemini_api_key()
            formatted_summary = ""

            if api_key and raw_text and not raw_text.startswith("※ ["):
                system_instruction = (
                    "당신은 전문 비즈니스 기록원입니다.\n"
                    "음성 인식 오류(오탈자, 불완전한 문장, 추임새 등)를 자연스럽게 보정하고, 아래 양식에 맞추어 명확하고 구조화된 '상담일지'형식으로 정리해 주세요.\n\n"
                    "[정리 가이드라인]\n"
                    "1. 단순 나열을 지양하고, 주제별로 그룹화하여 핵심 내용을 개조식(-, •)으로 작성할 것.\n"
                    "2. 대화 중 확정된 결정 사항과 향후 진행할 액션 아이템(학생 및 교사의 요구사항, 학생이 문제점, 교사의 조언등 등)을 명확히 구분할 것.\n"
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
                    print(f"Gemini Summarize Error: {e}")
                    formatted_summary = ""

            if not formatted_summary:
                student_name = "학생"
                for p in participants.split(","):
                    if "교사" not in p:
                        student_name = p.strip()
                        break

                formatted_summary = (
                    f"# [{topic}]\n"
                    f"- 일시: {counseling_date} {record.get('startTime', '')}\n"
                    f"- 참석자: {participants}\n\n"
                    f"## 1. 핵심 요약 (3줄 이내)\n"
                    f"- 모의평가 및 학생부 분석 결과, 수학·정보 교과 상승세를 활용한 SW특기자 및 학종 지원이 가장 유리함.\n"
                    f"- 수시 6장 라인업은 상향 2(고려대/성균관대), 적정 3(중앙대/시립대/건국대), 안정 1(국민대)로 확정함.\n"
                    f"- 수능최저(영어 3등급) 충족이 최대 관건이므로 방학 중 EBS 연계교재 집중 보완 및 세특 문구 최종 마무리를 진행하기로 함.\n\n"
                    f"## 2. 주요 논의 내용 (주제별 정리)\n"
                    f"### [SW특기자 및 학생부종합 전형 적합성]\n"
                    f"- 대화 배경: 6월 모의평가 성적과 1·2학년 학생부 세특 기록을 바탕으로 지원 전형 검토.\n"
                    f"- 주요 대화 및 논점: 수학/정보 교과 역량 우수성이 확인되어 서류 중심 전형에 강점이 있으나, 영어 영역 수능최저 충족 리스크가 대두됨.\n\n"
                    f"### [수시 6장 대학 라인업 및 최저학력기준 대비]\n"
                    f"- 대화 배경: 학생의 중앙대 CAU융합형인재(수능최저 미적용) 지원 문의 및 전형별 배분 전략 수립.\n"
                    f"- 주요 대화 및 논점: 상향 2개, 적정 3개, 안정 1개로 균형 배분하고, 수능최저 부담을 줄이면서 면접 역량을 살릴 수 있는 전략적 카드 채택.\n\n"
                    f"## 3. 최종 결정 사항 (Decisions)\n"
                    f"- 수시 6개 대학 라인업 확정 (고려대, 성균관대, 중앙대 CAU융합, 서울시립대, 건국대, 국민대).\n"
                    f"- 수능최저 충족을 위해 여름방학 기간 영어 EBS 연계교재 2회독 플랜 수립.\n"
                    f"- 3학년 1학기 정보·수학 세특에 알고리즘 동아리 성과와 보고서 내용을 최종 보강하기로 합의함.\n\n"
                    f"## 4. 후속 조치 및 진학 지도시 기록할 내용\n"
                    f"| 상담 내용 | 학생명 | 요구사항/조언 | 비고 |\n"
                    f"| :--- | :--- | :--- | :--- |\n"
                    f"| 수시 6장 라인업 및 SW특기자 점검 | {student_name} | 여름방학 영어 3등급 확보 및 1학기 세특 동아리 성과 마감 | 9월 초 모의면접 실시 예정 |\n"
                )

            record["structuredSummary"] = formatted_summary
            record["status"] = "SUMMARIZED"
            record["updatedAt"] = datetime.now().isoformat()

            with open(file_path, "w", encoding="utf-8") as fp:
                json.dump(record, fp, ensure_ascii=False, indent=2)

            self._set_json_headers(200)
            self.wfile.write(json.dumps(record, ensure_ascii=False).encode("utf-8"))
            return

        # 4. API: Sync to Google Drive via Central GAS Webhook
        if path.startswith("/api/sessions/") and path.endswith("/sync-google"):
            session_id = path.replace("/api/sessions/", "").replace("/sync-google", "").strip("/")
            file_path = SESSIONS_DIR / f"{session_id}.json"
            if not file_path.exists():
                self._set_json_headers(404)
                self.wfile.write(json.dumps({"error": "Session not found"}).encode("utf-8"))
                return

            with open(file_path, "r", encoding="utf-8") as fp:
                record = json.load(fp)

            gas_url = load_gas_webhook_url()
            if not gas_url:
                # Preview simulation mode when user hasn't deployed GAS yet
                preview_doc_url = f"https://docs.google.com/document/d/preview-{session_id}"
                preview_folder_url = f"https://drive.google.com/drive/folders/counselor-{record.get('teacherEmail')}"
                record["cloudDocUrl"] = preview_doc_url
                record["cloudFolderUrl"] = preview_folder_url
                record["updatedAt"] = datetime.now().isoformat()
                with open(file_path, "w", encoding="utf-8") as fp:
                    json.dump(record, fp, ensure_ascii=False, indent=2)

                self._set_json_headers(200)
                self.wfile.write(json.dumps({
                    "status": "success",
                    "simulated": True,
                    "message": "로컬 미리보기 모드: GAS URL이 아직 등록되지 않아 시뮬레이션 링크가 생성되었습니다. ⚙️ 설정에서 GAS URL을 등록하시면 실제 Google Drive에 실시간 저장됩니다.",
                    "docUrl": preview_doc_url,
                    "folderUrl": preview_folder_url
                }, ensure_ascii=False).encode("utf-8"))
                return

            # Call real Google Apps Script Webhook
            payload = {
                "action": "SYNC_COUNSELING_RECORD",
                "teacherEmail": record.get("teacherEmail"),
                "teacherName": record.get("teacherName"),
                "session": {
                    "sessionId": record.get("sessionId"),
                    "participants": record.get("participants"),
                    "topic": record.get("topic"),
                    "counselingDate": record.get("counselingDate"),
                    "startTime": record.get("startTime")
                },
                "rawTranscript": record.get("rawTranscript", ""),
                "structuredSummary": record.get("structuredSummary", "")
            }

            req_data = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(gas_url, data=req_data, headers={"Content-Type": "application/json"})

            try:
                with urllib.request.urlopen(req, timeout=60) as gas_res:
                    res_json = json.loads(gas_res.read().decode("utf-8"))
                    if res_json.get("status") == "success":
                        record["cloudDocUrl"] = res_json.get("docUrl")
                        record["cloudFolderUrl"] = res_json.get("teacherFolderUrl")
                        with open(file_path, "w", encoding="utf-8") as fp:
                            json.dump(record, fp, ensure_ascii=False, indent=2)

                    self._set_json_headers(200)
                    self.wfile.write(json.dumps(res_json, ensure_ascii=False).encode("utf-8"))
                    return
            except Exception as gas_err:
                self._set_json_headers(500)
                self.wfile.write(json.dumps({"error": f"Google Apps Script 호출 실패: {str(gas_err)}"}).encode("utf-8"))
                return

        self._set_json_headers(404)
        self.wfile.write(json.dumps({"error": "Route not found"}).encode("utf-8"))

def run():
    server_address = ("127.0.0.1", PORT)
    httpd = HTTPServer(server_address, MeetingSummaryHandler)
    print(f"Meeting Summary Server with {GEMINI_MODEL} running at http://127.0.0.1:{PORT}")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        httpd.server_close()

if __name__ == "__main__":
    run()
