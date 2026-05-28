const icons = {
  alert: '<svg viewBox="0 0 24 24"><path d="M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0Z"/><path d="M12 9v4"/><path d="M12 17h.01"/></svg>',
  book: '<svg viewBox="0 0 24 24"><path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"/><path d="M4 4.5A2.5 2.5 0 0 1 6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5Z"/></svg>',
  check: '<svg viewBox="0 0 24 24"><path d="m20 6-11 11-5-5"/></svg>',
  clock: '<svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="10"/><path d="M12 6v6l4 2"/></svg>',
  cloud: '<svg viewBox="0 0 24 24"><path d="M17.5 19H7a5 5 0 1 1 .9-9.9A7 7 0 0 1 21 12.5 3.5 3.5 0 0 1 17.5 19Z"/></svg>',
  file: '<svg viewBox="0 0 24 24"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8Z"/><path d="M14 2v6h6"/></svg>',
  folder: '<svg viewBox="0 0 24 24"><path d="M3 7a2 2 0 0 1 2-2h5l2 2h7a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2Z"/></svg>',
  help: '<svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="10"/><path d="M9.1 9a3 3 0 1 1 5.6 1.5c-.6.9-1.7 1.3-2.2 2.1-.3.4-.5.8-.5 1.4"/><path d="M12 17h.01"/></svg>',
  layout: '<svg viewBox="0 0 24 24"><rect width="7" height="9" x="3" y="3" rx="1"/><rect width="7" height="5" x="14" y="3" rx="1"/><rect width="7" height="9" x="14" y="12" rx="1"/><rect width="7" height="5" x="3" y="16" rx="1"/></svg>',
  search: '<svg viewBox="0 0 24 24"><circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/></svg>',
  settings: '<svg viewBox="0 0 24 24"><path d="M12.2 2h-.4a2 2 0 0 0-2 1.7l-.1.7a2 2 0 0 1-2.9 1.2l-.6-.4a2 2 0 0 0-2.6.3l-.2.3a2 2 0 0 0-.3 2.6l.4.6a2 2 0 0 1-1.2 2.9l-.7.1A2 2 0 0 0 2 13.8v.4a2 2 0 0 0 1.7 2l.7.1a2 2 0 0 1 1.2 2.9l-.4.6a2 2 0 0 0 .3 2.6l.3.2a2 2 0 0 0 2.6.3l.6-.4a2 2 0 0 1 2.9 1.2l.1.7a2 2 0 0 0 2 1.7h.4a2 2 0 0 0 2-1.7l.1-.7a2 2 0 0 1 2.9-1.2l.6.4a2 2 0 0 0 2.6-.3l.2-.3a2 2 0 0 0 .3-2.6l-.4-.6a2 2 0 0 1 1.2-2.9l.7-.1a2 2 0 0 0 1.7-2v-.4a2 2 0 0 0-1.7-2l-.7-.1a2 2 0 0 1-1.2-2.9l.4-.6a2 2 0 0 0-.3-2.6l-.3-.2a2 2 0 0 0-2.6-.3l-.6.4a2 2 0 0 1-2.9-1.2l-.1-.7A2 2 0 0 0 12.2 2Z"/><circle cx="12" cy="12" r="3"/></svg>',
  sync: '<svg viewBox="0 0 24 24"><path d="M21 12a9 9 0 0 0-15.5-6.2L3 8"/><path d="M3 3v5h5"/><path d="M3 12a9 9 0 0 0 15.5 6.2L21 16"/><path d="M16 16h5v5"/></svg>',
  x: '<svg viewBox="0 0 24 24"><path d="M18 6 6 18"/><path d="m6 6 12 12"/></svg>',
};

const state = {
  status: null,
  files: [],
  config: null,
  task: null,
  query: "",
  course: "",
  fileStatus: "",
};

const $ = (selector) => document.querySelector(selector);

function installIcons(root = document) {
  root.querySelectorAll("[data-icon]").forEach((node) => {
    node.innerHTML = icons[node.dataset.icon] || "";
  });
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  const data = await response.json();
  if (!response.ok) {
    throw new Error(data.message || "요청에 실패했습니다.");
  }
  return data;
}

function showToast(message) {
  const toast = $("#toast");
  toast.textContent = message;
  toast.classList.add("visible");
  window.clearTimeout(showToast.timer);
  showToast.timer = window.setTimeout(() => toast.classList.remove("visible"), 2600);
}

function statusLabel(status) {
  if (status === "local") return "로컬 저장";
  if (status === "missing") return "누락";
  return "샘플";
}

function shortText(value, max = 46) {
  const text = String(value || "");
  return text.length > max ? `${text.slice(0, max - 1)}…` : text;
}

