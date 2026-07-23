const icons = {
  alert: '<svg viewBox="0 0 24 24"><path d="M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0Z"/><path d="M12 9v4"/><path d="M12 17h.01"/></svg>',
  book: '<svg viewBox="0 0 24 24"><path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"/><path d="M4 4.5A2.5 2.5 0 0 1 6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5Z"/></svg>',
  calendar: '<svg viewBox="0 0 24 24"><rect width="18" height="18" x="3" y="4" rx="2"/><path d="M16 2v4"/><path d="M8 2v4"/><path d="M3 10h18"/></svg>',
  check: '<svg viewBox="0 0 24 24"><path d="m20 6-11 11-5-5"/></svg>',
  clock: '<svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="10"/><path d="M12 6v6l4 2"/></svg>',
  cloud: '<svg viewBox="0 0 24 24"><path d="M17.5 19H7a5 5 0 1 1 .9-9.9A7 7 0 0 1 21 12.5 3.5 3.5 0 0 1 17.5 19Z"/></svg>',
  download: '<svg viewBox="0 0 24 24"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><path d="m7 10 5 5 5-5"/><path d="M12 15V3"/></svg>',
  edit: '<svg viewBox="0 0 24 24"><path d="M12 20h9"/><path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4Z"/></svg>',
  reply: '<svg viewBox="0 0 24 24"><path d="M9 17l-5-5 5-5"/><path d="M4 12h11a5 5 0 0 1 5 5v1"/></svg>',
  send: '<svg viewBox="0 0 24 24"><path d="M22 2 11 13"/><path d="M22 2 15 22l-4-9-9-4Z"/></svg>',
  trash: '<svg viewBox="0 0 24 24"><path d="M3 6h18"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6"/><path d="M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/><path d="M10 11v6"/><path d="M14 11v6"/></svg>',
  paperclip: '<svg viewBox="0 0 24 24"><path d="m21.4 11.1-8.5 8.5a5 5 0 0 1-7-7l8.5-8.5a3.3 3.3 0 0 1 4.7 4.7l-8.5 8.5a1.7 1.7 0 0 1-2.4-2.4l7.8-7.8"/></svg>',
  mailAllRead: '<svg viewBox="0 0 24 24"><path d="m16 12 2 2 4-4"/><path d="M21 10.5V7a2 2 0 0 0-2-2H5a2 2 0 0 0-2 2v10a2 2 0 0 0 2 2h9"/><path d="m3 7 9 6 4-2.7"/></svg>',
  grid: '<svg viewBox="0 0 24 24"><rect width="7" height="7" x="3" y="3" rx="1"/><rect width="7" height="7" x="14" y="3" rx="1"/><rect width="7" height="7" x="3" y="14" rx="1"/><rect width="7" height="7" x="14" y="14" rx="1"/></svg>',
  list: '<svg viewBox="0 0 24 24"><path d="M8 6h13"/><path d="M8 12h13"/><path d="M8 18h13"/><path d="M3 6h.01"/><path d="M3 12h.01"/><path d="M3 18h.01"/></svg>',
  eye: '<svg viewBox="0 0 24 24"><path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7-10-7-10-7Z"/><circle cx="12" cy="12" r="3"/></svg>',
  file: '<svg viewBox="0 0 24 24"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8Z"/><path d="M14 2v6h6"/></svg>',
  mail: '<svg viewBox="0 0 24 24"><rect width="20" height="16" x="2" y="4" rx="2"/><path d="m22 7-10 6L2 7"/></svg>',
  moon: '<svg viewBox="0 0 24 24"><path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8Z"/></svg>',
  sun: '<svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="4"/><path d="M12 2v2"/><path d="M12 20v2"/><path d="m4.9 4.9 1.4 1.4"/><path d="m17.7 17.7 1.4 1.4"/><path d="M2 12h2"/><path d="M20 12h2"/><path d="m6.3 17.7-1.4 1.4"/><path d="m19.1 4.9-1.4 1.4"/></svg>',
  sparkle: '<svg viewBox="0 0 24 24"><path d="M12 3v3"/><path d="M12 18v3"/><path d="M3 12h3"/><path d="M18 12h3"/><path d="m5.6 5.6 2.1 2.1"/><path d="m16.3 16.3 2.1 2.1"/><path d="m5.6 18.4 2.1-2.1"/><path d="m16.3 7.7 2.1-2.1"/></svg>',
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
  deadlines: { items: [], events: [], updatedAt: null },
  selection: { courses: {}, hidden: [] },
  courseEditMode: false,
  config: null,
  task: null,
  query: "",
  course: "",
  fileStatus: "",
  deadlineCourse: "",
  deadlineStatus: "",
  view: "dashboard",
  selectedFiles: new Set(),
  lastPickIndex: null,
  emails: { emails: [], briefing: "", interests: "", contacts: [], updatedAt: null },
  emailFilter: "",
  emailQuery: "",
  emailSort: "newest",
  emailView: "grid",
  emailFolder: "inbox",
  replyContext: null,
  attachments: [],
  interestTags: new Set(),
  calMonth: null, // {y, m}
  calSelected: null,
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

function escapeHtml(text) {
  return String(text ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function shortText(value, max = 46) {
  const text = String(value || "");
  return text.length > max ? `${text.slice(0, max - 1)}…` : text;
}

function statusLabel(status) {
  if (status === "local") return "로컬 저장";
  if (status === "missing") return "누락";
  return "샘플";
}

/* ===== 뷰 전환 ===== */
function switchView(view) {
  state.view = view;
  // 메일 쓰기는 메일함(view-emails) 셸을 공유하되 작성 pane을 연다
  const isCompose = view === "compose";
  const shellView = isCompose ? "emails" : view;
  document.querySelectorAll(".view").forEach((node) => {
    node.hidden = node.id !== `view-${shellView}`;
  });
  if (view === "settings") {
    populateSettings();
  }
  if (view === "emails") {
    showMailPane("list");
  }
  if (isCompose) {
    if (!state.config?.schoolEmail) {
      showToast("설정 → 학교 이메일에서 계정을 먼저 입력해 주세요.");
      openSettings();
      return;
    }
    openCompose();
  }
  document.querySelectorAll(".nav-item").forEach((item) => {
    item.classList.toggle("active", item.dataset.view === view);
  });
  // 메일함은 Gmail식 집중 모드: 사이드바 축소 + 우측 로그 레일 숨김
  document.querySelector(".app-shell").classList.toggle("mail-focus", shellView === "emails");
}

/* ===== 마감일 헬퍼 ===== */
function parseDue(item) {
  if (!item.due) return null;
  const date = new Date(item.due);
  return Number.isNaN(date.getTime()) ? null : date;
}

function isSubmitted(item) {
  return item.myStatus === "Graded" || item.myStatus === "NeedsGrading";
}

function dayDiff(date) {
  const now = new Date();
  const startToday = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const startDue = new Date(date.getFullYear(), date.getMonth(), date.getDate());
  return Math.round((startDue - startToday) / 86400000);
}

function ddayInfo(item) {
  const due = parseDue(item);
  if (!due) return { label: "기한 없음", cls: "normal" };
  const overdue = due.getTime() < Date.now();
  const diff = dayDiff(due);
  if (isSubmitted(item)) {
    return { label: "완료", cls: "done" };
  }
  if (overdue) {
    return { label: "지남", cls: "urgent" };
  }
  if (diff <= 0) return { label: "D-DAY", cls: "urgent" };
  if (diff <= 3) return { label: `D-${diff}`, cls: "soon" };
  return { label: `D-${diff}`, cls: "normal" };
}

function submitBadge(item) {
  if (item.myStatus === "Graded") {
    const score = item.myScore != null ? ` · ${item.myScore}점` : "";
    return `<span class="submit-badge graded">채점 완료${escapeHtml(score)}</span>`;
  }
  if (item.myStatus === "NeedsGrading") {
    return '<span class="submit-badge submitted">제출됨 · 채점 대기</span>';
  }
  const due = parseDue(item);
  if (due && due.getTime() < Date.now()) {
    return '<span class="submit-badge missing">미제출 · 마감 지남</span>';
  }
  return '<span class="submit-badge unknown">미제출</span>';
}

function formatDue(date) {
  if (!date) return "기한 없음";
  const month = date.getMonth() + 1;
  const day = date.getDate();
  const weekday = ["일", "월", "화", "수", "목", "금", "토"][date.getDay()];
  const hours = String(date.getHours()).padStart(2, "0");
  const minutes = String(date.getMinutes()).padStart(2, "0");
  return `${month}/${day} (${weekday}) ${hours}:${minutes}`;
}

function deadlineRow(item) {
  const due = parseDue(item);
  const dday = ddayInfo(item);
  return `
    <div class="deadline-row">
      <span class="dday-badge ${dday.cls}">${dday.label}</span>
      <div class="deadline-main">
        <strong title="${escapeHtml(item.name)}">${escapeHtml(shortText(item.name, 56))}</strong>
        <span>${escapeHtml(shortText(item.courseLabel || item.course, 44))}</span>
      </div>
      <div class="deadline-meta">
        <time>${formatDue(due)}</time>
        ${submitBadge(item)}
      </div>
    </div>
  `;
}

/* ===== 대시보드 ===== */
function renderUpcoming() {
  const list = $("#upcomingList");
  const now = Date.now();
  const matchesQuery = queryMatcher();
  const upcoming = state.deadlines.items
    .filter((item) => {
      const due = parseDue(item);
      return due && due.getTime() >= now && !isSubmitted(item) && matchesQuery(item);
    })
    .sort((a, b) => new Date(a.due) - new Date(b.due))
    .slice(0, 6);

  if (!upcoming.length) {
    list.innerHTML =
      '<div class="empty-state"><strong>다가오는 미제출 과제가 없습니다 🎉</strong><span>마감 새로고침으로 최신 상태를 확인할 수 있어요.</span></div>';
    return;
  }
  list.innerHTML = upcoming.map(deadlineRow).join("");
}

function renderEvents() {
  const box = $("#eventsList");
  const now = Date.now();
  const events = (state.deadlines.events || [])
    .filter((ev) => ev.start && new Date(ev.start).getTime() >= now - 3600000)
    .sort((a, b) => new Date(a.start) - new Date(b.start))
    .slice(0, 6);

  if (!events.length) {
    box.innerHTML = '<div class="empty-state"><strong>등록된 일정이 없습니다.</strong></div>';
    return;
  }

  box.innerHTML = events
    .map((ev) => {
      const start = new Date(ev.start);
      const sub = [ev.calendarName, ev.location].filter(Boolean).join(" · ");
      return `
        <div class="event-row">
          <span class="event-date">${formatDue(start)}</span>
          <div class="event-title">
            ${escapeHtml(shortText(ev.title, 52))}
            ${sub ? `<span class="event-sub">${escapeHtml(shortText(sub, 56))}</span>` : ""}
          </div>
        </div>
      `;
    })
    .join("");
}

/* ===== 과제 마감 뷰 ===== */
function queryMatcher() {
  const query = state.query.trim().toLowerCase();
  if (!query) return () => true;
  return (item) =>
    `${item.name} ${item.course} ${item.courseLabel}`.toLowerCase().includes(query);
}

function renderDeadlineFilters() {
  const select = $("#deadlineCourseFilter");
  const labels = [...new Set(state.deadlines.items.map((i) => i.courseLabel).filter(Boolean))].sort();
  const current = select.value;
  select.innerHTML = '<option value="">전체 과목</option>';
  labels.forEach((label) => {
    const option = document.createElement("option");
    option.value = label;
    option.textContent = shortText(label, 30);
    select.append(option);
  });
  select.value = labels.includes(current) ? current : "";
}

function renderDeadlines() {
  const list = $("#deadlineList");
  const empty = $("#deadlineEmpty");
  const matchesQuery = queryMatcher();
  const now = Date.now();

  const rows = state.deadlines.items
    .filter((item) => {
      if (!matchesQuery(item)) return false;
      if (state.deadlineCourse && item.courseLabel !== state.deadlineCourse) return false;
      const due = parseDue(item);
      const overdue = due ? due.getTime() < now : false;
      if (state.deadlineStatus === "open") return !isSubmitted(item) && !overdue;
      if (state.deadlineStatus === "missing") return !isSubmitted(item) && overdue;
      if (state.deadlineStatus === "submitted") return isSubmitted(item);
      return true;
    })
    .sort((a, b) => {
      // 미제출 & 마감 전 → 마감 임박 순 → 지난 항목 → 제출 완료
      const rank = (item) => {
        const due = parseDue(item);
        const overdue = due ? due.getTime() < now : false;
        if (!isSubmitted(item) && !overdue) return 0;
        if (!isSubmitted(item) && overdue) return 1;
        return 2;
      };
      const diff = rank(a) - rank(b);
      if (diff !== 0) return diff;
      return new Date(a.due || 0) - new Date(b.due || 0);
    });

  $("#deadlinesCount").textContent = `${rows.length}건`;
  const updated = state.deadlines.updatedAt;
  $("#deadlinesUpdatedAt").textContent = updated
    ? `마지막 갱신 ${updated.replace("T", " ")} · 상단의 '마감 새로고침'으로 다시 가져올 수 있습니다.`
    : "아직 가져온 마감 정보가 없습니다. 상단의 '마감 새로고침'을 눌러 주세요.";

  list.innerHTML = rows.map(deadlineRow).join("");
  empty.hidden = rows.length > 0;
}

/* ===== 이메일 뷰 (신문식 레이아웃) ===== */
const CATEGORY_ORDER = ["답신", "교수님", "세미나·행사", "취업·진로", "학생회", "행정·학생팀", "동아리·문화", "기타"];

const CATEGORY_COLORS = {
  "답신": "blue",
  "교수님": "coral",
  "학생회": "amber",
  "행정·학생팀": "neutral",
  "세미나·행사": "green",
  "취업·진로": "coral",
  "동아리·문화": "blue",
  "기타": "neutral",
};

const CATEGORY_ICONS = {
  "답신": "↩️",
  "교수님": "🎓",
  "세미나·행사": "🎤",
  "취업·진로": "💼",
  "학생회": "📣",
  "행정·학생팀": "🏛️",
  "동아리·문화": "🎵",
  "기타": "📎",
};

function formatEmailDate(iso) {
  if (!iso) return "";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "";
  return formatDue(date);
}

function emailMatchesQuery(mail) {
  const query = `${state.query} ${state.emailQuery || ""}`.trim().toLowerCase();
  if (!query) return true;
  const haystack = `${mail.subject} ${mail.summary || ""} ${mail.fromName} ${mail.fromEmail} ${mail.snippet} ${mail.category}`.toLowerCase();
  return query.split(/\s+/).every((word) => haystack.includes(word));
}

function isPastEvent(mail) {
  if (!mail.eventDate) return false;
  const date = new Date(mail.eventDate);
  return !Number.isNaN(date.getTime()) && date.getTime() < Date.now();
}

const INFO_ORDER = ["일시", "마감", "장소", "연사", "주최", "대상"];
const INFO_ICONS = { "일시": "🕐", "마감": "⏳", "장소": "📍", "연사": "🎤", "주최": "🏛", "대상": "👥" };

function infoChips(mail, max = 4) {
  const info = mail.info || {};
  const keys = INFO_ORDER.filter((key) => info[key]).slice(0, max);
  if (!keys.length) return "";
  return `
    <div class="info-chips">
      ${keys
        .map(
          (key) => `<span class="info-chip"><b>${INFO_ICONS[key] || ""} ${escapeHtml(key)}</b>${escapeHtml(info[key])}</span>`,
        )
        .join("")}
    </div>
  `;
}

function newsCard(mail, featured = false) {
  const color = CATEGORY_COLORS[mail.category] || "neutral";
  const headline = mail.summary || mail.subject;
  const showSubject = Boolean(mail.summary) && mail.summary !== mail.subject;
  const icon = CATEGORY_ICONS[mail.category] || "📎";
  return `
    <article class="news-card ${featured ? "featured" : ""} ${mail.unread ? "unread" : ""}" data-mail-id="${mail.id}">
      <div class="news-card-top">
        <span class="category-chip ${color}">${icon} ${escapeHtml(mail.category || "기타")}</span>
        ${mail.unread ? '<span class="unread-dot" title="안 읽은 메일"></span>' : ""}
        <span class="card-actions">
          <button type="button" class="mail-act" data-act="read" title="${mail.unread ? "읽음 표시" : "안읽음 표시"}">
            <span class="icon" data-icon="${mail.unread ? "check" : "mail"}"></span>
          </button>
          <button type="button" class="mail-act danger" data-act="delete" title="삭제">
            <span class="icon" data-icon="trash"></span>
          </button>
        </span>
      </div>
      <strong class="news-headline">${escapeHtml(headline)}</strong>
      ${showSubject ? `<span class="news-subject" title="${escapeHtml(mail.subject)}">${escapeHtml(shortText(mail.subject, featured ? 80 : 56))}</span>` : ""}
      <p class="email-snippet">${escapeHtml(shortText(mail.snippet, featured ? 200 : 110))}</p>
      <div class="news-card-foot">
        <span class="news-card-sender">${escapeHtml(shortText(mail.fromName || mail.fromEmail, 26))} · ${formatEmailDate(mail.date)}</span>
      </div>
    </article>
  `;
}

function openEmailDetail(mail) {
  const color = CATEGORY_COLORS[mail.category] || "neutral";
  const icon = CATEGORY_ICONS[mail.category] || "📎";
  const chip = $("#readCategory");
  chip.className = `category-chip ${color}`;
  chip.textContent = `${icon} ${mail.category || "기타"}`;
  $("#readSubject").textContent = mail.subject;
  const date = mail.date ? formatEmailDate(mail.date) : "";
  $("#readMeta").textContent = `${mail.fromName || mail.fromEmail} <${mail.fromEmail}>${date ? " · " + date : ""}`;

  const summary = $("#readSummary");
  if (mail.summary && mail.summary !== mail.subject) {
    summary.textContent = mail.summary;
    summary.hidden = false;
  } else {
    summary.hidden = true;
  }

  $("#readBody").textContent = mail.body || mail.snippet || "(본문을 불러오지 못했습니다)";
  state.replyContext = mail;
  // 읽음/안읽음 토글 아이콘
  const markBtn = $("#readMarkButton");
  markBtn.querySelector(".icon").dataset.icon = mail.unread ? "check" : "mail";
  markBtn.title = mail.unread ? "읽음 표시" : "안읽음 표시";
  installIcons(markBtn);

  showMailPane("read");
  $("#mailReadPane").querySelector(".mail-read-scroll").scrollTop = 0;

  // 열람 시 자동 읽음 처리
  if (mail.unread) {
    setEmailRead(mail, true, { silent: true });
  }
}

/* ===== 메일 읽음/삭제 액션 ===== */
async function setEmailRead(mail, seen, { silent = false } = {}) {
  // 로컬 상태 즉시 반영
  const target = state.emails.emails.find((m) => m.id === mail.id);
  if (target) target.unread = !seen;
  renderEmails();
  try {
    await api("/api/mark-read", {
      method: "POST",
      body: JSON.stringify({ uid: mail.uid, folder: mail.folder, seen }),
    });
    if (!silent) showToast(seen ? "읽음으로 표시했습니다." : "안읽음으로 표시했습니다.");
  } catch (error) {
    if (!silent) showToast(error.message);
  }
}

async function deleteEmail(mail) {
  const target = state.emails.emails.find((m) => m.id === mail.id);
  if (target) {
    state.emails.emails = state.emails.emails.filter((m) => m.id !== mail.id);
  }
  renderEmails();
  try {
    await api("/api/delete-email", {
      method: "POST",
      body: JSON.stringify({ uid: mail.uid, folder: mail.folder }),
    });
    showToast("메일을 삭제했습니다.");
  } catch (error) {
    showToast(error.message);
  }
}

async function markAllRead() {
  state.emails.emails.forEach((m) => {
    if (m.folder === state.emailFolder || (state.emailFolder !== "sent" && state.emailFolder !== "promo" && m.folder === "inbox")) {
      m.unread = false;
    }
  });
  renderEmails();
  try {
    const data = await api("/api/mark-all-read", {
      method: "POST",
      body: JSON.stringify({ folder: state.emailFolder === "promo" || state.emailFolder === "sent" ? state.emailFolder : "inbox" }),
    });
    showToast(data.message || "모두 읽음으로 표시했습니다.");
  } catch (error) {
    showToast(error.message);
  }
}

/* ===== 인앱 작성 화면 ===== */
function openCompose({ to = "", cc = "", bcc = "", subject = "", body = "", inReplyTo = "", references = "", title = "새 메일" } = {}) {
  const form = $("#composeForm");
  form.elements.to.value = to;
  form.elements.cc.value = cc;
  form.elements.bcc.value = bcc;
  form.elements.subject.value = subject;
  form.elements.body.value = body;
  form.dataset.inReplyTo = inReplyTo;
  form.dataset.references = references;
  $("#composeTitle").textContent = title;
  $("#ccField").hidden = !cc;
  $("#bccField").hidden = !bcc;
  $("#htmlModeToggle").checked = false;
  state.attachments = [];
  renderAttachments();
  const account = state.config?.schoolEmail || "";
  $("#composeFrom").textContent = account ? `보내는 사람: ${account}` : "설정에서 학교 이메일을 먼저 입력해 주세요.";
  showMailPane("compose");
  form.elements[to ? "subject" : "to"].focus();
}

function closeCompose() {
  state.attachments = [];
  showMailPane("list");
}

/* 작성 중인 내용이 있는지 (폴더 이동 시 실수로 날리는 것 방지) */
function composeHasContent() {
  const form = $("#composeForm");
  if (!form) return false;
  const filled = ["to", "cc", "bcc", "subject", "body"].some(
    (name) => (form.elements[name]?.value || "").trim() !== "",
  );
  return filled || (state.attachments || []).length > 0;
}

function renderAttachments() {
  const wrap = $("#composeAttachments");
  const atts = state.attachments || [];
  wrap.innerHTML = atts
    .map(
      (a, i) => `
      <span class="attach-chip">
        <span class="icon" data-icon="paperclip"></span>
        <span class="attach-name">${escapeHtml(a.filename)}</span>
        <span class="attach-size">${formatBytes(a.size)}</span>
        <button type="button" class="attach-remove" data-idx="${i}" aria-label="제거">✕</button>
      </span>`,
    )
    .join("");
  installIcons(wrap);
  const total = atts.reduce((s, a) => s + a.size, 0);
  $("#attachNote").textContent = atts.length ? `첨부 ${atts.length}개 · ${formatBytes(total)}` : "";
}

function formatBytes(n) {
  if (n < 1024) return `${n}B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(0)}KB`;
  return `${(n / 1024 / 1024).toFixed(1)}MB`;
}

function fileToBase64(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result).split(",")[1] || "");
    reader.onerror = reject;
    reader.readAsDataURL(file);
  });
}

