const form = document.querySelector("#calendar-form");
const taskList = document.querySelector("#task-list");
const addTaskButton = document.querySelector("#add-task");
const scanGmailButton = document.querySelector("#scan-gmail");
const saveButton = document.querySelector("#save-button");
const dayTabs = document.querySelector("#day-tabs");
const dayView = document.querySelector("#day-view");
const status = document.querySelector("#calendar-status");
let currentPlanExists = false;

const escapeHtml = (value) => String(value).replace(/[&<>'"]/g, (character) => ({
  "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#039;", '"': "&quot;"
}[character]));

function addTaskRow(values = {}) {
  const row = document.createElement("article");
  row.className = "task-row";
  row.innerHTML = `<div class="task-row-top"><span class="task-number">Công việc</span><button type="button" class="remove-task">Xóa</button></div>
    <label>Tên công việc<input class="task-title" value="${escapeHtml(values.title || "")}" placeholder="Ví dụ: Học tiếng Anh" /></label>
    <div class="task-fields"><label>Thời lượng (phút)<input class="task-minutes" type="number" min="5" max="480" value="${values.estimated_minutes || 30}" /></label>
    <label>Kiểu deadline<select class="deadline-mode"><option value="none">Không đặt</option><option value="daily">Hằng ngày</option><option value="specific">Thời gian cụ thể</option></select></label>
    <label class="specific-deadline hidden">Ngày và giờ deadline<input class="deadline-at" type="datetime-local" /></label></div>`;
  row.querySelector(".deadline-mode").value = values.deadline_mode || "none";
  row.querySelector(".deadline-at").value = values.deadline_at ? String(values.deadline_at).slice(0, 16) : "";
  const mode = row.querySelector(".deadline-mode");
  const specific = row.querySelector(".specific-deadline");
  mode.addEventListener("change", () => specific.classList.toggle("hidden", mode.value !== "specific"));
  specific.classList.toggle("hidden", mode.value !== "specific");
  row.querySelector(".remove-task").addEventListener("click", () => {
    if (taskList.children.length > 1) row.remove();
  });
  taskList.appendChild(row);
}

function collectTasks() {
  return [...document.querySelectorAll(".task-row")].map((row) => {
    const title = row.querySelector(".task-title").value.trim();
    const deadlineMode = row.querySelector(".deadline-mode").value;
    const deadlineAt = row.querySelector(".deadline-at").value || null;
    if (!title && deadlineMode === "none" && !deadlineAt) return null;
    return {
      title,
      estimated_minutes: Number(row.querySelector(".task-minutes").value),
      deadline_mode: deadlineMode,
      deadline_at: deadlineAt,
    };
  }).filter(Boolean);
}

function periodLabel(period) {
  return { morning: "Sáng", afternoon: "Chiều", evening: "Tối", night: "Đêm" }[period] || period;
}

function renderDay(data, selectedDate) {
  const blocks = data.schedule.filter((item) => item.date === selectedDate);
  const groups = ["morning", "afternoon", "evening", "night"];
  dayView.innerHTML = `<div class="selected-day"><h3>${new Date(`${selectedDate}T12:00:00`).toLocaleDateString("vi-VN", { weekday: "long", day: "numeric", month: "long" })}</h3></div>${groups.map((period) => {
    const periodBlocks = blocks.filter((item) => item.period === period);
    if (!periodBlocks.length) return "";
    return `<section class="period"><h4>${periodLabel(period)}</h4><div class="block-list">${periodBlocks.map((block) => `<div class="time-block ${block.block_type}"><time>${block.start_time}<br /><span>${block.end_time}</span></time><div><strong>${escapeHtml(block.task_title)}</strong><small>${block.minutes} phút${block.block_type === "task" ? " · Công việc" : ""}</small></div></div>`).join("")}</div></section>`;
  }).join("")}`;
}

