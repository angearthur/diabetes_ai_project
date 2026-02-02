let bmiChartInstance; // global variable for chart

function loadHistory() {
    fetch("/history")
        .then(res => res.json())
        .then(data => {
            // Show table of last 3 recommendations
            let html = "<h3>Last 3 Recommendations</h3>";
            html += "<table><tr><th>BMI</th><th>Diet</th><th>Exercise</th><th>General Advice</th></tr>";
            data.forEach(rec => {
                html += `<tr>
                    <td>${rec.bmi}</td>
                    <td>${rec.diet.join(", ")}</td>
                    <td>${rec.exercise.join(", ")}</td>
                    <td>${rec.general.join(", ")}</td>
                </tr>`;
            });
            html += "</table>";
            document.getElementById("historyTable").innerHTML = html;

            // Draw BMI chart
            const labels = data.map((_, i) => `Rec ${i + 1}`);
            const bmis = data.map(rec => rec.bmi);

            const ctx = document.getElementById('bmiChart').getContext('2d');
            if (bmiChartInstance) bmiChartInstance.destroy(); // destroy previous chart
            bmiChartInstance = new Chart(ctx, {
                type: 'line',
                data: {
                    labels: labels.reverse(),
                    datasets: [{
                        label: 'BMI Trend',
                        data: bmis.reverse(),
                        borderColor: 'rgba(31, 59, 115, 1)',
                        backgroundColor: 'rgba(31, 59, 115, 0.2)',
                        fill: true,
                        tension: 0.3
                    }]
                },
                options: {
                    responsive: true,
                    plugins: { legend: { display: true } },
                    scales: { y: { beginAtZero: false } }
                }
            });
        })
        .catch(err => console.error("Error loading history:", err));
}

// Load data when page loads
window.onload = loadHistory;
