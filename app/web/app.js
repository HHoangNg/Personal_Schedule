const form = document.querySelector("#planner-form");
const button = document.querySelector("#submit-button");
const result = document.querySelector("#result");
const emptyState = document.querySelector("#empty-state");
const savedPlans = document.querySelector("#saved-plans");
const loadPlansButton = document.querySelector("#load-plans");
const taskList = document.querySelector("#task-list");
const addTaskButton = document.querySelector("#add-task");

const escapeHtml = (value) => String(value).replace(/[&<>'"]/g, (character) => ({
  "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#039;", '"': "&quot;"
}[character]));

function renderList(id, items) {
  document.querySelector(id).innerHTML = items.map((item) => `<li>${item}</li>`).join("");
}

function addTaskRow(values = {}) {
  const row = document.createElement("div");
  row.className = "task-entry";
  row.innerHTML = `<div class="task-entry-header"><strong>Công việc</strong><button class="remove-task secondary" type="button">Xóa</button></div>
    <label>Tên công việc<input class="task-title" required value="${escapeHtml(values.title || "")}" placeholder="Ví dụ: Học tiếng Anh" /></label>
    <div class="form-grid"><label>Loại công việc<select class="task-type"><option value="general">Chung</option><option value="learning">Học tập</option><option value="housework">Việc nhà</option><option value="cooking">Nấu ăn</option><option value="health">Sức khỏe</option></select></label>
    <label>Ưu tiên<select class="task-priority"><option value="medium">Trung bình</option><option value="high">Cao</option><option value="low">Thấp</option></select></label></div>
    <div class="form-grid"><label>Thời lượng (phút)<input class="task-minutes" type="number" min="5" max="480" value="${values.estimated_minutes || 30}" /></label>
    <label>Kiểu deadline<select class="task-deadline-mode"><option value="none">Không đặt</option><option value="daily">Hằng ngày</option><option value="specific">Thời gian cụ thể</option></select></label></div>
    <label class="task-deadline-label hidden">Deadline cụ thể<input class="task-deadline-at" type="datetime-local" /></label>`;
  row.querySelector(".task-type").value = values.type || "general";
  row.querySelector(".task-priority").value = values.priority || "medium";
  row.querySelector(".task-deadline-mode").value = values.deadline_mode || "none";
  row.querySelector(".task-deadline-at").value = values.deadline_at ? String(values.deadline_at).slice(0, 16) : "";
  const mode = row.querySelector(".task-deadline-mode");
  const deadlineLabel = row.querySelector(".task-deadline-label");
  mode.addEventListener("change", () => deadlineLabel.classList.toggle("hidden", mode.value !== "specific"));
  deadlineLabel.classList.toggle("hidden", mode.value !== "specific");
  row.querySelector(".remove-task").addEventListener("click", () => {
    if (taskList.children.length > 1) row.remove();
  });
  taskList.appendChild(row);
}

function collectTaskInputs() {
  return [...document.querySelectorAll(".task-entry")].map((row) => ({
    title: row.querySelector(".task-title").value.trim(),
    type: row.querySelector(".task-type").value,
    priority: row.querySelector(".task-priority").value,
    estimated_minutes: Number(row.querySelector(".task-minutes").value),
    deadline_mode: row.querySelector(".task-deadline-mode").value,
    deadline_at: row.querySelector(".task-deadline-at").value || null,
  })).filter((item) => item.title);
}

addTaskButton.addEventListener("click", () => addTaskRow());
addTaskRow();
const legacyDeadline = document.querySelector("#deadline-at");
if (legacyDeadline) legacyDeadline.closest("div").classList.add("hidden");

function renderPlan(data) {
  document.querySelectorAll("#result > .grid").forEach((element) => element.classList.remove("hidden"));
  document.querySelector("#schedule-only").classList.add("hidden");
  renderList("#tasks", data.tasks.map((task) => {
    const deadline = task.deadline ? `Hạn: ${task.deadline}` : "Chưa có hạn rõ ràng";
    return `<strong>${escapeHtml(task.title)}</strong><span class="task-meta">${escapeHtml(task.type)} · ${escapeHtml(task.priority)} · ${deadline}</span>`;
  }));
  renderList("#priorities", data.priorities.map((item) => `<strong>${escapeHtml(item.task)}</strong> — ${item.score}/100`));
  renderList("#schedule", data.schedule.map((item) => `${item.date} · ${item.start_time}–${item.end_time}: <strong>${escapeHtml(item.task_title)}</strong> (${item.minutes} phút)`));
  document.querySelector("#subtasks").innerHTML = Object.entries(data.subtasks).map(([task, steps]) =>
    `<p><strong>${escapeHtml(task)}</strong></p><ul>${steps.map((step) => `<li>${escapeHtml(step.title)}<span class="task-meta">Hoàn thành khi: ${escapeHtml(step.definition_of_done)}</span></li>`).join("")}</ul>`
  ).join("");
  document.querySelector("#warnings").innerHTML = data.warnings.map((warning) => `<div class="warning">${escapeHtml(warning)}</div>`).join("");
  const analysis = data.goal_analysis || {};
  document.querySelector("#goal-analysis").textContent = analysis.summary || "AI chưa có đủ thông tin để phân tích mục tiêu.";
  renderList("#success-criteria", (analysis.success_criteria || []).map(escapeHtml));
  document.querySelector("#assumptions").textContent = (analysis.assumptions || []).length ? `Giả định: ${analysis.assumptions.join(" · ")}` : "";
  document.querySelector("#schedule-reasoning").textContent = data.schedule_reasoning || "Lịch dựa trên thời gian rảnh bạn đã cung cấp.";
  document.querySelector("#risks").innerHTML = (data.risks || []).map((risk) => `<p><strong>${escapeHtml(risk.title)}</strong><span class="task-meta">Mức độ: ${escapeHtml(risk.severity)} · ${escapeHtml(risk.mitigation)}</span></p>`).join("") || "<p class=\"task-meta\">Chưa phát hiện rủi ro nổi bật.</p>";
  document.querySelector("#focus-sessions").innerHTML = (data.focus_sessions || []).map((session) => `<p><strong>${escapeHtml(session.task_title)}</strong><span class="task-meta">${escapeHtml(session.objective)} · ${escapeHtml(session.method)}</span><span class="task-meta">${escapeHtml((session.checklist || []).join(" · "))}</span></p>`).join("") || "<p class=\"task-meta\">Chưa có gợi ý phiên tập trung.</p>";
  document.querySelector("#review-questions").innerHTML = (data.review_questions || []).map((item) => `<p><strong>${escapeHtml(item.question)}</strong><span class="task-meta">${escapeHtml(item.purpose)}</span></p>`).join("") || "<p class=\"task-meta\">Chưa có câu hỏi review.</p>";
  document.querySelector("#llm-status").textContent = `LLM: ${data.llm_provider} · ${data.llm_model}`;
  document.querySelector("#confidence").textContent = `Độ tin cậy ${Math.round(data.confidence * 100)}%`;
  const note = document.querySelector("#confirmation-note");
  note.classList.toggle("hidden", !data.needs_confirmation);
  note.textContent = "Vui lòng kiểm tra và xác nhận các mục được cảnh báo trước khi lưu hoặc tạo lịch.";
  emptyState.classList.add("hidden");
  result.classList.remove("hidden");
}