function renderCalendar(data) {
  const displayName = data.plan_input?.display_name || document.querySelector("#display-name").value.trim() || data.plan_input?.user_id || "";
  const userName = document.querySelector("#calendar-user-name");
  if (userName) userName.textContent = displayName ? `Của ${displayName}` : "";
  if (data.plan_input?.display_name && !document.querySelector("#display-name").value.trim()) {
    document.querySelector("#display-name").value = data.plan_input.display_name;
  }
  const dates = [...new Set(data.schedule.map((item) => item.date))].sort();
  dayTabs.innerHTML = dates.map((date, index) => `<button type="button" class="day-tab ${index === 0 ? "active" : ""}" data-date="${date}"><strong>${new Date(`${date}T12:00:00`).toLocaleDateString("vi-VN", { weekday: "short" })}</strong><span>${new Date(`${date}T12:00:00`).getDate()}/${new Date(`${date}T12:00:00`).getMonth() + 1}</span></button>`).join("");
  dayTabs.querySelectorAll(".day-tab").forEach((tab) => tab.addEventListener("click", () => {
    dayTabs.querySelectorAll(".day-tab").forEach((item) => item.classList.remove("active"));
    tab.classList.add("active");
    renderDay(data, tab.dataset.date);
  }));
  if (dates.length) renderDay(data, dates[0]);
  status.textContent = "Đã lưu";
  currentPlanExists = true;
  updateSaveButtonMode();
}

function resetTaskInputs() {
  taskList.innerHTML = "";
  addTaskRow();
  document.querySelector("#planning-notes").value = "";
}

async function loadCalendar() {
  const userId = document.querySelector("#user-id").value.trim();
  if (!userId) return;
  try {
    const listResponse = await fetch(`/v1/plans?user_id=${encodeURIComponent(userId)}`);
    const plans = await listResponse.json();
    if (!plans.length) {
      currentPlanExists = false;
      updateSaveButtonMode();
      status.textContent = "Chưa có lịch cho mã người dùng này";
      dayTabs.innerHTML = "";
      dayView.innerHTML = `<div class="empty-calendar">Tạo lịch để xem các khối công việc, thời gian cá nhân và nghỉ ngơi.</div>`;
      const userName = document.querySelector("#calendar-user-name");
      if (userName) userName.textContent = "";
      return;
    }
    const response = await fetch(`/v1/plans/${encodeURIComponent(plans[0].plan_id)}?user_id=${encodeURIComponent(userId)}`);
    if (response.ok) renderCalendar(await response.json());
  } catch (_) { status.textContent = "Chưa tải được lịch đã lưu"; }
}

function updateSaveButtonMode() {
  saveButton.textContent = currentPlanExists ? "Chỉnh sửa lịch 14 ngày" : "Tạo lịch 14 ngày";
}

addTaskButton.addEventListener("click", () => addTaskRow());
addTaskRow();
loadCalendar();
document.querySelector("#user-id").addEventListener("change", loadCalendar);
document.querySelector("#user-id").addEventListener("blur", loadCalendar);

scanGmailButton.addEventListener("click", async () => {
  const userId = document.querySelector("#user-id").value.trim();
  if (!userId) { status.textContent = "Hãy nhập mã người dùng trước khi quét Gmail"; return; }
  scanGmailButton.disabled = true;
  scanGmailButton.textContent = "Đang quét Gmail…";
  status.textContent = "Đang đọc Gmail 3 ngày gần nhất";
  try {
    const response = await fetch("/v1/integrations/gmail/scan", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        user_id: userId,
        display_name: document.querySelector("#display-name").value.trim(),
        days: Number(document.querySelector("#gmail-days").value || 3),
        max_results: 50,
      }),
    });
    if (!response.ok) throw new Error("Không thể quét Gmail. Hãy kiểm tra OAuth Gmail và thử lại.");
    renderCalendar(await response.json());
    resetTaskInputs();
  } catch (error) {
    status.textContent = error.message;
  } finally {
    scanGmailButton.disabled = false;
    scanGmailButton.textContent = "Quét Gmail và cập nhật lịch";
  }
});

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const tasks = collectTasks();
  const planningNotes = document.querySelector("#planning-notes").value.trim();
  if (!tasks.length && planningNotes.length < 3) {
    status.textContent = "Hãy chọn deadline, thêm công việc hoặc nhập thông tin cập nhật lịch";
    return;
  }
  saveButton.disabled = true;
  saveButton.textContent = "AI đang cập nhật lịch…";
  try {
    const response = await fetch("/v1/workflow/plan", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        user_id: document.querySelector("#user-id").value.trim(),
        display_name: document.querySelector("#display-name").value.trim(),
        raw_input: tasks.map((task) => task.title).join(", ") || planningNotes,
        task_inputs: tasks,
        planning_notes: planningNotes,
        horizon_days: 14,
      }),
    });
    if (!response.ok) throw new Error("Không thể cập nhật lịch. Hãy kiểm tra cấu hình LLM và dữ liệu nhập.");
    renderCalendar(await response.json());
    resetTaskInputs();
  } catch (error) {
    status.textContent = error.message;
  } finally {
    saveButton.disabled = false;
    updateSaveButtonMode();
  }
});