async function importFromDrive() {
  try {
    const data = await api("/api/drive/list");
    if (!data.files || !data.files.length) {
      showToast("Drive에 가져올 파일이 없습니다. 먼저 구글 계정을 연결하세요.");
      return;
    }
    const options = data.files
      .slice(0, 20)
      .map((f, i) => `${i + 1}. ${f.name}`)
      .join("\n");
    const pick = window.prompt(`Google Drive에서 첨부할 파일 번호를 입력하세요:\n\n${options}`);
    const idx = Number(pick) - 1;
    if (Number.isNaN(idx) || idx < 0 || idx >= data.files.length) return;
    const file = data.files[idx];
    showToast(`${file.name} 가져오는 중…`);
    const got = await api(`/api/drive/get?id=${encodeURIComponent(file.id)}`);
    state.attachments.push({ filename: got.filename, size: got.size, content: got.content });
    renderAttachments();
    showToast(`${got.filename} 첨부됨`);
  } catch (error) {
    showToast(error.message);
  }
}

/* ===== 주소 자동완성 (DGIST 연락처) ===== */
function contactMatches(term) {
  const q = term.trim().toLowerCase();
  if (!q) return [];
  const contacts = state.emails.contacts || [];
  const hits = contacts.filter(
    (c) => c.email.toLowerCase().includes(q) || (c.name || "").toLowerCase().includes(q),
  );
  // dgist 도메인 자동 완성 후보 추가 (아이디만 입력 시)
  if (/^[a-z0-9._-]+$/i.test(term.trim()) && !term.includes("@")) {
    const guess = `${term.trim()}@dgist.ac.kr`;
    if (!hits.some((c) => c.email === guess)) {
      hits.push({ email: guess, name: "DGIST 메일", count: 0, guess: true });
    }
  }
  return hits.slice(0, 6);
}

