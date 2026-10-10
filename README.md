# Meeting Summary App (진학상담 음성 요약 시스템)

학교 교사가 학생과의 1:1 진학 상담 시 음성을 녹음하고, 즉시 1차 저장하여 상담을 지체 없이 이어간 뒤 여유 시간에 AI 요약 및 Google Drive로 동기화하는 모바일 웹/앱 시스템입니다.

## 1. 아키텍처 핵심 특징
- **1차 즉시 저장 (Decoupled Pipeline):** 연속 2~3회 상담 시 대기 시간(STT/LLM 대기 1~2분) 없이 5초 내로 오디오 원본 및 메타데이터를 로컬 저장하고 즉시 다음 상담 진행.
- **자동 캡처 & 수동 입력 결합:**
  - 녹음 시작 시 당일 일시(`counselingDate`, `startTime`) 자동 저장.
  - 상담 종료 시 소요 시간(`durationSeconds`, `durationFormatted`) 자동 계산.
  - 상담 대상자(`studentName`) 및 핵심 주제(`topic`)는 교사가 직관적으로 텍스트 직접 입력.
- **중앙 관리형 GAS Webhook (A안 채택):**
  - 개별 교사가 복잡한 GCP/OAuth/GAS 배포를 할 필요 없이, 교사 이메일(`teacherEmail`)만 입력하면 중앙 GAS에서 교사별 Google Drive 폴더로 자동 라우팅 및 Google Docs 생성.

## 2. 프로젝트 구조
- `server.py`: 단독 실행 가능한 경량 HTTP 서버 (포트 `3850`)
- `web/`: Stitch UI/UX 디자인 기반 반응형 프론트엔드
  - `index.html`: 실시간 녹음, 일시 자동 캡처, 학생/주제 입력, 1차 즉시 저장 화면
  - `stt_view.html`: 화자 분리(교사/학생) STT 전문 및 AI 진학 요약 리포트 화면
  - `app.js`: 녹음 타이머, 파형 애니메이션, 대기열(Queue) 관리 컨트롤러
- `gas/Code.gs`: 중앙 관리형 Google Apps Script Webhook 배포 코드
- `backend/`: 모듈화된 FastAPI / Pydantic / Service 아키텍처

## 3. 실행 방법
```powershell
# 서버 실행 (Port 3850)
python server.py
```
브라우저에서 `http://127.0.0.1:3850` 접속.
