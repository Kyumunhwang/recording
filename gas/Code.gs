/**
 * Central Google Apps Script (GAS) Webhook for Meeting Summary App
 * 
 * Deployment Instructions (중앙 배포 1회):
 * 1. Google Drive -> New -> More -> Google Apps Script 생성
 * 2. Code.gs 파일에 본 코드 전체 붙여넣기
 * 3. 상단 [배포] -> [새 배포] 클릭
 *    - 유형 선택: 웹 앱 (Web app)
 *    - 설명: 진학상담 자동 연동 Webhook
 *    - 다음 사용자 권한으로 실행: '나(내 계정)'
 *    - 액세스 권한이 있는 사용자: '모든 사용자(Anyone)'
 * 4. 배포 완료 후 생성된 '웹 앱 URL'을 복사하여 Meeting Summary 앱의 설정에 1회 등록!
 */

function doPost(e) {
  try {
    if (!e || !e.postData || !e.postData.contents) {
      return ContentService.createTextOutput(JSON.stringify({
        status: "error",
        message: "요청 본문이 비어있습니다."
      })).setMimeType(ContentService.MimeType.JSON);
    }

    var payload = JSON.parse(e.postData.contents);
    var teacherEmail = payload.teacherEmail || "counselor@school.kr";
    var teacherName = payload.teacherName || "상담교사";
    var session = payload.session || {};
    var rawTranscript = payload.rawTranscript || "";
    var structuredSummary = payload.structuredSummary || "";

    var topic = session.topic || "진학상담";
    var dateStr = session.counselingDate || Utilities.formatDate(new Date(), "Asia/Seoul", "yyyy-MM-dd");
    var participants = session.participants || teacherName;

    // 1. Root 폴더 생성/가져오기
    var rootFolderName = "진학상담_AI_기록소";
    var rootFolder = getOrCreateFolder(DriveApp.getRootFolder(), rootFolderName);

    // 2. 교사별 전용 서브폴더 생성/가져오기 (이메일 기반 라우팅)
    var teacherFolderCleanName = teacherName + " (" + teacherEmail + ")";
    var teacherFolder = getOrCreateFolder(rootFolder, teacherFolderCleanName);

    // 3. 교사 본인의 구글 계정으로 폴더 편집 권한 자동 부여
    try {
      if (teacherEmail && teacherEmail.indexOf("@") !== -1) {
        teacherFolder.addEditor(teacherEmail);
      }
    } catch (permErr) {
      Logger.log("권한 부여 알림: " + permErr.message);
    }

    // 4. Google Docs 상담일지 문서 생성
    var docTitle = "[" + dateStr + "] " + topic + " - 진학상담일지 (" + participants + ")";
    var doc = DocumentApp.create(docTitle);
    var body = doc.getBody();

    // 헤더 타이틀
    var titleParagraph = body.appendParagraph("🎓 진학상담 AI 리포트 및 상담일지");
    titleParagraph.setHeading(DocumentApp.ParagraphHeading.HEADING1);
    titleParagraph.setForegroundColor("#00236F");

    // 기본 메타데이터 표
    var metaTable = [
      ["상담 일시", dateStr + " " + (session.startTime || "")],
      ["상담 교사", teacherName + " (" + teacherEmail + ")"],
      ["참석자", participants],
      ["상담 주제", topic],
      ["세션 번호", session.sessionId || "N/A"]
    ];
    var table = body.appendTable(metaTable);
    table.setBorderColor("#C5C5D3");
    body.appendParagraph("");

    // AI 구조화 상담일지 내용 삽입 (대화저장형식.txt 결과물)
    var summaryHeading = body.appendParagraph("📌 AI 정리 상담일지 (구조화 리포트)");
    summaryHeading.setHeading(DocumentApp.ParagraphHeading.HEADING2);
    summaryHeading.setForegroundColor("#006A61");

    if (structuredSummary) {
      body.appendParagraph(structuredSummary);
    } else {
      body.appendParagraph("정리된 요약 내용이 없습니다.");
    }

    body.appendParagraph("");

    // 최종 수정 원문 대화 전문 삽입
    var transcriptHeading = body.appendParagraph("🎙️ 최종 대화 원문 전문");
    transcriptHeading.setHeading(DocumentApp.ParagraphHeading.HEADING2);
    transcriptHeading.setForegroundColor("#1E3A8A");

    if (rawTranscript) {
      body.appendParagraph(rawTranscript);
    } else {
      body.appendParagraph("저장된 원문이 없습니다.");
    }

    doc.saveAndClose();

    // 5. 생성된 문서를 교사 전용 폴더로 이동
    var docFile = DriveApp.getFileById(doc.getId());
    docFile.moveTo(teacherFolder);

    return ContentService.createTextOutput(JSON.stringify({
      status: "success",
      message: "교사 전용 Google Drive 폴더에 상담일지가 안전하게 저장되었습니다.",
      docId: doc.getId(),
      docUrl: doc.getUrl(),
      teacherFolderUrl: teacherFolder.getUrl()
    })).setMimeType(ContentService.MimeType.JSON);

  } catch (err) {
    Logger.log("doPost Error: " + err.toString());
    return ContentService.createTextOutput(JSON.stringify({
      status: "error",
      message: err.toString()
    })).setMimeType(ContentService.MimeType.JSON);
  }
}

function getOrCreateFolder(parentFolder, folderName) {
  var folders = parentFolder.getFoldersByName(folderName);
  if (folders.hasNext()) {
    return folders.next();
  }
  return parentFolder.createFolder(folderName);
}