function setupAutocomplete() {
  document.querySelectorAll('#composeForm input[data-ac="1"]').forEach((input) => {
    const menu = document.getElementById(`ac-${input.name}`);
    if (!menu) return;
    let active = -1;

    const currentToken = () => {
      const val = input.value;
      const start = Math.max(val.lastIndexOf(","), val.lastIndexOf(";")) + 1;
      return { start, text: val.slice(start).trim() };
    };

    const closeMenu = () => {
      menu.hidden = true;
      menu.innerHTML = "";
      active = -1;
    };

    const applyChoice = (email) => {
      const { start } = currentToken();
      const before = input.value.slice(0, start);
      input.value = `${before}${before && !before.trimEnd().endsWith(",") ? " " : ""}${email}, `;
      closeMenu();
      input.focus();
    };

    const showMenu = () => {
      const { text } = currentToken();
      const matches = contactMatches(text);
      if (!matches.length) return closeMenu();
      menu.innerHTML = matches
        .map(
          (c, i) => `
          <button type="button" class="ac-item ${i === active ? "active" : ""}" data-email="${escapeHtml(c.email)}">
            <span class="ac-name">${escapeHtml(c.name || c.email)}</span>
            <span class="ac-email">${escapeHtml(c.email)}${c.guess ? " · 추정" : ""}</span>
          </button>`,
        )
        .join("");
      menu.hidden = false;
    };

    input.addEventListener("input", () => {
      active = -1;
      showMenu();
    });
    input.addEventListener("keydown", (event) => {
      const items = [...menu.querySelectorAll(".ac-item")];
      if (menu.hidden || !items.length) return;
      if (event.key === "ArrowDown") {
        event.preventDefault();
        active = (active + 1) % items.length;
      } else if (event.key === "ArrowUp") {
        event.preventDefault();
        active = (active - 1 + items.length) % items.length;
      } else if (event.key === "Enter" && active >= 0) {
        event.preventDefault();
        applyChoice(items[active].dataset.email);
        return;
      } else if (event.key === "Escape") {
        closeMenu();
        return;
      } else {
        return;
      }
      items.forEach((it, i) => it.classList.toggle("active", i === active));
    });
    menu.addEventListener("mousedown", (event) => {
      const item = event.target.closest(".ac-item");
      if (item) {
        event.preventDefault();
        applyChoice(item.dataset.email);
      }
    });
    input.addEventListener("blur", () => setTimeout(closeMenu, 150));
  });
}

function replyToCurrentEmail() {
  const mail = state.replyContext;
  if (!mail) return;
  const subject = /^\s*re\s*:/i.test(mail.subject) ? mail.subject : `Re: ${mail.subject}`;
  const when = mail.date ? formatEmailDate(mail.date) : "";
  const quoted = (mail.body || mail.snippet || "")
    .split("\n")
    .map((line) => `> ${line}`)
    .join("\n");
  const body = `\n\n----- 원본 메일 (${escapeHtml(mail.fromName || mail.fromEmail)}${when ? ", " + when : ""}) -----\n${quoted}`;
  openCompose({
    to: mail.fromEmail,
    subject,
    body,
    inReplyTo: mail.messageId || "",
    references: mail.messageId || "",
    title: "답장",
  });
}

const MAIL_FOLDERS = [
  { key: "inbox", label: "받은 편지함", icon: "mail" },
  { key: "unread", label: "안 읽음", icon: "alert" },
  { key: "starred", label: "관심 메일", icon: "sparkle" },
  { key: "sent", label: "보낸 편지함", icon: "send" },
  { key: "lms", label: "LMS·공지", icon: "book" },
  { key: "promo", label: "프로모션", icon: "folder" },
  { key: "all", label: "전체 메일", icon: "list" },
];

// 폴더별 메일 필터 (검색·카테고리칩과 별개)
function mailInFolder(mail, folder) {
  switch (folder) {
    case "inbox":
      return mail.folder === "inbox";
    case "sent":
      return mail.folder === "sent";
    case "promo":
      return mail.folder === "promo";
    case "unread":
      return mail.folder === "inbox" && mail.unread;
    case "starred":
      return (mail.score || 0) >= 6;
    case "lms":
      return /lms|blackboard|공지|학사|academic/i.test(`${mail.fromEmail} ${mail.fromName} ${mail.subject}`);
    case "all":
    default:
      return true;
  }
}

function folderCount(emails, folder) {
  return emails.filter((m) => mailInFolder(m, folder)).length;
}

function renderMailFolders(emails) {
  const nav = $("#mailFolders");
  if (!nav) return;
  nav.innerHTML = MAIL_FOLDERS.map((f) => {
    const count = folderCount(emails, f.key);
    const unreadInFolder = emails.filter((m) => mailInFolder(m, f.key) && m.unread).length;
    return `
      <button type="button" class="mail-folder ${state.emailFolder === f.key ? "active" : ""}" data-folder="${f.key}">
        <span class="icon" data-icon="${f.icon}"></span>
        <span class="mf-label">${f.label}</span>
        ${unreadInFolder ? `<span class="mf-count">${unreadInFolder}</span>` : count ? `<span class="mf-count muted">${count}</span>` : ""}
      </button>
    `;
  }).join("");
  installIcons(nav);
  const current = MAIL_FOLDERS.find((f) => f.key === state.emailFolder);
  $("#mailFolderTitle").textContent = current ? current.label : "메일함";
}

function renderEmailFilterChips(emails) {
  const wrap = $("#emailFilterChips");
  if (!emails.length) {
    wrap.innerHTML = "";
    return;
  }
  const unreadCount = emails.filter((mail) => mail.unread).length;
  const chips = [
    { key: "", label: `📥 전체 ${emails.length}` },
    { key: "unread", label: `🔴 안읽음 ${unreadCount}` },
  ];
  CATEGORY_ORDER.forEach((category) => {
    const count = emails.filter((mail) => mail.category === category).length;
    if (count) chips.push({ key: category, label: `${CATEGORY_ICONS[category] || ""} ${category} ${count}` });
  });
  wrap.innerHTML = chips
    .map(
      (chip) => `
        <button type="button" class="filter-chip ${state.emailFilter === chip.key ? "active" : ""}"
          data-filter="${escapeHtml(chip.key)}">${escapeHtml(chip.label)}</button>
      `,
    )
    .join("");
}