function renderStatus() {
  const status = state.status;
  if (!status) return;

  const ready = Object.values(status.requiredConfig || {}).every(Boolean);
  const oauth = status.googleOAuth || {};
  const isSharedSite = status.mode === "multi-user";
  $("#metricFiles").textContent = status.counts.files;
  $("#metricCourses").textContent = status.counts.courses;
  $("#metricLocal").textContent = oauth.tokenUsable ? "연결" : "대기";
  $("#metricMissing").textContent = status.counts.missing;
  $("#metricFilesNote").textContent = status.counts.files ? "관리 중인 파일" : "자료 없음";
  $("#metricDriveNote").textContent = oauth.tokenUsable
    ? `Drive 연결됨 · 로컬 ${status.counts.localFiles}개`
    : oauth.credentialsExists
      ? "OAuth 연결 필요"
      : "credentials.json 필요";

  $("#sidebarStatus").textContent = ready ? "설정 완료" : "설정 필요";
  $("#sidebarSchedule").textContent = `매일 ${status.scheduleTime || "08:00"} 실행`;
  $("#sidebarStatusDot").classList.toggle("ready", ready);

  const checklist = [
    ["LMS 로그인", status.requiredConfig.lms, "ID와 비밀번호"],
    ["Gemini API", status.requiredConfig.gemini, "자료 요약 키"],
    [
      "Google Drive",
      status.requiredConfig.drive,
      oauth.credentialsExists ? "OAuth 연결 필요" : "credentials.json 필요",
    ],
    ["Gmail 알림", status.requiredConfig.gmail, "앱 비밀번호"],
  ];

  $("#checklist").innerHTML = checklist
    .map(
      ([label, ok, note]) => `
        <div class="check-item ${ok ? "ready" : ""}">
          <div class="check-icon"><span class="icon" data-icon="${ok ? "check" : "alert"}"></span></div>
          <div>
            <strong>${label}</strong>
            <span>${ok ? "설정 완료" : note}</span>
          </div>
        </div>
      `,
    )
    .join("");
  installIcons($("#checklist"));

  const connectButton = $("#connectGoogleButton");
  const disconnectButton = $("#disconnectGoogleButton");
  connectButton.innerHTML = `<span class="icon" data-icon="cloud"></span>${
    oauth.tokenUsable ? "Google OAuth 재연결" : "Google OAuth 연결"
  }`;
  connectButton.title = oauth.credentialsExists
    ? `브라우저를 열어 Google Drive 권한을 연결합니다. 오류가 나면 ${oauth.requiredRedirectUri}를 Console에 추가하세요.`
    : "먼저 credentials.json을 준비해 주세요.";
  disconnectButton.hidden = !oauth.tokenExists;
  installIcons(connectButton);

  const openDownloadsButton = $("#openDownloadsButton");
  openDownloadsButton.disabled = isSharedSite;
  openDownloadsButton.title = isSharedSite
    ? "공유 웹사이트 모드에서는 서버 폴더를 직접 열 수 없습니다."
    : "다운로드 폴더를 엽니다.";
}

function renderCourseFilter() {
  const select = $("#courseFilter");
  const courses = [...new Set(state.files.map((file) => file.courseLabel).filter(Boolean))].sort();
  const current = select.value;
  select.innerHTML = '<option value="">전체 강의</option>';
  courses.forEach((course) => {
    const option = document.createElement("option");
    option.value = course;
    option.textContent = shortText(course, 28);
    select.append(option);
  });
  select.value = courses.includes(current) ? current : "";
}

function filteredFiles() {
  const query = state.query.trim().toLowerCase();
  return state.files.filter((file) => {
    const haystack = `${file.name} ${file.courseLabel} ${file.folder} ${file.type}`.toLowerCase();
    const matchesQuery = !query || haystack.includes(query);
    const matchesCourse = !state.course || file.courseLabel === state.course;
    const matchesStatus = !state.fileStatus || file.status === state.fileStatus;
    return matchesQuery && matchesCourse && matchesStatus;
  });
}

function renderFiles() {
  const rows = filteredFiles().slice(0, 120);
  const table = $("#filesTable");
  const empty = $("#emptyState");

  table.innerHTML = rows
    .map(
      (file) => `
        <tr>
          <td>
            <div class="file-name">
              <span class="file-type-icon"><span class="icon" data-icon="file"></span></span>
              <span title="${file.name}">${shortText(file.name, 54)}</span>
            </div>
          </td>
          <td>${shortText(file.courseLabel, 34)}</td>
          <td class="cell-muted">${shortText(file.folder || "강의 자료", 34)}</td>
          <td class="cell-muted">${file.type}</td>
          <td><span class="status-badge ${file.status}">${statusLabel(file.status)}</span></td>
        </tr>
      `,
    )
    .join("");

  empty.hidden = rows.length > 0;
  installIcons(table);
}

function renderTask(task) {
  state.task = task;
  const logBox = $("#logBox");
  const logs = task.logs || [];
  const taskLabel = task.kind === "sync" ? "동기화" : task.kind === "google-oauth" ? "Google OAuth" : "검증";
  const runButton = $("#runButton");
  const verifyButton = $("#verifyButton");
  if (task.running) {
    runButton.innerHTML = '<span class="icon" data-icon="x"></span>작업 중지';
    runButton.classList.remove("primary");
    runButton.classList.add("danger");
    verifyButton.disabled = true;
  } else {
    runButton.innerHTML = '<span class="icon" data-icon="sync"></span>지금 동기화';
    runButton.classList.add("primary");
    runButton.classList.remove("danger");
    verifyButton.disabled = false;
  }
  installIcons(runButton);

  $("#taskSummary").textContent = task.running
    ? `${taskLabel} 실행 중`
    : task.returnCode === null
      ? "대기 중"
      : `최근 종료 코드 ${task.returnCode}`;

  if (!logs.length) {
    logBox.innerHTML = '<div class="log-line">아직 실행 로그가 없습니다.</div>';
    return;
  }

  logBox.innerHTML = logs
    .slice(-80)
    .map((line) => `<div class="log-line">${escapeHtml(line)}</div>`)
    .join("");
  logBox.scrollTop = logBox.scrollHeight;
}

