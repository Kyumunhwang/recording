// Meeting Summary App - Upload & Summarize Controller
(function() {
  let currentSessionId = null;
  let currentRawTranscript = "";
  let currentSummaryMarkdown = "";

  // Teacher Profile
  let teacherProfile = {
    name: localStorage.getItem('teacher_name') || '나경식 교사 (Mr. David Nah)',
    email: localStorage.getItem('teacher_email') || 'counselor@school.kr'
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

  // Init Header Profile
  headerTeacherName.textContent = teacherProfile.name;

  // File Select Event
  fileInput.addEventListener('change', (e) => {
    if (e.target.files.length > 0) {
      const file = e.target.files[0];
      selectedFileName.textContent = `선택된 파일: ${file.name} (${(file.size / (1024 * 1024)).toFixed(2)} MB)`;
      selectedFileName.classList.add('text-secondary');
    }
  });

  // Action 1: Upload File & Generate Raw STT Transcript
  btnGenerateRaw.addEventListener('click', async () => {
    const participants = inputParticipants.value.trim();
    const topic = inputTopic.value.trim();

    if (!participants) {
      alert('상담 대상자(참석자)를 입력해 주세요.');
      inputParticipants.focus();
      return;
    }

    const formData = new FormData();
    formData.append('teacherName', teacherProfile.name);
    formData.append('teacherEmail', teacherProfile.email);
    formData.append('participants', participants);
    formData.append('topic', topic || '진학 상담');

    if (fileInput.files.length > 0) {
      formData.append('audioFile', fileInput.files[0]);
    } else {
      // Create a mock audio blob if user didn't pick a file, to allow rapid demo
      const mockBlob = new Blob(["DEMO_AUDIO_STREAM"], { type: "audio/m4a" });
      formData.append('audioFile', mockBlob, "recorded_counseling.m4a");
    }

    btnGenerateRaw.disabled = true;
    btnGenerateRaw.classList.add('opacity-75');
    const originalText = btnGenerateRaw.innerHTML;
    btnGenerateRaw.innerHTML = `
      <span class="material-symbols-outlined animate-spin text-[20px]">sync</span>
      <span>음성 인식 및 원문 전체 텍스트 추출 중...</span>
    `;

    try {
      const response = await fetch('/api/sessions/upload-transcribe', {
        method: 'POST',
        body: formData
      });

      if (!response.ok) throw new Error('원문 추출에 실패했습니다.');

      const data = await response.json();
      currentSessionId = data.sessionId;
      currentRawTranscript = data.rawTranscript;

      // Render Raw Transcript
      rawBox.textContent = currentRawTranscript;
      rawSection.classList.remove('hidden');

      // Enable AI Summarize Button
      btnSummarizeAi.disabled = false;
      btnSummarizeAi.classList.remove('opacity-50', 'cursor-not-allowed');
      btnSummarizeAi.classList.add('hover:bg-primary-container', 'hover:text-white', 'cursor-pointer');

      // Scroll to raw transcript
      rawSection.scrollIntoView({ behavior: 'smooth' });

    } catch (err) {
      alert(`오류 발생: ${err.message}`);
    } finally {
      btnGenerateRaw.disabled = false;
      btnGenerateRaw.classList.remove('opacity-75');
      btnGenerateRaw.innerHTML = originalText;
    }
  });

  // Modal Open for Editing Raw Transcript
  btnOpenEditModal.addEventListener('click', () => {
    modalTextarea.value = currentRawTranscript;
    editModal.classList.remove('hidden');
  });

  function closeEditModal() {
    editModal.classList.add('hidden');
  }

  btnCloseEditModal.addEventListener('click', closeEditModal);
  btnCancelModal.addEventListener('click', closeEditModal);

  // Save Modified Raw Transcript
  btnSaveModal.addEventListener('click', async () => {
    const updatedText = modalTextarea.value.trim();
    if (!updatedText) {
      alert('원문 내용을 입력해 주세요.');
      return;
    }

    if (!currentSessionId) {
      currentRawTranscript = updatedText;
      rawBox.textContent = currentRawTranscript;
      closeEditModal();
      return;
    }

    try {
      const response = await fetch(`/api/sessions/${currentSessionId}/transcript`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ rawTranscript: updatedText })
      });

      if (!response.ok) throw new Error('원문 수정 저장 실패');

      currentRawTranscript = updatedText;
      rawBox.textContent = currentRawTranscript;
      closeEditModal();
      alert('원문 수정 사항이 안전하게 반영되었습니다.\n이제 아래 [2. AI 내용 분석 및 상담일지 요약] 버튼을 누르시면 수정된 원문으로 정리됩니다.');
    } catch (err) {
      alert(err.message);
    }
  });

  // Action 2: Generate AI Summary according to [대화저장형식.txt]
  btnSummarizeAi.addEventListener('click', async () => {
    if (!currentSessionId) {
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
      const response = await fetch(`/api/sessions/${currentSessionId}/summarize`, {
        method: 'POST'
      });

      if (!response.ok) throw new Error('AI 분석 및 요약에 실패했습니다.');

      const data = await response.json();
      currentSummaryMarkdown = data.structuredSummary;

      // Render Markdown using Marked.js
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

  // Action 3: Sync to Google Drive
  const btnSyncGoogle = document.getElementById('btn-sync-google');
  const googleSyncResultBox = document.getElementById('google-sync-result-box');
  const linkOpenGdoc = document.getElementById('link-open-gdoc');
  const linkOpenFolder = document.getElementById('link-open-folder');

  btnSyncGoogle.addEventListener('click', async () => {
    if (!currentSessionId) {
      alert('저장할 상담 세션이 없습니다.');
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
      const response = await fetch(`/api/sessions/${currentSessionId}/sync-google`, {
        method: 'POST'
      });

      if (!response.ok) throw new Error('Google Drive 동기화에 실패했습니다.');

      const data = await response.json();
      
      linkOpenGdoc.href = data.docUrl || '#';
      linkOpenFolder.href = data.teacherFolderUrl || data.folderUrl || '#';
      googleSyncResultBox.classList.remove('hidden');
      googleSyncResultBox.scrollIntoView({ behavior: 'smooth' });

      alert(data.message || 'Google Drive 저장이 완료되었습니다!');

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
  btnOpenSettingsModal.addEventListener('click', async () => {
    inputTeacherName.value = teacherProfile.name;
    inputTeacherEmail.value = teacherProfile.email;
    const inputGeminiKey = document.getElementById('setting-gemini-key');
    const inputGasUrl = document.getElementById('setting-gas-url');
    try {
      const res = await fetch('/api/status');
      const data = await res.json();
      if (data.hasKey) {
        inputGeminiKey.placeholder = "API 키가 이미 서버에 등록되어 있습니다 (변경 시에만 입력)";
      }
      if (data.gasUrl) {
        inputGasUrl.value = data.gasUrl;
      }
    } catch(e) {}
    settingsModal.classList.remove('hidden');
  });

  btnCloseSettingsModal.addEventListener('click', () => {
    settingsModal.classList.add('hidden');
  });

  btnSaveSettings.addEventListener('click', async () => {
    teacherProfile.name = inputTeacherName.value.trim() || '상담교사';
    teacherProfile.email = inputTeacherEmail.value.trim() || 'counselor@school.kr';
    localStorage.setItem('teacher_name', teacherProfile.name);
    localStorage.setItem('teacher_email', teacherProfile.email);
    headerTeacherName.textContent = teacherProfile.name;

    const inputGeminiKey = document.getElementById('setting-gemini-key');
    const inputGasUrl = document.getElementById('setting-gas-url');
    const newKey = inputGeminiKey ? inputGeminiKey.value.trim() : "";
    const newGasUrl = inputGasUrl ? inputGasUrl.value.trim() : "";

    const payload = {};
    if (newKey) payload.geminiApiKey = newKey;
    if (newGasUrl) payload.gasWebhookUrl = newGasUrl;

    if (Object.keys(payload).length > 0) {
      try {
        await fetch('/api/settings/key', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload)
        });
        alert('설정이 서버에 안전하게 등록되었습니다.');
      } catch(e) {
        alert('설정 저장 실패: ' + e.message);
      }
    } else {
      alert('교사 정보가 저장되었습니다.');
    }

    settingsModal.classList.add('hidden');
  });

})();