function renderEmails() {
  const data = state.emails;
  const emails = data.emails || [];

  renderMailFolders(emails);

  // 현재 폴더의 메일만 (지난 일정 숨김 설정은 받은편지함에서만 적용)
  const hidePast = Boolean(state.config?.hidePastEmails) && state.emailFolder === "inbox";
  const folderPool = emails.filter(
    (mail) => mailInFolder(mail, state.emailFolder) && !(hidePast && isPastEvent(mail)),
  );
  const isInboxLike = state.emailFolder === "inbox";

  const unreadInFolder = folderPool.filter((m) => m.unread).length;
  $("#emailsUpdatedAt").textContent = data.updatedAt
    ? `${folderPool.length}통${unreadInFolder ? ` · 안읽음 ${unreadInFolder}` : ""}`
    : "아직 가져온 메일이 없습니다. '새로고침'을 눌러 주세요.";
  // "모두 읽음" 버튼: 받은편지함에 안읽음 있을 때만
  $("#markAllReadButton").hidden = !(isInboxLike && unreadInFolder > 0);

  // 브리핑은 받은편지함에서만, 아주 간결하게 (한 줄 + todo)
  const briefingPanel = $("#briefingPanel");
  const briefing = data.briefing || {};
  const intro = typeof briefing === "string" ? briefing : briefing.intro || "";
  const todo = typeof briefing === "object" && Array.isArray(briefing.todo) ? briefing.todo.filter(Boolean) : [];
  briefingPanel.hidden = !emails.length || !isInboxLike || (!intro && !todo.length);
  $("#briefingText").textContent = intro;
  $("#briefingTodo").innerHTML = todo.length
    ? todo.map((t) => `<span class="todo-item">${escapeHtml(t)}</span>`).join("")
    : "";

  // 카테고리 칩은 받은편지함에서만
  if (isInboxLike) {
    renderEmailFilterChips(folderPool);
  } else {
    $("#emailFilterChips").innerHTML = "";
    state.emailFilter = "";
  }

  // 필터/검색 적용
  const searching = Boolean(state.emailFilter) || Boolean(state.query.trim()) || Boolean(state.emailQuery?.trim());
  const visible = folderPool.filter((mail) => {
    if (!emailMatchesQuery(mail)) return false;
    if (state.emailFilter === "unread") return mail.unread;
    if (state.emailFilter) return (mail.category || "기타") === state.emailFilter;
    return true;
  });

  // 정렬
  const sorted = sortEmails(visible, state.emailSort);

  // 메인 뉴스: 받은편지함 기본(최신순 & 필터 없음)일 때만 상위 관심 3건을 크게
  let featured = [];
  if (isInboxLike && !searching && state.emailSort === "newest" && state.emailView === "grid") {
    featured = visible
      .filter((mail) => (mail.score || 0) >= 5)
      .sort((a, b) => (b.score || 0) - (a.score || 0) || new Date(b.date) - new Date(a.date))
      .slice(0, 3);
  }
  const featuredIds = new Set(featured.map((mail) => mail.id));
  $("#newsFeatured").innerHTML = featured.length
    ? `
      <div class="featured-main">${newsCard(featured[0], true)}</div>
      <div class="featured-side">${featured.slice(1).map((mail) => newsCard(mail)).join("")}</div>
    `
    : "";

  const rest = sorted.filter((mail) => !featuredIds.has(mail.id));
  const grid = $("#newsGrid");
  grid.classList.toggle("list-mode", state.emailView === "list");
  grid.innerHTML =
    state.emailView === "list"
      ? rest.map((mail) => emailListRow(mail)).join("")
      : rest.map((mail) => newsCard(mail)).join("");
  installIcons(grid);
  installIcons($("#newsFeatured"));
  $("#emailEmpty").hidden = visible.length > 0;

  const badge = $("#emailBadge");
  const count = emails.filter((mail) => (mail.score || 0) >= 6 && mail.unread).length;
  badge.textContent = count;
  badge.hidden = !count;
}

function sortEmails(list, mode) {
  const arr = [...list];
  const byDateDesc = (a, b) => new Date(b.date || 0) - new Date(a.date || 0);
  switch (mode) {
    case "oldest":
      return arr.sort((a, b) => new Date(a.date || 0) - new Date(b.date || 0));
    case "sender":
      return arr.sort(
        (a, b) => (a.fromName || a.fromEmail || "").localeCompare(b.fromName || b.fromEmail || "", "ko") || byDateDesc(a, b),
      );
    case "subject":
      return arr.sort((a, b) => (a.subject || "").localeCompare(b.subject || "", "ko"));
    case "score":
      return arr.sort((a, b) => (b.score || 0) - (a.score || 0) || byDateDesc(a, b));
    case "newest":
    default:
      // 안읽음 우선 후 최신순
      return arr.sort((a, b) => Number(b.unread) - Number(a.unread) || byDateDesc(a, b));
  }
}

function emailListRow(mail) {
  const color = CATEGORY_COLORS[mail.category] || "neutral";
  const icon = CATEGORY_ICONS[mail.category] || "📎";
  const title = mail.summary || mail.subject;
  return `
    <div class="email-list-row ${mail.unread ? "unread" : ""}" data-mail-id="${mail.id}">
      <span class="list-unread">${mail.unread ? '<span class="unread-dot"></span>' : ""}</span>
      <span class="category-chip ${color} list-chip">${icon}</span>
      <div class="list-main">
        <strong>${escapeHtml(shortText(title, 70))}</strong>
        <span>${escapeHtml(shortText(mail.fromName || mail.fromEmail, 24))}${mail.summary && mail.summary !== mail.subject ? " · " + escapeHtml(shortText(mail.subject, 40)) : ""}</span>
      </div>
      <span class="list-actions">
        <button type="button" class="mail-act" data-act="read" title="${mail.unread ? "읽음 표시" : "안읽음 표시"}">
          <span class="icon" data-icon="${mail.unread ? "check" : "mail"}"></span>
        </button>
        <button type="button" class="mail-act danger" data-act="delete" title="삭제">
          <span class="icon" data-icon="trash"></span>
        </button>
      </span>
      <time class="list-date">${formatEmailDate(mail.date)}</time>
    </div>
  `;
}

/* ===== 강의 뷰 ===== */
function courseSummaries() {
  const map = new Map();
  const ensure = (label) => {
    if (!map.has(label)) {
      map.set(label, { label, korean: "", files: 0, deadlines: 0, next: null });
    }
    return map.get(label);
  };

  state.files.forEach((file) => {
    const entry = ensure(file.courseLabel || "기타");
    entry.files += 1;
    if (!entry.korean && file.course && file.course.includes("(")) {
      entry.korean = file.course.split("(", 1)[0].trim();
    }
  });

  const now = Date.now();
  state.deadlines.items.forEach((item) => {
    const entry = ensure(item.courseLabel || "기타");
    entry.deadlines += 1;
    if (!entry.korean && item.course && item.course.includes("(")) {
      entry.korean = item.course.split("(", 1)[0].trim();
    }
    const due = parseDue(item);
    if (due && due.getTime() >= now && !isSubmitted(item)) {
      if (!entry.next || due < entry.next.due) {
        entry.next = { due, name: item.name };
      }
    }
  });

  (state.status?.courses || []).forEach((label) => ensure(label));
  return [...map.values()].sort((a, b) => a.label.localeCompare(b.label));
}

function renderCourses() {
  const grid = $("#courseGrid");
  const empty = $("#courseEmpty");
  const query = state.query.trim().toLowerCase();
  const hidden = state.selection.hidden || [];
  const summaries = courseSummaries().filter(
    (course) =>
      !hidden.includes(course.label) &&
      (!query ||
        course.label.toLowerCase().includes(query) ||
        course.korean.toLowerCase().includes(query)),
  );

  // 편집 모드: 카드 흔들림 + 제거 버튼
  grid.classList.toggle("editing", !!state.courseEditMode);
  const editLabel = $("#courseEditLabel");
  if (editLabel) editLabel.textContent = state.courseEditMode ? "완료" : "편집";
  $("#courseEditButton")?.setAttribute("aria-pressed", String(!!state.courseEditMode));
  const restoreBtn = $("#restoreCoursesButton");
  if (restoreBtn) {
    restoreBtn.hidden = hidden.length === 0;
    restoreBtn.textContent = `숨긴 과목 ${hidden.length}개 복원`;
  }

  empty.hidden = summaries.length > 0;
  grid.innerHTML = summaries
    .map((course) => {
      const enabled = state.selection.courses[course.label] !== false;
      const removeBtn = state.courseEditMode
        ? `<button type="button" class="course-remove" data-remove="${escapeHtml(course.label)}" aria-label="과목 제거" title="목록에서 제거">✕</button>`
        : "";
      const nextLine = course.next
        ? `다음 마감 <b>${formatDue(course.next.due)}</b> · ${escapeHtml(shortText(course.next.name, 30))}`
        : "다가오는 미제출 마감 없음";
      return `
        <article class="course-card ${enabled ? "" : "off"}">
          ${removeBtn}
          <div class="course-card-top">
            <h3>
              ${escapeHtml(shortText(course.label, 40))}
              ${course.korean ? `<span class="course-korean">${escapeHtml(shortText(course.korean, 36))}</span>` : ""}
            </h3>
            <label class="toggle" title="Drive 자동 업로드 포함 여부">
              <input type="checkbox" data-course="${escapeHtml(course.label)}" ${enabled ? "checked" : ""} />
              <span class="track"></span>
            </label>
          </div>
          <div class="course-stats">
            <span>자료 <b>${course.files}</b></span>
            <span>과제 <b>${course.deadlines}</b></span>
            <span>${enabled ? "업로드 포함" : "업로드 제외"}</span>
          </div>
          <div class="course-next">${nextLine}</div>
        </article>
      `;
    })
    .join("");

  grid.querySelectorAll("input[data-course]").forEach((input) => {
    input.addEventListener("change", async (event) => {
      const label = event.target.dataset.course;
      state.selection.courses[label] = event.target.checked;
      try {
        await api("/api/selection", {
          method: "POST",
          body: JSON.stringify(state.selection),
        });
        showToast(
          event.target.checked
            ? `'${shortText(label, 24)}' 과목을 업로드에 포함합니다.`
            : `'${shortText(label, 24)}' 과목을 업로드에서 제외합니다.`,
        );
        renderCourses();
      } catch (error) {
        showToast(error.message);
      }
    });
  });

  // 편집 모드에서 과목 제거 (자료는 지우지 않고 목록에서만 숨김)
  grid.querySelectorAll("[data-remove]").forEach((btn) => {
    btn.addEventListener("click", async (event) => {
      event.stopPropagation();
      const label = btn.dataset.remove;
      const ok = window.confirm(
        `'${shortText(label, 30)}' 과목을 목록에서 제거할까요?\n받아둔 자료는 삭제되지 않으며, '숨긴 과목 복원'으로 되돌릴 수 있습니다.`,
      );
      if (!ok) return;
      state.selection.hidden = [...new Set([...(state.selection.hidden || []), label])];
      try {
        await api("/api/selection", { method: "POST", body: JSON.stringify(state.selection) });
        showToast(`'${shortText(label, 24)}' 과목을 목록에서 제거했습니다.`);
        renderCourses();
      } catch (error) {
        showToast(error.message);
      }
    });
  });
}