function renderScheduleOnly(data) {
  document.querySelectorAll("#result > .grid").forEach((element) => element.classList.add("hidden"));
  document.querySelector("#warnings").innerHTML = "";
  document.querySelector("#schedule-only").classList.remove("hidden");
  document.querySelector("#schedule-reasoning-only").textContent = data.schedule_reasoning || "Lịch được tạo theo các khung giờ bạn đã nhập.";
  renderList("#schedule-only-list", data.schedule.map((item) => `${item.date} · ${item.start_time}–${item.end_time} · ${escapeHtml(item.task_title)} · ${item.minutes} phút`));
  emptyState.classList.add("hidden");
  result.classList.remove("hidden");
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  button.disabled = true;
  button.textContent = "Đang tạo kế hoạch…";
  try {
    const response = await fetch("/v1/workflow/plan", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        user_id: document.querySelector("#user-id").value.trim(),
        display_name: document.querySelector("#display-name").value.trim(),
        raw_input: collectTaskInputs().map((item) => item.title).join(", "),
        task_inputs: collectTaskInputs(),
        available_minutes_per_day: Number(document.querySelector("#minutes").value),
        deadline_at: document.querySelector("#deadline-at").value || null,
        daily_start_time: document.querySelector("#start-time").value,
        daily_end_time: document.querySelector("#end-time").value,
        preferred_weekdays: [...document.querySelectorAll("input[name=weekday]:checked")].map((item) => Number(item.value)),
        energy_peak: document.querySelector("#energy-peak").value,
        work_style: document.querySelector("#work-style").value,
        focus_minutes: Number(document.querySelector("#focus-minutes").value),
        existing_commitments: document.querySelector("#commitments").value,
        planning_notes: document.querySelector("#planning-notes").value,
      }),
    });
    if (!response.ok) throw new Error("Không thể tạo kế hoạch. Hãy kiểm tra lại cấu hình LLM hoặc dữ liệu nhập.");
    const plan = await response.json();
    renderPlan(plan);
    loadSavedPlans();
  } catch (error) {
    document.querySelector("#warnings").innerHTML = `<div class="warning">${escapeHtml(error.message)}</div>`;
    emptyState.classList.add("hidden");
    result.classList.remove("hidden");
  } finally {
    button.disabled = false;
    button.textContent = "Tạo kế hoạch";
  }
});

async function loadSavedPlans() {
  const userId = document.querySelector("#user-id").value.trim();
  if (!userId) return;
  savedPlans.innerHTML = "<p class=\"task-meta\">Đang tải…</p>";
  try {
    const response = await fetch(`/v1/plans?user_id=${encodeURIComponent(userId)}`);
    if (!response.ok) throw new Error();
    const plans = await response.json();
    savedPlans.innerHTML = plans.length ? plans.map((plan) => `<button class=\"saved-plan\" type=\"button\" data-plan-id=\"${escapeHtml(plan.plan_id)}\"><strong>${escapeHtml(plan.title)}</strong><span>${new Date(plan.created_at).toLocaleString("vi-VN")} · ${plan.task_count} việc</span></button>`).join("") : "<p class=\"task-meta\">Chưa có kế hoạch nào được lưu cho mã người dùng này.</p>";
  } catch (_) {
    savedPlans.innerHTML = "<p class=\"warning\">Không thể tải lịch sử kế hoạch.</p>";
  }
}

loadPlansButton.addEventListener("click", loadSavedPlans);
savedPlans.addEventListener("click", async (event) => {
  const button = event.target.closest("[data-plan-id]");
  if (!button) return;
  const userId = document.querySelector("#user-id").value.trim();
  try {
    const response = await fetch(`/v1/plans/${encodeURIComponent(button.dataset.planId)}?user_id=${encodeURIComponent(userId)}`);
    if (!response.ok) throw new Error();
    renderScheduleOnly(await response.json());
  } catch (_) {
    document.querySelector("#warnings").innerHTML = "<div class=\"warning\">Không thể mở kế hoạch đã lưu.</div>";
  }
});

loadSavedPlans();
