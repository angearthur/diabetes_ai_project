let currentUserId = null;
let charts = {};

async function mustBePatient() {
  const res = await fetch("/whoami", { credentials: "include" });
  const me = await res.json();
  if (me.role !== "patient") window.location.href = "/login.html";
  currentUserId = me.user_id;
}

function count(arr) {
  return arr.reduce((a, c) => {
    a[c] = (a[c] || 0) + 1;
    return a;
  }, {});
}

function drawChart(id, type, data, label) {
  if (charts[id]) charts[id].destroy();

  charts[id] = new Chart(document.getElementById(id), {
    type,
    data: {
      labels: Array.isArray(data)
        ? data.map((_, i) => `Rec ${i + 1}`)
        : Object.keys(data),
      datasets: [{
        label,
        data: Array.isArray(data) ? data : Object.values(data),
        backgroundColor: "#1f3b73",
        borderColor: "#1f3b73",
        fill: type === "line",
        tension: 0.3
      }]
    },
    options: { responsive: true }
  });
}

async function loadUserCharts() {
  try {
    const res = await fetch(`/user-charts/${currentUserId}`, { credentials: "include" });
    if (!res.ok) throw new Error("charts fetch failed");
    const data = await res.json();

    document.getElementById("chartsTitle").style.display = "block";

    drawChart("bmiChart", "line", data.bmi, "BMI Trend");
    drawChart("dietChart", "bar", count(data.diet), "Diet Frequency");
    drawChart("exerciseChart", "bar", count(data.exercise), "Exercise Frequency");
    drawChart("generalChart", "bar", count(data.general), "General Advice Frequency");
  } catch (e) {
    console.error(e);
    alert("Failed to load charts");
  }
}

async function getRecommendation() {
  try {
    await mustBePatient();

    const payload = {
      age: document.getElementById("age").value,
      weight: document.getElementById("weight").value,
      height: document.getElementById("height").value,
      activity_level: document.getElementById("activity").value,
      diet_preference: document.getElementById("diet").value
    };

    const res = await fetch("/recommend", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "include",
      body: JSON.stringify(payload)
    });

    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "Recommendation failed");

    document.getElementById("recommendationResult").innerHTML = `
      <div class="card">
        <h3 style="margin-top:0;">Your Recommendation</h3>
        <p><strong>BMI:</strong> ${data.bmi}</p>

        <div class="section">
          <strong>🥗 Diet</strong>
          <ul>${data.diet.map(d => `<li>${d}</li>`).join("")}</ul>
        </div>

        <div class="section">
          <strong>🏃 Exercise</strong>
          <ul>${data.exercise.map(e => `<li>${e}</li>`).join("")}</ul>
        </div>

        <div class="section">
          <strong>🧠 General Advice</strong>
          <ul>${data.general.map(g => `<li>${g}</li>`).join("")}</ul>
        </div>

        <div class="feedback">
          <p><strong>Was this helpful?</strong></p>
          <button onclick="sendFeedback(5)">👍 Yes</button>
          <button onclick="sendFeedback(1)">👎 No</button>
        </div>
      </div>
    `;

    await loadUserCharts();
  } catch (err) {
    console.error(err);
    alert("Failed to get recommendation");
  }
}

async function sendFeedback(score) {
  try {
    const res = await fetch("/feedback", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "include",
      body: JSON.stringify({ score })
    });

    if (!res.ok) throw new Error("feedback failed");
    document.querySelector(".feedback").innerHTML = "<p>✅ Feedback submitted</p>";
  } catch (e) {
    alert("Failed to submit feedback");
  }
}

// On load: ensure patient session
window.addEventListener("DOMContentLoaded", mustBePatient);