/* ===== 상태/메트릭 ===== */
function renderCourseChangeBanner() {
  const banner = $("#courseChangeBanner");
  if (!banner) return;
  const change = state.status?.courseChange || {};
  if (!change.pending) {
    banner.hidden = true;
    return;
  }
  const added = change.added || [];
  const removed = change.removed || [];
  const parts = [];
  if (added.length) parts.push(`새로 추가된 과목 ${added.length}개: ${added.map((c) => shortText(c.name, 24)).join(", ")}`);
  if (removed.length) parts.push(`사라진 과목 ${removed.length}개: ${removed.map((c) => shortText(c.name, 24)).join(", ")}`);
  $("#courseChangeDetail").textContent = parts.join(" / ");
  banner.hidden = false;
}

function renderStatus() {
  const status = state.status;
  if (!status) return;

  renderCourseChangeBanner();

  const ready = Object.values(status.requiredConfig || {}).every(Boolean);
  const oauth = status.googleOAuth || {};
  const isSharedSite = status.mode === "multi-user";
  const deadlineInfo = status.deadlines || {};

  $("#metricFiles").textContent = status.counts.files;
  $("#metricCourses").textContent = status.counts.courses;
  $("#metricLocal").textContent = oauth.tokenUsable ? "연결" : "대기";
  $("#metricFilesNote").textContent = status.counts.files ? "관리 중인 파일" : "자료 없음";
  $("#metricCoursesNote").textContent = status.counts.missing
    ? `누락 ${status.counts.missing}건 포함`
    : "분류된 과목";
  $("#metricDriveNote").textContent = oauth.tokenUsable
    ? `Drive 연결됨 · 로컬 ${status.counts.localFiles}개`
    : oauth.credentialsExists
      ? "OAuth 연결 필요"
      : "credentials.json 필요";

  $("#metricDeadlines").textContent = deadlineInfo.upcoming7d ?? 0;
  $("#metricDeadlinesNote").textContent = deadlineInfo.overdueUnsubmitted
    ? `지난 미제출 ${deadlineInfo.overdueUnsubmitted}건`
    : "7일 이내 미제출";

  const badge = $("#deadlineBadge");
  const badgeCount = deadlineInfo.upcoming7d ?? 0;
  badge.textContent = badgeCount;
  badge.hidden = !badgeCount;

  $("#sidebarStatus").textContent = ready ? "설정 완료" : "설정 필요";
  $("#sidebarSchedule").textContent = `매일 ${status.scheduleTime || "08:00"} 실행`;
  $("#sidebarStatusDot").classList.toggle("ready", ready);

  renderGoogleSection();

  const openDownloadsButton = $("#openDownloadsButton");
  openDownloadsButton.disabled = isSharedSite;
  openDownloadsButton.title = isSharedSite
    ? "공유 웹사이트 모드에서는 서버 폴더를 직접 열 수 없습니다."
    : "다운로드 폴더를 엽니다.";
}

/* ===== 설정: 구글 계정 섹션 ===== */
function renderGoogleSection() {
  const oauth = state.status?.googleOAuth || {};
  const statusText = $("#googleStatusText");
  const loginButton = $("#googleLoginButton");
  const disconnectButton = $("#disconnectGoogleButton");
  if (!statusText || !loginButton) return;

  if (oauth.tokenUsable) {
    statusText.textContent = "연결됨 · Drive 업로드 사용 가능";
    statusText.classList.add("connected");
    loginButton.textContent = "다시 로그인";
    loginButton.classList.remove("primary");
  } else {
    statusText.textContent = oauth.credentialsExists
      ? "연결 안 됨 · 로그인이 필요합니다"
      : "credentials.json 준비 필요 (도움말 참고)";
    statusText.classList.remove("connected");
    loginButton.textContent = "구글 계정으로 로그인";
    loginButton.classList.add("primary");
  }
  disconnectButton.hidden = !oauth.tokenExists;
}

/* ===== 파일 저장 ===== */
async function saveFilesToComputer(localNames) {
  const names = Array.isArray(localNames) ? localNames : [localNames];
  if (!names.length) return;
  if (state.status?.mode === "multi-user") {
    names.slice(0, 10).forEach((name) => {
      window.open(`/api/file?name=${encodeURIComponent(name)}`, "_blank");
    });
    if (names.length > 10) showToast("브라우저 모드에서는 한 번에 10개까지 다운로드됩니다.");
    return;
  }
  try {
    const data = await api("/api/save-local", {
      method: "POST",
      body: JSON.stringify({ names }),
    });
    showToast(data.message || "다운로드 폴더에 저장했습니다.");
    state.selectedFiles.clear();
    renderFiles();
  } catch (error) {
    showToast(error.message);
  }
}

function updateBulkSaveButton() {
  const button = $("#bulkSaveButton");
  const count = state.selectedFiles.size;
  button.disabled = count === 0;
  button.innerHTML = `<span class="icon" data-icon="download"></span>선택 저장${count ? ` (${count})` : ""}`;
  installIcons(button);
}

/* ===== 자료 뷰 ===== */
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
    // file.course에 한국어 과목명이 포함되어 '프로그래밍', '생명과학개론' 같은 검색도 가능
    const haystack = `${file.name} ${file.course} ${file.courseLabel} ${file.folder} ${file.type}`.toLowerCase();
    const matchesQuery = !query || haystack.includes(query);
    const matchesCourse = !state.course || file.courseLabel === state.course;
    const matchesStatus = !state.fileStatus || file.status === state.fileStatus;
    return matchesQuery && matchesCourse && matchesStatus;
  });
}

function renderFiles() {
  const rows = filteredFiles().slice(0, 150);
  const table = $("#filesTable");
  const empty = $("#emptyState");

  // 화면에 없는 파일은 선택에서 제거
  const visible = new Set(rows.filter((f) => f.status === "local").map((f) => f.localName));
  [...state.selectedFiles].forEach((name) => {
    if (!visible.has(name)) state.selectedFiles.delete(name);
  });

  table.innerHTML = rows
    .map(
      (file) => `
        <tr>
          <td class="check-col">
            <input type="checkbox" data-pick="${escapeHtml(file.localName)}"
              ${state.selectedFiles.has(file.localName) ? "checked" : ""}
              ${file.status === "local" ? "" : "disabled"}
              aria-label="파일 선택" />
          </td>
          <td>
            <div class="file-name">
              <span class="file-type-icon"><span class="icon" data-icon="file"></span></span>
              <span title="${escapeHtml(file.name)}">${escapeHtml(shortText(file.name, 54))}</span>
            </div>
          </td>
          <td title="${escapeHtml(file.course)}">${escapeHtml(shortText(file.courseLabel, 34))}</td>
          <td class="cell-muted">${escapeHtml(shortText(file.folder || "강의 자료", 34))}</td>
          <td class="cell-muted">${escapeHtml(file.type)}</td>
          <td><span class="status-badge ${file.status}">${statusLabel(file.status)}</span></td>
          <td>
            <button class="save-file-button" data-save="${escapeHtml(file.localName)}"
              ${file.status === "local" ? "" : "disabled"}
              title="${file.status === "local" ? "내 컴퓨터 다운로드 폴더에 저장" : "로컬에 없는 파일입니다. 먼저 동기화해 주세요."}">
              <span class="icon" data-icon="download"></span>저장
            </button>
          </td>
        </tr>
      `,
    )
    .join("");

  empty.hidden = rows.length > 0;
  installIcons(table);

  table.querySelectorAll("[data-save]").forEach((button) => {
    button.addEventListener("click", () => saveFilesToComputer(button.dataset.save));
  });

  const pickables = [...table.querySelectorAll("[data-pick]:not([disabled])")];
  const setPicked = (checkbox, picked) => {
    checkbox.checked = picked;
    if (picked) {
      state.selectedFiles.add(checkbox.dataset.pick);
    } else {
      state.selectedFiles.delete(checkbox.dataset.pick);
    }
  };

  pickables.forEach((checkbox, index) => {
    // Shift+클릭: 직전 클릭 위치부터 범위 선택 / 해제
    checkbox.addEventListener("click", (event) => {
      const picked = checkbox.checked; // 클릭 후 상태
      if (event.shiftKey && state.lastPickIndex !== null && state.lastPickIndex !== index) {
        const [from, to] = [Math.min(state.lastPickIndex, index), Math.max(state.lastPickIndex, index)];
        for (let i = from; i <= to; i += 1) setPicked(pickables[i], picked);
      } else {
        setPicked(checkbox, picked);
      }
      state.lastPickIndex = index;
      updateBulkSaveButton();
      syncSelectAllState();
    });
  });

  // Ctrl/Cmd+클릭(행 아무 곳): 해당 행 선택 토글
  table.querySelectorAll("tr").forEach((row) => {
    row.addEventListener("click", (event) => {
      if (!(event.ctrlKey || event.metaKey)) return;
      if (event.target.closest("[data-pick], [data-save]")) return;
      const checkbox = row.querySelector("[data-pick]:not([disabled])");
      if (!checkbox) return;
      event.preventDefault();
      setPicked(checkbox, !checkbox.checked);
      state.lastPickIndex = pickables.indexOf(checkbox);
      updateBulkSaveButton();
      syncSelectAllState();
    });
  });

  updateBulkSaveButton();
  syncSelectAllState();
}

function syncSelectAllState() {
  const selectAll = $("#selectAllFiles");
  if (!selectAll) return;
  const pickable = [...document.querySelectorAll('#filesTable [data-pick]:not([disabled])')];
  selectAll.checked = pickable.length > 0 && pickable.every((box) => box.checked);
}

