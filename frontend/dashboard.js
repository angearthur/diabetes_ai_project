let bmiChartInstance = null;
let feedbackChartInstance = null;
let allPatients = [];

function showStatus(msg) {
  const el = document.getElementById("statusMsg");
  el.style.display = "block";
  el.textContent = msg;
}
function clearStatus() {
  const el = document.getElementById("statusMsg");
  el.style.display = "none";
  el.textContent = "";
}

function escapeHtml(str) {
  return String(str ?? "").replace(/[&<>"']/g, s => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#039;"
  }[s]));
}

// Quiet retry to prevent "flash" error then load.
async function fetchWithRetry(url, tries = 3) {
  let lastErr = null;
  for (let i = 0; i < tries; i++) {
    try {
      const res = await fetch(url, { credentials: "include" });
      if (!res.ok) throw new Error(`${url} returned ${res.status}`);
      return await res.json();
    } catch (err) {
      lastErr = err;
      await new Promise(r => setTimeout(r, 250 * (i + 1)));
    }
  }
  throw lastErr;
}

async function requireClinicianAndSetHeader() {
  const res = await fetch("/whoami", { credentials: "include" });
  const data = await res.json();

  if (data.role !== "clinician") {
    window.location.href = "/clinician_login.html";
    return false;
  }

  const welcome = document.getElementById("welcomeText");
  if (welcome) welcome.textContent = `Welcome, ${data.name || "Clinician"}`;
  return true;
}

function applyFilters() {
  clearStatus();

  const bmiFilter = document.getElementById("bmiFilter").value;
  const feedbackFilter = document.getElementById("feedbackFilter").value;

  let filtered = [...allPatients];

  // BMI filter
  if (bmiFilter === "low") filtered = filtered.filter(p => Number(p.bmi) < 25);
  if (bmiFilter === "medium") filtered = filtered.filter(p => Number(p.bmi) >= 25 && Number(p.bmi) < 30);
  if (bmiFilter === "high") filtered = filtered.filter(p => Number(p.bmi) >= 30);

  // Feedback filter
  if (feedbackFilter === "low") filtered = filtered.filter(p => p.feedback != null && Number(p.feedback) < 3);
  if (feedbackFilter === "high") filtered = filtered.filter(p => p.feedback != null && Number(p.feedback) >= 4);

  renderTable(filtered);
  drawCharts(filtered);

  if (filtered.length === 0) showStatus("No patients match the selected filters.");
}

function renderListCell(items) {
  const arr = Array.isArray(items) ? items.filter(Boolean) : [];
  if (arr.length === 0) return `<span class="muted">—</span>`;

  const first = arr.slice(0, 3);
  const rest = arr.slice(3);

  const firstHtml = `<ul class="cell-list">${first.map(x => `<li>${escapeHtml(x)}</li>`).join("")}</ul>`;

  if (rest.length === 0) return firstHtml;

  return firstHtml + `
    <details class="cell-details">
      <summary>Show all (${arr.length})</summary>
      <ul class="cell-list">${arr.map(x => `<li>${escapeHtml(x)}</li>`).join("")}</ul>
    </details>
  `;
}

function renderTable(rows) {
  const host = document.getElementById("patientsTable");

  if (!rows || rows.length === 0) {
    host.innerHTML = `<p style="color:#555;">No data to display.</p>`;
    return;
  }

  let html = `
    <table class="dashboard-table clinician-table">
      <thead>
        <tr>
          <th class="col-patient">Patient</th>
          <th class="col-bmi">BMI</th>
          <th class="col-diet">Diet</th>
          <th class="col-exercise">Exercise</th>
          <th class="col-general">General Advice</th>
          <th class="col-feedback">Avg Feedback</th>
          <th class="col-risk">Risk</th>
          <th class="col-ai">AI Interpretation</th>
        </tr>
      </thead>
      <tbody>
  `;

  rows.forEach(p => {
    const bmi = Number(p.bmi);
    const fb = (p.feedback === null || p.feedback === undefined) ? null : Number(p.feedback);

    let risks = Array.isArray(p.risks) ? p.risks : [];
    if (risks.length === 0) {
      if (!Number.isNaN(bmi) && bmi >= 30) risks.push("⚠️ High BMI");
      if (fb !== null && fb < 3) risks.push("⚠️ Low Feedback");
    }
    const riskText = risks.length ? risks.join(" | ") : "None";

    html += `
      <tr>
        <td class="patient-name"><strong>${escapeHtml(p.name || "Unknown")}</strong></td>
        <td>${Number.isNaN(bmi) ? "N/A" : bmi.toFixed(2)}</td>
        <td>${renderListCell(p.diet)}</td>
        <td>${renderListCell(p.exercise)}</td>
        <td>${renderListCell(p.general)}</td>
        <td>${fb === null ? "N/A" : `${fb.toFixed(1)}/5`}</td>
        <td>${escapeHtml(riskText)}</td>
        <td class="ai-cell"><div class="ai-wrap">${escapeHtml(p.ai_explanation || "")}</div></td>
      </tr>
    `;
  });

  html += `</tbody></table>`;
  host.innerHTML = html;
}

function drawCharts(rows) {
  const bmiCanvas = document.getElementById("bmiChart");
  const fbCanvas = document.getElementById("feedbackChart");
  if (!bmiCanvas || !fbCanvas) return;

  if (bmiChartInstance) bmiChartInstance.destroy();
  if (feedbackChartInstance) feedbackChartInstance.destroy();

  if (!rows || rows.length === 0) return;

  const labels = rows.map((_, i) => `#${i + 1}`);
  const bmiValues = rows.map(p => Number(p.bmi));
  const feedbackValues = rows.map(p => (p.feedback == null) ? 0 : Number(p.feedback));

  bmiChartInstance = new Chart(bmiCanvas.getContext("2d"), {
    type: "line",
    data: {
      labels,
      datasets: [{ label: "BMI", data: bmiValues, fill: true, tension: 0.3 }]
    },
    options: { responsive: true, plugins: { legend: { display: true } } }
  });

  feedbackChartInstance = new Chart(fbCanvas.getContext("2d"), {
    type: "bar",
    data: {
      labels,
      datasets: [{ label: "Feedback (0 = N/A)", data: feedbackValues }]
    },
    options: { responsive: true, scales: { y: { beginAtZero: true, max: 5 } } }
  });
}

function downloadPdf() {
  const bmi = document.getElementById("bmiFilter").value;
  const feedback = document.getElementById("feedbackFilter").value;

  // NOTE: backend must have /export-pdf route, otherwise you'll get "URL not found"
  window.location.href = `/export-pdf?bmi=${encodeURIComponent(bmi)}&feedback=${encodeURIComponent(feedback)}`;
}

async function logout() {
  try {
    await fetch("/logout", { method: "POST", credentials: "include" });
  } catch (e) {}
  window.location.href = "/clinician_login.html";
}

async function init() {
  const ok = await requireClinicianAndSetHeader();
  if (!ok) return;

  try {
    clearStatus();
    allPatients = await fetchWithRetry("/clinician-data", 3);
    renderTable(allPatients);
    drawCharts(allPatients);

    document.getElementById("applyBtn").addEventListener("click", applyFilters);
    document.getElementById("pdfBtn").addEventListener("click", downloadPdf);
    document.getElementById("logoutBtn").addEventListener("click", logout);

  } catch (err) {
    console.error("Clinician dashboard load failed:", err);
    showStatus("Could not load clinician dashboard data. Please refresh once.");
  }
}

window.addEventListener("DOMContentLoaded", init);