function escapeHtml(text) {
  return String(text)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

async function refreshAll() {
  try {
    const [status, files, task] = await Promise.all([
      api("/api/status"),
      api("/api/files"),
      api("/api/task"),
    ]);
    state.status = status;
    state.files = files.files || [];
    renderStatus();
    renderCourseFilter();
    renderFiles();
    renderTask(task);
  } catch (error) {
    showToast(error.message);
  }
}

async function loadConfig() {
  state.config = await api("/api/config");
  const form = $("#configForm");
  Object.entries(state.config).forEach(([key, value]) => {
    const input = form.elements[key];
    if (input && !key.startsWith("has")) input.value = value || "";
  });
}

async function startRun(path, label, payload = {}) {
  try {
    const data = await api(path, { method: "POST", body: JSON.stringify(payload) });
    showToast(data.message || `${label} 시작`);
    await refreshAll();
  } catch (error) {
    showToast(error.message);
  }
}

function bindEvents() {
  $("#searchInput").addEventListener("input", (event) => {
    state.query = event.target.value;
    renderFiles();
  });

  $("#courseFilter").addEventListener("change", (event) => {
    state.course = event.target.value;
    renderFiles();
  });

  $("#statusFilter").addEventListener("change", (event) => {
    state.fileStatus = event.target.value;
    renderFiles();
  });

  $("#runButton").addEventListener("click", () => {
    if (state.task?.running) {
      startRun("/api/stop", "중지");
      return;
    }
    const confirmed = window.confirm("LMS 동기화를 시작할까요? 다운로드, Drive 업로드, 알림이 실행됩니다.");
    if (confirmed) {
      startRun("/api/run", "동기화", { confirm: true });
    }
  });
  $("#verifyButton").addEventListener("click", () => startRun("/api/verify", "검증"));
  $("#connectGoogleButton").addEventListener("click", () => {
    const oauth = state.status?.googleOAuth || {};
    if (!oauth.credentialsExists) {
      $("#googleHelpDialog").showModal();
      showToast("credentials.json을 먼저 준비해 주세요.");
      return;
    }
    const confirmed = window.confirm("브라우저에서 Google Drive OAuth 권한 연결을 시작할까요?");
    if (confirmed) {
      api("/api/google/connect", { method: "POST", body: "{}" })
        .then((data) => {
          if (data.authUrl) {
            window.location.href = data.authUrl;
            return;
          }
          showToast(data.message || "Google OAuth 연결을 시작합니다.");
        })
        .catch((error) => showToast(error.message));
    }
  });
  $("#disconnectGoogleButton").addEventListener("click", () => {
    const confirmed = window.confirm("이 컴퓨터에 저장된 Google OAuth token.json을 제거할까요?");
    if (confirmed) {
      startRun("/api/google/disconnect", "Google 연결 해제");
    }
  });
  $("#googleHelpButton").addEventListener("click", () => $("#googleHelpDialog").showModal());
  $("#closeGoogleHelpButton").addEventListener("click", () => $("#googleHelpDialog").close());
  $("#openDownloadsButton").addEventListener("click", async () => {
    try {
      await api("/api/open-downloads", { method: "POST", body: "{}" });
      showToast("다운로드 폴더를 열었습니다.");
    } catch (error) {
      showToast(error.message);
    }
  });

  const dialog = $("#settingsDialog");
  const openSettings = async () => {
    await loadConfig();
    dialog.showModal();
  };
  $("#settingsButton").addEventListener("click", openSettings);
  document.querySelector('[data-view="settings"]').addEventListener("click", openSettings);
  $("#closeSettingsButton").addEventListener("click", () => dialog.close());
  $("#cancelSettingsButton").addEventListener("click", () => dialog.close());

  $("#configForm").addEventListener("submit", async (event) => {
    event.preventDefault();
    const formData = new FormData(event.currentTarget);
    const payload = Object.fromEntries(formData.entries());
    try {
      await api("/api/config", { method: "POST", body: JSON.stringify(payload) });
      dialog.close();
      showToast("설정을 저장했습니다.");
      await refreshAll();
    } catch (error) {
      showToast(error.message);
    }
  });

  document.querySelectorAll(".nav-item").forEach((button) => {
    button.addEventListener("click", () => {
      document.querySelectorAll(".nav-item").forEach((item) => item.classList.remove("active"));
      button.classList.add("active");
    });
  });
}

installIcons();
bindEvents();
refreshAll();
window.setInterval(refreshAll, 3500);