/* ===== 작업/로그 ===== */
function renderTask(task) {
  state.task = task;
  const logBox = $("#logBox");
  const logs = task.logs || [];
  const labels = {
    sync: "동기화",
    verify: "검증",
    deadlines: "마감 새로고침",
    emails: "메일 새로고침",
    "google-oauth": "Google OAuth",
  };
  const taskLabel = labels[task.kind] || "작업";
  const runButton = $("#runButton");
  const verifyButton = $("#verifyButton");
  const refreshButton = $("#refreshDeadlinesButton");
  if (task.running) {
    runButton.innerHTML = '<span class="icon" data-icon="x"></span>작업 중지';
    runButton.classList.remove("primary");
    runButton.classList.add("danger");
    verifyButton.disabled = true;
    refreshButton.disabled = true;
  } else {
    runButton.innerHTML = '<span class="icon" data-icon="sync"></span>지금 동기화';
    runButton.classList.add("primary");
    runButton.classList.remove("danger");
    verifyButton.disabled = false;
    refreshButton.disabled = false;
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

/* ===== 데이터 로드 ===== */
function renderAll() {
  renderStatus();
  renderUpcoming();
  renderEvents();
  renderDeadlineFilters();
  renderDeadlines();
  renderEmails();
  renderCalendar();
  renderCourses();
  renderCourseFilter();
  renderFiles();
}

/* ===== 캘린더 화면 ===== */
function calendarItems() {
  // 과제 마감 + 메일 이벤트(eventDate) 합치기
  const items = [];
  (state.deadlines.items || []).forEach((d) => {
    const due = parseDue(d);
    if (!due) return;
    items.push({
      date: due,
      title: d.name,
      sub: d.courseLabel || d.course,
      kind: isSubmitted(d) ? "done" : "deadline",
    });
  });
  (state.emails.emails || []).forEach((m) => {
    if (!m.eventDate) return;
    const dt = new Date(m.eventDate);
    if (Number.isNaN(dt.getTime())) return;
    items.push({ date: dt, title: m.summary || m.subject, sub: m.fromName || m.fromEmail, kind: "event", mailId: m.id });
  });
  return items;
}

function renderCalendar() {
  const grid = $("#calendarGrid");
  if (!grid) return;
  if (!state.calMonth) {
    const now = new Date();
    state.calMonth = { y: now.getFullYear(), m: now.getMonth() };
  }
  const { y, m } = state.calMonth;
  $("#calendarTitle").textContent = `${y}년 ${m + 1}월`;

  const items = calendarItems();
  const byDay = {};
  items.forEach((it) => {
    if (it.date.getFullYear() === y && it.date.getMonth() === m) {
      const d = it.date.getDate();
      (byDay[d] = byDay[d] || []).push(it);
    }
  });

  const first = new Date(y, m, 1);
  const startDow = first.getDay();
  const daysInMonth = new Date(y, m + 1, 0).getDate();
  const today = new Date();
  const isToday = (d) => today.getFullYear() === y && today.getMonth() === m && today.getDate() === d;

  const weekdays = ["일", "월", "화", "수", "목", "금", "토"];
  let html = weekdays.map((w) => `<div class="cal-weekday">${w}</div>`).join("");
  for (let i = 0; i < startDow; i += 1) html += `<div class="cal-cell empty"></div>`;
  // 삼성 캘린더처럼 칸 안에 일정 제목을 간략히 표시 (넘치면 +N)
  const MAX_CHIPS = 3;
  for (let d = 1; d <= daysInMonth; d += 1) {
    const dayItems = byDay[d] || [];
    const chips = dayItems
      .slice(0, MAX_CHIPS)
      .map(
        (it) =>
          `<span class="cal-chip cal-${it.kind}" title="${escapeHtml(it.title || "")}">${escapeHtml(
            shortText(it.title || "", 14),
          )}</span>`,
      )
      .join("");
    const more =
      dayItems.length > MAX_CHIPS ? `<span class="cal-more">+${dayItems.length - MAX_CHIPS}</span>` : "";
    html += `
      <div class="cal-cell ${isToday(d) ? "today" : ""} ${state.calSelected === d ? "selected" : ""}" data-day="${d}">
        <span class="cal-daynum">${d}</span>
        <span class="cal-chips">${chips}${more}</span>
      </div>`;
  }
  grid.innerHTML = html;
  installIcons(grid);

  // 선택된 날짜(없으면 오늘 또는 첫 일정일) 상세 목록
  renderCalendarDayList(byDay);
}

function renderCalendarDayList(byDay) {
  const wrap = $("#calendarDayList");
  const day = state.calSelected;
  if (!day || !byDay[day]) {
    // 이번 달 전체 일정 요약
    const all = Object.entries(byDay)
      .sort((a, b) => Number(a[0]) - Number(b[0]))
      .flatMap(([d, arr]) => arr.map((it) => ({ ...it, d })));
    wrap.innerHTML = all.length
      ? `<h3>이번 달 일정 ${all.length}건</h3>` +
        all
          .map(
            (it) => `
        <div class="cal-item" ${it.mailId ? `data-mailid="${it.mailId}"` : ""}>
          <span class="cal-item-date">${it.date.getMonth() + 1}/${it.date.getDate()} ${String(it.date.getHours()).padStart(2, "0")}:${String(it.date.getMinutes()).padStart(2, "0")}</span>
          <span class="dot cal-${it.kind}"></span>
          <div class="cal-item-main"><strong>${escapeHtml(shortText(it.title, 46))}</strong><span>${escapeHtml(shortText(it.sub || "", 34))}</span></div>
        </div>`,
          )
          .join("")
      : `<p class="cal-empty">이번 달 일정이 없습니다.</p>`;
    return;
  }
  const arr = byDay[day].sort((a, b) => a.date - b.date);
  wrap.innerHTML =
    `<h3>${state.calMonth.m + 1}월 ${day}일 · ${arr.length}건</h3>` +
    arr
      .map(
        (it) => `
      <div class="cal-item" ${it.mailId ? `data-mailid="${it.mailId}"` : ""}>
        <span class="cal-item-date">${String(it.date.getHours()).padStart(2, "0")}:${String(it.date.getMinutes()).padStart(2, "0")}</span>
        <span class="dot cal-${it.kind}"></span>
        <div class="cal-item-main"><strong>${escapeHtml(shortText(it.title, 46))}</strong><span>${escapeHtml(shortText(it.sub || "", 34))}</span></div>
      </div>`,
      )
      .join("");
}

async function refreshAll() {
  try {
    const [status, files, task, deadlines, selection, emails, config] = await Promise.all([
      api("/api/status"),
      api("/api/files"),
      api("/api/task"),
      api("/api/deadlines"),
      api("/api/selection"),
      api("/api/emails"),
      api("/api/config"),
    ]);
    state.status = status;
    state.files = files.files || [];
    state.deadlines = deadlines;
    state.selection = selection.courses ? selection : { courses: {} };
    if (!Array.isArray(state.selection.hidden)) state.selection.hidden = [];
    state.emails = emails.emails ? emails : { emails: [], briefing: "", interests: "", updatedAt: null };
    state.config = config;
    renderAll();
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

/* ===== 관심사 선택 (설정) ===== */
const TRACK_OPTIONS = [
  "물리학", "화학", "생명과학", "뇌과학", "컴퓨터·AI", "전기·전자",
  "로봇·기계", "신소재", "에너지공학", "의생명공학", "뉴바이올로지", "수학·데이터",
];
const ACTIVITY_OPTIONS = [
  "대학원·연구", "취업·인턴", "창업", "장학금", "교환학생·해외",
  "세미나·특강", "공모전·대회", "학생회·자치", "동아리", "음악·공연", "운동·스포츠", "봉사",
];

function renderInterestChips() {
  const render = (options) =>
    options
      .map(
        (tag) => `
          <button type="button" class="interest-chip ${state.interestTags.has(tag) ? "active" : ""}"
            data-tag="${escapeHtml(tag)}">${escapeHtml(tag)}</button>
        `,
      )
      .join("");
  $("#trackChips").innerHTML = render(TRACK_OPTIONS);
  $("#activityChips").innerHTML = render(ACTIVITY_OPTIONS);
}

function bindInterestChips() {
  const toggle = (event) => {
    const chip = event.target.closest("[data-tag]");
    if (!chip) return;
    const tag = chip.dataset.tag;
    if (state.interestTags.has(tag)) {
      state.interestTags.delete(tag);
    } else {
      state.interestTags.add(tag);
    }
    renderInterestChips();
  };
  $("#trackChips").addEventListener("click", toggle);
  $("#activityChips").addEventListener("click", toggle);
}

function renderSecretBadges() {
  const config = state.config || {};
  $("#geminiSavedBadge").hidden = !config.hasGeminiKey;
  $("#clearGeminiKey").hidden = !config.hasGeminiKey;
  $("#emailPwSavedBadge").hidden = !config.hasEmailPassword;
  $("#schoolPwSavedBadge").hidden = !config.hasSchoolEmailPassword;
}

function openSettings() {
  switchView("settings");
  document.querySelectorAll(".nav-item").forEach((item) => {
    item.classList.toggle("active", item.dataset.view === "settings");
  });
}

async function populateSettings() {
  try {
    await loadConfig();
  } catch (error) {
    showToast(error.message);
  }
  const form = $("#configForm");
  form.elements.geminiKey.value = "";
  form.elements.geminiKey.type = "password";
  form.elements.lmsPassword.value = "";
  form.elements.emailPassword.value = "";
  form.elements.schoolEmailPassword.value = "";
  state.interestTags = new Set(state.config?.interestTags || []);
  form.elements.interestsCustom.value = state.config?.interestsCustom || "";
  form.elements.hidePastEmails.checked = Boolean(state.config?.hidePastEmails);
  // 구글 캘린더 동기화 (체크박스라 value 대입으로는 반영되지 않음)
  form.elements.gcalSyncEnabled.checked = Boolean(state.config?.gcalSyncEnabled);
  form.elements.gcalCalendarName.value = state.config?.gcalCalendarName || "DGIST 메일 일정";
  renderGcalStatus();
  renderInterestChips();
  renderSecretBadges();
  renderGoogleSection();
  // 앱 버전 표시 (업데이트 확인 전 현재 버전만)
  api("/api/update/check")
    .then((d) => {
      $("#appVersion").textContent = `v${d.current || "?"}`;
    })
    .catch(() => {});
}

/* ===== 메일 pane 전환 (목록/읽기/작성) ===== */
function showMailPane(pane) {
  state.mailPane = pane;
  $("#mailListPane").hidden = pane !== "list";
  $("#mailReadPane").hidden = pane !== "read";
  $("#mailComposePane").hidden = pane !== "compose";
}

/* ===== 이벤트 바인딩 ===== */
function bindEvents() {
  $("#searchInput").addEventListener("input", (event) => {
    state.query = event.target.value;
    renderUpcoming();
    renderDeadlines();
    renderEmails();
    renderCourses();
    renderFiles();
  });

  $("#refreshEmailsButton").addEventListener("click", () =>
    startRun("/api/refresh-emails", "메일 새로고침"),
  );

  $("#emailSearchInput").addEventListener("input", (event) => {
    state.emailQuery = event.target.value;
    renderEmails();
  });

  $("#emailFilterChips").addEventListener("click", (event) => {
    const chip = event.target.closest("[data-filter]");
    if (!chip) return;
    state.emailFilter = chip.dataset.filter;
    renderEmails();
  });

  // 캘린더
  $("#calPrevButton").addEventListener("click", () => {
    const { y, m } = state.calMonth;
    state.calMonth = m === 0 ? { y: y - 1, m: 11 } : { y, m: m - 1 };
    state.calSelected = null;
    renderCalendar();
  });
  $("#calNextButton").addEventListener("click", () => {
    const { y, m } = state.calMonth;
    state.calMonth = m === 11 ? { y: y + 1, m: 0 } : { y, m: m + 1 };
    state.calSelected = null;
    renderCalendar();
  });
  $("#calTodayButton").addEventListener("click", () => {
    const now = new Date();
    state.calMonth = { y: now.getFullYear(), m: now.getMonth() };
    state.calSelected = now.getDate();
    renderCalendar();
  });
  $("#calendarGrid").addEventListener("click", (event) => {
    const cell = event.target.closest(".cal-cell[data-day]");
    if (!cell) return;
    const day = Number(cell.dataset.day);
    state.calSelected = state.calSelected === day ? null : day;
    renderCalendar();
  });
  $("#calendarDayList").addEventListener("click", (event) => {
    const item = event.target.closest("[data-mailid]");
    if (!item) return;
    const mail = state.emails.emails.find((m) => String(m.id) === item.dataset.mailid);
    if (mail) {
      switchView("emails");
      openEmailDetail(mail);
    }
  });
  $("#gcalConnectButton").addEventListener("click", async () => {
    if (state.status?.mode === "multi-user") {
      window.open("/api/deadlines.ics", "_blank");
      return;
    }
    try {
      const data = await api("/api/export-ics", { method: "POST", body: "{}" });
      showToast((data.message || "캘린더 파일을 저장했습니다.") + " 구글 캘린더 → 가져오기로 등록하세요.");
    } catch (error) {
      showToast(error.message);
    }
  });

  // 폴더 네비게이션
  $("#mailFolders").addEventListener("click", (event) => {
    const btn = event.target.closest("[data-folder]");
    if (!btn) return;
    // 작성 중이던 내용이 있으면 확인 후 이동
    if (
      state.mailPane === "compose" &&
      composeHasContent() &&
      !window.confirm("작성 중인 메일이 있습니다. 저장하지 않고 이동할까요?")
    ) {
      return;
    }
    state.emailFolder = btn.dataset.folder;
    state.emailFilter = "";
    state.attachments = [];
    // 작성/읽기 pane에 가려지지 않도록 목록으로 복귀 + 사이드바 활성 항목 동기화
    switchView("emails");
    $("#mailScroll")?.scrollTo?.(0, 0);
    renderEmails();
  });

  // 카드/리스트 클릭 → 읽음/삭제 액션 또는 전문 보기
  const handleMailClick = (event) => {
    const item = event.target.closest(".news-card, .email-list-row");
    if (!item) return;
    const mail = state.emails.emails.find((m) => String(m.id) === item.dataset.mailId);
    if (!mail) return;
    const actBtn = event.target.closest("[data-act]");
    if (actBtn) {
      event.stopPropagation();
      if (actBtn.dataset.act === "read") {
        setEmailRead(mail, mail.unread); // 안읽음이면 읽음으로, 읽음이면 안읽음으로
      } else if (actBtn.dataset.act === "delete") {
        deleteEmail(mail);
      }
      return;
    }
    openEmailDetail(mail);
  };
  $("#newsGrid").addEventListener("click", handleMailClick);
  $("#newsFeatured").addEventListener("click", handleMailClick);
  $("#markAllReadButton").addEventListener("click", markAllRead);

  // 읽기 pane 버튼
  $("#readBackButton").addEventListener("click", () => showMailPane("list"));
  $("#readReplyButton").addEventListener("click", replyToCurrentEmail);
  $("#readMarkButton").addEventListener("click", () => {
    const mail = state.replyContext;
    if (mail) {
      setEmailRead(mail, mail.unread);
      showMailPane("list");
    }
  });
  $("#readDeleteButton").addEventListener("click", () => {
    const mail = state.replyContext;
    if (mail && window.confirm("이 메일을 삭제할까요?")) {
      deleteEmail(mail);
      showMailPane("list");
    }
  });

  // 정렬 / 보기 방식
  $("#emailSortSelect").addEventListener("change", (event) => {
    state.emailSort = event.target.value;
    renderEmails();
  });
  document.querySelectorAll(".view-toggle-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      state.emailView = btn.dataset.viewmode;
      document.querySelectorAll(".view-toggle-btn").forEach((b) => b.classList.toggle("active", b === btn));
      renderEmails();
    });
  });

  // 메일 쓰기 / 발송
  $("#composeButton").addEventListener("click", () => switchView("compose"));
  $("#closeComposeDialog").addEventListener("click", closeCompose);
  $("#cancelComposeButton").addEventListener("click", closeCompose);
  $("#toggleCcBcc").addEventListener("click", () => {
    const cc = $("#ccField");
    const bcc = $("#bccField");
    const show = cc.hidden;
    cc.hidden = !show;
    bcc.hidden = !show;
    if (show) $("#composeForm").elements.cc.focus();
  });

  // 첨부파일
  $("#attachButton").addEventListener("click", () => $("#attachInput").click());
  $("#attachInput").addEventListener("change", async (event) => {
    const files = [...event.target.files];
    for (const file of files) {
      if (file.size > 20 * 1024 * 1024) {
        showToast(`${file.name}은(는) 20MB를 넘어 제외됐습니다.`);
        continue;
      }
      const content = await fileToBase64(file);
      state.attachments.push({ filename: file.name, size: file.size, content });
    }
    event.target.value = "";
    renderAttachments();
  });
  $("#composeAttachments").addEventListener("click", (event) => {
    const rm = event.target.closest(".attach-remove");
    if (rm) {
      state.attachments.splice(Number(rm.dataset.idx), 1);
      renderAttachments();
    }
  });

  // Google Drive에서 첨부 가져오기
  $("#driveImportButton").addEventListener("click", importFromDrive);

  setupAutocomplete();
  $("#composeForm").addEventListener("submit", async (event) => {
    event.preventDefault();
    const form = event.currentTarget;
    const payload = {
      to: form.elements.to.value.trim(),
      cc: form.elements.cc.value.trim(),
      bcc: form.elements.bcc.value.trim(),
      subject: form.elements.subject.value,
      body: form.elements.body.value,
      html: $("#htmlModeToggle").checked,
      inReplyTo: form.dataset.inReplyTo || "",
      references: form.dataset.references || "",
      attachments: (state.attachments || []).map((a) => ({ filename: a.filename, content: a.content })),
    };
    if (!payload.to) {
      showToast("받는 사람 주소를 입력해 주세요.");
      return;
    }
    const sendBtn = $("#sendMailButton");
    sendBtn.disabled = true;
    try {
      const data = await api("/api/send-email", { method: "POST", body: JSON.stringify(payload) });
      showToast(data.message || "메일을 보냈습니다.");
      closeCompose();
    } catch (error) {
      showToast(error.message);
    } finally {
      sendBtn.disabled = false;
    }
  });

  // 과목 변경 확인
  $("#acknowledgeCoursesButton").addEventListener("click", async () => {
    try {
      await api("/api/acknowledge-courses", { method: "POST", body: "{}" });
      showToast("과목 변경을 확인했습니다.");
      await refreshAll();
    } catch (error) {
      showToast(error.message);
    }
  });
  $("#courseChangeSyncButton").addEventListener("click", () => {
    const confirmed = window.confirm("전체 동기화를 시작할까요? 바뀐 과목의 자료를 처음부터 다시 검사합니다.");
    if (confirmed) startRun("/api/run", "전체 동기화", { confirm: true, mode: "full" });
  });

  $("#pickFolderButton").addEventListener("click", async () => {
    try {
      const data = await api("/api/pick-folder", { method: "POST", body: "{}" });
      if (data.path) {
        $("#configForm").elements.localSavePath.value = data.path;
        showToast("폴더를 선택했습니다. 설정 저장을 눌러 적용하세요.");
      } else {
        showToast(data.message || "폴더 선택이 취소되었습니다.");
      }
    } catch (error) {
      showToast(error.message);
    }
  });

  $("#courseFilter").addEventListener("change", (event) => {
    state.course = event.target.value;
    renderFiles();
  });

  $("#statusFilter").addEventListener("change", (event) => {
    state.fileStatus = event.target.value;
    renderFiles();
  });

  $("#deadlineCourseFilter").addEventListener("change", (event) => {
    state.deadlineCourse = event.target.value;
    renderDeadlines();
  });

  $("#deadlineStatusFilter").addEventListener("change", (event) => {
    state.deadlineStatus = event.target.value;
    renderDeadlines();
  });

  $("#runButton").addEventListener("click", () => {
    if (state.task?.running) {
      startRun("/api/stop", "중지");
      return;
    }
    const confirmed = window.confirm(
      "빠른 동기화를 시작할까요? 마지막 동기화 이후 변경된 자료만 빠르게 확인합니다.\n(전체 검사는 설정 → 고급 설정에서 실행할 수 있습니다.)",
    );
    if (confirmed) {
      startRun("/api/run", "빠른 동기화", { confirm: true, mode: "fast" });
    }
  });

  $("#selectAllFiles").addEventListener("change", (event) => {
    const pickable = document.querySelectorAll('#filesTable [data-pick]:not([disabled])');
    pickable.forEach((box) => {
      box.checked = event.target.checked;
      if (box.checked) {
        state.selectedFiles.add(box.dataset.pick);
      } else {
        state.selectedFiles.delete(box.dataset.pick);
      }
    });
    updateBulkSaveButton();
  });

  $("#bulkSaveButton").addEventListener("click", () => {
    const names = [...state.selectedFiles];
    if (!names.length) return;
    saveFilesToComputer(names);
  });

  $("#fullSyncButton").addEventListener("click", () => {
    const confirmed = window.confirm(
      "전체 동기화를 시작할까요? 모든 과목의 자료를 처음부터 다시 검사하므로 수 분 정도 걸립니다.",
    );
    if (confirmed) {
      startRun("/api/run", "전체 동기화", { confirm: true, mode: "full" });
    }
  });

  $("#verifyButton").addEventListener("click", () => startRun("/api/verify", "검증"));
  $("#refreshDeadlinesButton").addEventListener("click", () =>
    startRun("/api/refresh-deadlines", "마감 새로고침"),
  );

  $("#googleLoginButton").addEventListener("click", () => {
    const oauth = state.status?.googleOAuth || {};
    if (!oauth.credentialsExists) {
      $("#googleHelpDialog").showModal();
      showToast("credentials.json을 먼저 준비해 주세요.");
      return;
    }
    api("/api/google/connect", {
      method: "POST",
      body: JSON.stringify({ openBrowser: true }),
    })
      .then((data) => {
        if (data.openedInBrowser) {
          showToast("브라우저가 열렸습니다. 구글 계정으로 로그인해 주세요.");
          return;
        }
        if (data.authUrl) {
          if (state.status?.mode === "multi-user") {
            window.location.href = data.authUrl;
          } else {
            window.open(data.authUrl, "_blank");
            showToast("새 창에서 구글 계정으로 로그인해 주세요.");
          }
          return;
        }
        showToast(data.message || "구글 로그인을 시작합니다.");
      })
      .catch((error) => showToast(error.message));
  });

  $("#disconnectGoogleButton").addEventListener("click", () => {
    const confirmed = window.confirm("이 컴퓨터에 저장된 구글 로그인 정보를 제거할까요?");
    if (confirmed) {
      startRun("/api/google/disconnect", "구글 로그인 해제");
    }
  });

  $("#toggleGeminiKey").addEventListener("click", () => {
    const input = $("#configForm").elements.geminiKey;
    input.type = input.type === "password" ? "text" : "password";
  });

  $("#clearGeminiKey").addEventListener("click", async () => {
    const confirmed = window.confirm("저장된 Gemini API 키를 삭제할까요? AI 요약 기능이 중지됩니다.");
    if (!confirmed) return;
    try {
      await api("/api/config", {
        method: "POST",
        body: JSON.stringify({ clearGeminiKey: true }),
      });
      showToast("Gemini API 키를 삭제했습니다.");
      await refreshAll();
      await loadConfig();
      renderSecretBadges();
    } catch (error) {
      showToast(error.message);
    }
  });

  $("#openSettingsFromRail")?.addEventListener("click", openSettings);

  // 구글 캘린더 지금 동기화
  $("#gcalSyncNowButton")?.addEventListener("click", async (event) => {
    const btn = event.currentTarget;
    btn.disabled = true;
    renderGcalStatus("동기화 중…");
    try {
      const data = await api("/api/gcal/sync", { method: "POST", body: JSON.stringify({}) });
      showToast(`'${data.calendar}' 캘린더에 반영했습니다. ${data.message || ""}`.trim());
      renderGcalStatus(`마지막 동기화: ${data.message || "완료"}`);
    } catch (error) {
      showToast(error.message);
      renderGcalStatus(error.message);
    } finally {
      btn.disabled = false;
    }
  });

  // 과목 편집 모드 토글 / 숨긴 과목 복원
  $("#courseEditButton")?.addEventListener("click", () => {
    state.courseEditMode = !state.courseEditMode;
    renderCourses();
  });
  $("#restoreCoursesButton")?.addEventListener("click", async () => {
    const count = (state.selection.hidden || []).length;
    if (!count) return;
    state.selection.hidden = [];
    try {
      await api("/api/selection", { method: "POST", body: JSON.stringify(state.selection) });
      showToast(`숨긴 과목 ${count}개를 복원했습니다.`);
      renderCourses();
    } catch (error) {
      showToast(error.message);
    }
  });

  document.querySelectorAll(".theme-opt").forEach((btn) => {
    btn.addEventListener("click", () => applyTheme(btn.dataset.theme));
  });

  $("#exportIcsButton").addEventListener("click", async () => {
    if (!state.deadlines.items.length) {
      showToast("내보낼 마감 정보가 없습니다. 먼저 '마감 새로고침'을 실행해 주세요.");
      return;
    }
    if (state.status?.mode === "multi-user") {
      window.open("/api/deadlines.ics", "_blank");
      return;
    }
    try {
      const data = await api("/api/export-ics", { method: "POST", body: "{}" });
      showToast(data.message || "캘린더 파일을 저장했습니다.");
    } catch (error) {
      showToast(error.message);
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

  // 앱 업데이트
  $("#checkUpdateButton").addEventListener("click", async () => {
    $("#updateStatus").textContent = "GitHub에서 확인 중…";
    try {
      const d = await api("/api/update/check");
      $("#appVersion").textContent = `v${d.current}`;
      if (d.updateAvailable) {
        $("#updateStatus").textContent = `새 버전 v${d.latest}이(가) 있습니다.`;
        $("#applyUpdateButton").hidden = false;
      } else if (d.ok) {
        $("#updateStatus").textContent = `최신 버전입니다 (v${d.current}).`;
        $("#applyUpdateButton").hidden = true;
      } else {
        $("#updateStatus").textContent = d.message || "확인 실패";
      }
    } catch (error) {
      $("#updateStatus").textContent = error.message;
    }
  });
  $("#applyUpdateButton").addEventListener("click", async () => {
    if (!window.confirm("최신 버전으로 업데이트할까요? 완료 후 앱을 재시작해야 합니다.")) return;
    $("#updateStatus").textContent = "업데이트 내려받는 중…";
    try {
      const d = await api("/api/update/apply", { method: "POST", body: "{}" });
      $("#updateStatus").textContent = d.message || "업데이트 완료";
      $("#appVersion").textContent = `v${d.version}`;
      $("#applyUpdateButton").hidden = true;
      showToast("업데이트 완료! 앱을 껐다 켜면 새 버전이 적용됩니다.");
    } catch (error) {
      $("#updateStatus").textContent = error.message;
    }
  });

  $("#configForm").addEventListener("submit", async (event) => {
    event.preventDefault();
    const formData = new FormData(event.currentTarget);
    const payload = Object.fromEntries(formData.entries());
    payload.interestTags = [...state.interestTags];
    payload.hidePastEmails = event.currentTarget.elements.hidePastEmails.checked;
    payload.gcalSyncEnabled = event.currentTarget.elements.gcalSyncEnabled.checked;
    try {
      await api("/api/config", { method: "POST", body: JSON.stringify(payload) });
      showToast("설정을 저장했습니다.");
      await refreshAll();
      switchView("dashboard");
    } catch (error) {
      showToast(error.message);
    }
  });

  document.querySelectorAll(".nav-item").forEach((button) => {
    button.addEventListener("click", () => switchView(button.dataset.view));
  });

  document.querySelectorAll("[data-goto]").forEach((node) => {
    node.addEventListener("click", () => switchView(node.dataset.goto));
  });
}

/* ===== 테마 (클로드 기본 / 화이트 / 다크) ===== */
const THEMES = [
  { key: "claude", label: "클로드", icon: "sparkle" },
  { key: "light", label: "화이트", icon: "sun" },
  { key: "dark", label: "다크", icon: "moon" },
];

function applyTheme(theme) {
  // claude 기본은 :root라 data-theme를 비움
  if (theme === "claude") {
    document.documentElement.removeAttribute("data-theme");
  } else {
    document.documentElement.dataset.theme = theme;
  }
  try {
    localStorage.setItem("autosaver-theme", theme);
  } catch (error) {
    /* localStorage 사용 불가 환경 무시 */
  }
  // 3분할 테마 선택기: 현재 테마 버튼만 활성 표시
  document.querySelectorAll(".theme-opt").forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.theme === theme);
  });
}

function currentTheme() {
  return document.documentElement.getAttribute("data-theme") || "claude";
}

function initTheme() {
  let saved = "claude";
  try {
    saved = localStorage.getItem("autosaver-theme") || "claude";
  } catch (error) {
    /* 무시 */
  }
  if (!THEMES.some((t) => t.key === saved)) saved = "claude";
  applyTheme(saved);
}

/* ===== 구글 캘린더 동기화 상태 ===== */
function renderGcalStatus(message) {
  const el = $("#gcalStatusText");
  if (!el) return;
  if (message) {
    el.textContent = message;
    return;
  }
  const oauth = state.status?.googleOAuth || {};
  if (!oauth.tokenExists) {
    el.textContent = "먼저 위에서 구글 계정을 연결해 주세요.";
  } else if (!oauth.calendarGranted) {
    el.textContent = "캘린더 권한이 없습니다. 구글 계정을 다시 연결하면 권한이 추가됩니다.";
  } else {
    el.textContent = "메일에서 찾은 일정을 구글 캘린더에 자동으로 등록합니다.";
  }
}

/* ===== 실행 로그 레일 접기/펼치기 ===== */
function applyRailCollapsed(collapsed) {
  const workspace = document.querySelector(".workspace");
  if (!workspace) return;
  workspace.classList.toggle("rail-collapsed", collapsed);
  const toggle = $("#railToggle");
  if (toggle) {
    toggle.setAttribute("aria-expanded", String(!collapsed));
    toggle.title = collapsed ? "실행 로그 펼치기" : "실행 로그 접기";
  }
  try {
    localStorage.setItem("autosaver-rail-collapsed", collapsed ? "1" : "0");
  } catch (error) {
    /* localStorage 사용 불가 환경 무시 */
  }
}

function initRail() {
  let collapsed = false;
  try {
    collapsed = localStorage.getItem("autosaver-rail-collapsed") === "1";
  } catch (error) {
    /* 무시 */
  }
  applyRailCollapsed(collapsed);
  $("#railToggle")?.addEventListener("click", () => {
    const now = document.querySelector(".workspace")?.classList.contains("rail-collapsed");
    applyRailCollapsed(!now);
  });
}

function setHeroGreeting() {
  const hour = new Date().getHours();
  const greeting =
    hour < 6 ? "늦은 밤까지 수고가 많아요 🌙" : hour < 12 ? "좋은 아침이에요 ☀️" : hour < 18 ? "좋은 오후예요 👋" : "좋은 저녁이에요 🌆";
  $("#heroTitle").textContent = greeting;
}

installIcons();
bindEvents();
bindInterestChips();
initTheme();
initRail();
setHeroGreeting();
refreshAll();
window.setInterval(refreshAll, 3500);
