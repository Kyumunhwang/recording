// Meeting Summary App - Vercel Pure Edge Client Controller
// Direct browser-to-Gemini & browser-to-GAS architecture (100% Serverless & 0% 500 error)
(function() {
  const GEMINI_MODEL = "gemini-3.8-flash";
  let currentSessionId = null;
  let currentRawTranscript = "";
  let currentSummaryMarkdown = "";

  // Local Credentials & Teacher Profile
  let credentials = {
    teacherName: localStorage.getItem('teacher_name') || '나경식 교사 (Mr. David Nah)',
    teacherEmail: localStorage.getItem('teacher_email') || 'counselor@school.kr',
    geminiApiKey: localStorage.getItem('gemini_api_key') || '',
    gasWebhookUrl: localStorage.getItem('gas_webhook_url') || ''
  };

  // DOM Elements
  const headerTeacherName = document.getElementById('header-teacher-name');
  const inputParticipants = document.getElementById('input-participants');
  const inputTopic = document.getElementById('input-topic');
  const fileInput = document.getElementById('audio-file-input');
  const selectedFileName = document.getElementById('selected-file-name');

  const btnGenerateRaw = document.getElementById('btn-generate-raw');
  const btnSummarizeAi = document.getElementById('btn-summarize-ai');

  const rawSection = document.getElementById('raw-transcript-section');
  const rawBox = document.getElementById('raw-transcript-box');
  const btnOpenEditModal = document.getElementById('btn-open-edit-modal');

  const summarySection = document.getElementById('ai-summary-section');
  const summaryContent = document.getElementById('ai-summary-content');
  const btnCopySummary = document.getElementById('btn-copy-summary');

  // Edit Modal
  const editModal = document.getElementById('edit-transcript-modal');
  const modalTextarea = document.getElementById('modal-transcript-textarea');
  const btnCloseEditModal = document.getElementById('btn-close-edit-modal');
  const btnCancelModal = document.getElementById('btn-cancel-modal');
  const btnSaveModal = document.getElementById('btn-save-modal');

  // Settings Modal
  const settingsModal = document.getElementById('settings-modal');
  const btnOpenSettingsModal = document.getElementById('btn-settings-modal');
  const btnCloseSettingsModal = document.getElementById('btn-close-settings-modal');
  const btnSaveSettings = document.getElementById('btn-save-settings');
  const inputTeacherName = document.getElementById('setting-teacher-name');
  const inputTeacherEmail = document.getElementById('setting-teacher-email');
  const inputGeminiKey = document.getElementById('setting-gemini-key');
  const inputGasUrl = document.getElementById('setting-gas-url');

  // Init Header
  headerTeacherName.textContent = credentials.teacherName;

  // File Select Event
  fileInput.addEventListener('change', (e) => {
    if (e.target.files.length > 0) {
      const file = e.target.files[0];
      selectedFileName.textContent = `선택된 파일: ${file.name} (${(file.size / (1024 * 1024)).toFixed(2)} MB)`;
      selectedFileName.classList.add('text-secondary');
    }
  });

  // Helper: Convert File to Base64
  function fileToBase64(file) {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => {
        const b64 = reader.result.split(',')[1];
        resolve(b64);
      };
      reader.onerror = error => reject(error);
      reader.readAsDataURL(file);
    });
  }

  // Direct Call to Gemini API from Browser
  async function callGemini(contentsParts, systemInstruction = null) {
    if (!credentials.geminiApiKey) {
      throw new Error('Gemini API Key가 설정되지 않았습니다. 우측 상단 ⚙️ 설정에서 API Key를 먼저 등록해 주세요.');
    }

    const url = `https://generativelanguage.googleapis.com/v1beta/models/${GEMINI_MODEL}:generateContent?key=${credentials.geminiApiKey}`;
    const payload = {
      contents: [{ parts: contentsParts }],
      generationConfig: { temperature: 0.2 }
    };

    if (systemInstruction) {
      payload.systemInstruction = {
        parts: [{ text: systemInstruction }]
      };
    }

    const response = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });

    if (!response.ok) {
      const err = await response.json().catch(() => ({}));
      throw new Error(err.error?.message || `Gemini API 호출 오류 (${response.status})`);
    }

    const resJson = await response.json();
    const candidate = resJson.candidates?.[0];
    const textPart = candidate?.content?.parts?.[0]?.text;
    return textPart || "응답 텍스트를 파싱하지 못했습니다.";
  }

  // Action 1: Generate Raw STT Transcript
  btnGenerateRaw.addEventListener('click', async () => {
    const participants = inputParticipants.value.trim();
    const topic = inputTopic.value.trim();

    if (!participants) {
      alert('상담 대상자(참석자)를 입력해 주세요.');
      inputParticipants.focus();
      return;
    }

    if (!credentials.geminiApiKey) {
      alert('우측 상단 ⚙️ 설정에서 학교 Gemini API Key를 1회 등록해 주세요.');
      settingsModal.classList.remove('hidden');
      return;
    }

    btnGenerateRaw.disabled = true;
    btnGenerateRaw.classList.add('opacity-75');
    const originalText = btnGenerateRaw.innerHTML;
    btnGenerateRaw.innerHTML = `
      <span class="material-symbols-outlined animate-spin text-[20px]">sync</span>
      <span>Gemini 3.8 Flash가 음성을 듣고 화자 분리 전사 중...</span>
    `;

    try {
      const now = new Date();
      currentSessionId = `CS-${now.getFullYear()}${String(now.getMonth()+1).padStart(2,'0')}${String(now.getDate()).padStart(2,'0')}-${String(now.getHours()).padStart(2,'0')}${String(now.getMinutes()).padStart(2,'0')}`;

      const promptText = `당신은 고등학교 진학 상담 전문 기록원입니다.\n첨부된 음성 파일을 듣고, 상담 교사와 학생(또는 학부모)의 대화 내용을 한국어로 충실하게 전사(STT)해 주세요.\n\n[상담 정보]\n- 참석자: ${participants}\n- 상담 주제: ${topic}\n\n[작성 규칙]\n1. 목소리와 어조를 분석하여 화자를 분리해 [상담교사], [학생] 등의 형식으로 말머리를 붙이세요.\n2. 불필요한 추임새는 다듬되, 대화의 핵심 내용과 맥락은 생략하지 마세요.\n3. 입시 용어(세특, 모평, 학종, 전형명, 수능최저 등)를 문맥에 맞게 정확하게 표기해 주세요.\n4. 오직 전사된 대화 원문 내용만 출력하세요 (인사말이나 부가 설명 제외).`;

      let contentsParts = [];
      if (fileInput.files.length > 0) {
        const file = fileInput.files[0];
        const b64Data = await fileToBase64(file);
        contentsParts = [
          {
            inlineData: {
              mimeType: file.type || "audio/mp4",
              data: b64Data
            }
          },
          { text: promptText }
        ];
      } else {
        // Fallback realistic demo text when user didn't pick audio
        contentsParts = [{ text: `[데모 모드]\n상담교사와 학생의 입시 상담 대화 원문 예시를 [상담교사], [학생] 화자 분리 형태로 생성해 주세요.` }];
      }

      currentRawTranscript = await callGemini(contentsParts);
      rawBox.textContent = currentRawTranscript;
      rawSection.classList.remove('hidden');

      // Enable AI Summarize Button
      btnSummarizeAi.disabled = false;
      btnSummarizeAi.classList.remove('opacity-50', 'cursor-not-allowed');
      btnSummarizeAi.classList.add('hover:bg-primary-container', 'hover:text-white', 'cursor-pointer');
      rawSection.scrollIntoView({ behavior: 'smooth' });

    } catch (err) {
      alert(`오류 발생: ${err.message}`);
    } finally {
      btnGenerateRaw.disabled = false;
      btnGenerateRaw.classList.remove('opacity-75');
      btnGenerateRaw.innerHTML = originalText;
    }
  });

  // Modal Control
  btnOpenEditModal.addEventListener('click', () => {
    modalTextarea.value = currentRawTranscript;
    editModal.classList.remove('hidden');
  });

  function closeEditModal() {
    editModal.classList.add('hidden');
  }

  btnCloseEditModal.addEventListener('click', closeEditModal);
  btnCancelModal.addEventListener('click', closeEditModal);

  btnSaveModal.addEventListener('click', () => {
    const updatedText = modalTextarea.value.trim();
    if (!updatedText) {
      alert('원문 내용을 입력해 주세요.');
      return;
    }
    currentRawTranscript = updatedText;
    rawBox.textContent = currentRawTranscript;
    closeEditModal();
    alert('원문 수정 사항이 반영되었습니다.\n이제 아래 [2. AI 내용 분석 및 상담일지 요약] 버튼을 누르시면 수정된 원문으로 정리됩니다.');
  });

  // Action 2: Generate AI Summary strictly to [대화저장형식.txt]
  btnSummarizeAi.addEventListener('click', async () => {
    if (!currentRawTranscript) {
      alert('먼저 1단계 원문 추출을 진행해 주세요.');
      return;
    }

    btnSummarizeAi.disabled = true;
    btnSummarizeAi.classList.add('opacity-75');
    const originalText = btnSummarizeAi.innerHTML;
    btnSummarizeAi.innerHTML = `
      <span class="material-symbols-outlined animate-spin text-[20px]">auto_awesome</span>
      <span>대화저장형식 양식에 맞춰 AI 상담일지 분석 및 정리 중...</span>
    `;

    try {
      const now = new Date();
      const dateStr = `${now.getFullYear()}-${String(now.getMonth()+1).padStart(2,'0')}-${String(now.getDate()).padStart(2,'0')}`;
      const timeStr = `${String(now.getHours()).padStart(2,'0')}:${String(now.getMinutes()).padStart(2,'0')}`;
      const topic = inputTopic.value.trim() || '진학 상담';
      const participants = inputParticipants.value.trim() || credentials.teacherName;

      const systemInstruction = `당신은 전문 비즈니스 기록원입니다.\n음성 인식 오류(오탈자, 불완전한 문장, 추임새 등)를 자연스럽게 보정하고, 아래 양식에 맞추어 명확하고 구조화된 '상담일지'형식으로 정리해 주세요.\n\n[정리 가이드라인]\n1. 단순 나열을 지양하고, 주제별로 그룹화하여 핵심 내용을 개조식(-, •)으로 작성할 것.\n2. 대화 중 확정된 결정 사항과 향후 진행할 액션 아이템(학생 및 교사의 요구사항, 학생이 문제점, 교사의 조언등 등)을 명확히 구분할 것.\n3. 구어체는 명확한 문어체(~함, ~하기로 함)로 변환할 것.`;

      const prompt = `다음 상담 정보와 수정된 최종 대화 원문을 바탕으로 지정된 마크다운 양식 그대로 상담일지를 작성해 주세요.\n\n[상담 정보]\n- 안건 주제: ${topic}\n- 일시: ${dateStr} ${timeStr}\n- 참석자: ${participants}\n\n[대화 원문]\n${currentRawTranscript}\n\n[반드시 준수할 출력 양식]\n# [${topic}]\n- 일시: ${dateStr} ${timeStr}\n- 참석자: ${participants}\n\n## 1. 핵심 요약 (3줄 이내)\n- [핵심 요약 1]\n- [핵심 요약 2]\n- [핵심 요약 3]\n\n## 2. 주요 논의 내용 (주제별 정리)\n### [주제 A]\n- 대화 배경:\n- 주요 대화 및 논점:\n\n### [주제 B]\n- 대화 배경:\n- 주요 대화 및 논점:\n\n## 3. 최종 결정 사항 (Decisions)\n- \n\n## 4. 후속 조치 및 진학 지도시 기록할 내용\n| 상담 내용 | 학생명 | 요구사항/조언 | 비고 |\n| :--- | :--- | :--- | :--- |\n| ... | ... | ... | ... |\n`;

      currentSummaryMarkdown = await callGemini([{ text: prompt }], systemInstruction);
      summaryContent.innerHTML = marked.parse(currentSummaryMarkdown);
      summarySection.classList.remove('hidden');
      summarySection.scrollIntoView({ behavior: 'smooth' });

    } catch (err) {
      alert(`요약 오류: ${err.message}`);
    } finally {
      btnSummarizeAi.disabled = false;
      btnSummarizeAi.classList.remove('opacity-75');
      btnSummarizeAi.innerHTML = originalText;
    }
  });

  // Action 3: Sync to Google Drive (GAS Webhook Direct)
  const btnSyncGoogle = document.getElementById('btn-sync-google');
  const googleSyncResultBox = document.getElementById('google-sync-result-box');
  const linkOpenGdoc = document.getElementById('link-open-gdoc');
  const linkOpenFolder = document.getElementById('link-open-folder');

  btnSyncGoogle.addEventListener('click', async () => {
    if (!currentSummaryMarkdown) {
      alert('저장할 상담일지 요약 내용이 없습니다.');
      return;
    }

    if (!credentials.gasWebhookUrl) {
      // Local preview simulation mode
      linkOpenGdoc.href = `https://docs.google.com/document/d/preview-${currentSessionId}`;
      linkOpenFolder.href = `https://drive.google.com`;
      googleSyncResultBox.classList.remove('hidden');
      googleSyncResultBox.scrollIntoView({ behavior: 'smooth' });
      alert('로컬 시뮬레이션 모드: 우측 상단 ⚙️ 설정에서 구글 드라이브 GAS Webhook URL을 등록하시면 실제 구글 드라이브 폴더로 자동 저장됩니다.');
      return;
    }

    btnSyncGoogle.disabled = true;
    btnSyncGoogle.classList.add('opacity-75');
    const originalText = btnSyncGoogle.innerHTML;
    btnSyncGoogle.innerHTML = `
      <span class="material-symbols-outlined animate-spin text-[20px]">sync</span>
      <span>교사 Google Drive로 상담일지 생성 및 전송 중...</span>
    `;

    try {
      const now = new Date();
      const payload = {
        action: "SYNC_COUNSELING_RECORD",
        teacherEmail: credentials.teacherEmail,
        teacherName: credentials.teacherName,
        session: {
          sessionId: currentSessionId,
          participants: inputParticipants.value.trim(),
          topic: inputTopic.value.trim(),
          counselingDate: `${now.getFullYear()}-${String(now.getMonth()+1).padStart(2,'0')}-${String(now.getDate()).padStart(2,'0')}`,
          startTime: `${String(now.getHours()).padStart(2,'0')}:${String(now.getMinutes()).padStart(2,'0')}`
        },
        rawTranscript: currentRawTranscript,
        structuredSummary: currentSummaryMarkdown
      };

      const response = await fetch(credentials.gasWebhookUrl, {
        method: 'POST',
        headers: { 'Content-Type': 'text/plain;charset=utf-8' },
        body: JSON.stringify(payload)
      });

      const resJson = await response.json();
      linkOpenGdoc.href = resJson.docUrl || '#';
      linkOpenFolder.href = resJson.teacherFolderUrl || '#';
      googleSyncResultBox.classList.remove('hidden');
      googleSyncResultBox.scrollIntoView({ behavior: 'smooth' });
      alert(resJson.message || '교사 전용 Google Drive에 상담일지가 안전하게 저장되었습니다!');

    } catch (err) {
      alert(`Google Drive 전송 오류: ${err.message}`);
    } finally {
      btnSyncGoogle.disabled = false;
      btnSyncGoogle.classList.remove('opacity-75');
      btnSyncGoogle.innerHTML = originalText;
    }
  });

  // Copy Summary
  btnCopySummary.addEventListener('click', () => {
    if (!currentSummaryMarkdown) return;
    navigator.clipboard.writeText(currentSummaryMarkdown).then(() => {
      alert('상담일지 양식이 클립보드에 복사되었습니다.');
    });
  });

  // Teacher & API Key Settings Modal
  btnOpenSettingsModal.addEventListener('click', () => {
    inputTeacherName.value = credentials.teacherName;
    inputTeacherEmail.value = credentials.teacherEmail;
    inputGeminiKey.value = credentials.geminiApiKey;
    inputGasUrl.value = credentials.gasWebhookUrl;
    settingsModal.classList.remove('hidden');
  });

  btnCloseSettingsModal.addEventListener('click', () => {
    settingsModal.classList.add('hidden');
  });

  btnSaveSettings.addEventListener('click', () => {
    credentials.teacherName = inputTeacherName.value.trim() || '상담교사';
    credentials.teacherEmail = inputTeacherEmail.value.trim() || 'counselor@school.kr';
    credentials.geminiApiKey = inputGeminiKey.value.trim();
    credentials.gasWebhookUrl = inputGasUrl.value.trim();

    localStorage.setItem('teacher_name', credentials.teacherName);
    localStorage.setItem('teacher_email', credentials.teacherEmail);
    if (credentials.geminiApiKey) localStorage.setItem('gemini_api_key', credentials.geminiApiKey);
    if (credentials.gasWebhookUrl) localStorage.setItem('gas_webhook_url', credentials.gasWebhookUrl);

    headerTeacherName.textContent = credentials.teacherName;
    settingsModal.classList.add('hidden');
    alert('설정이 안전하게 브라우저에 저장되었습니다.\n이제 Vercel 웹 사이트에서 실시간으로 음성 인식과 요약을 사용하실 수 있습니다.');
  });

  // Auto load key from environment if present in query param
  const urlParams = new URLSearchParams(window.location.search);
  if (urlParams.get('key')) {
    credentials.geminiApiKey = urlParams.get('key');
    localStorage.setItem('gemini_api_key', credentials.geminiApiKey);
  }

})();
