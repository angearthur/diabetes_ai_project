function getRecommendations() {
    const age = parseInt(document.getElementById("age").value);
    const weight = parseFloat(document.getElementById("weight").value);
    const height = parseFloat(document.getElementById("height").value);
    const activity = document.getElementById("activity").value;
    const diet = document.getElementById("diet").value;

    if (!age || !weight || !height) {
        alert("Please fill all fields with valid numbers.");
        return;
    }

    const data = { age, weight, height, activity_level: activity, diet_preference: diet };

    fetch("/recommend", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(data)
    })
    .then(res => res.json())
    .then(result => {
        // Ensure arrays
        result.diet = Array.isArray(result.diet) ? result.diet : result.diet.split(", ");
        result.exercise = Array.isArray(result.exercise) ? result.exercise : result.exercise.split(", ");
        result.general = Array.isArray(result.general) ? result.general : result.general.split(", ");

        // Display current recommendation
        let html = `<div class="rec-box current-rec">
            <h3>BMI: ${result.bmi}</h3>
            <p><strong>Diet:</strong> ${result.diet.join(", ")}</p>
            <p><strong>Exercise:</strong> ${result.exercise.join(", ")}</p>
            <p><strong>General:</strong> ${result.general.join(", ")}</p>
        </div>`;

        document.getElementById("result").innerHTML = html;

        // Update past recommendations (show only last 3)
        updateHistory(result);
    })
    .catch(err => {
        console.error(err);
        alert("Error getting recommendations. Check console.");
    });
}

// Store last recommendations in memory (show last 3)
let recommendationHistory = [];

function updateHistory(newRecommendation) {
    recommendationHistory.unshift(newRecommendation);
    if (recommendationHistory.length > 3) recommendationHistory = recommendationHistory.slice(0, 3);

    let historyHtml = "<h3>Past Recommendations</h3>";
    recommendationHistory.forEach(rec => {
        historyHtml += `<div class="rec-box past-rec">
            <p><strong>BMI:</strong> ${rec.bmi}</p>
            <p><strong>Diet:</strong> ${rec.diet.join(", ")}</p>
            <p><strong>Exercise:</strong> ${rec.exercise.join(", ")}</p>
            <p><strong>General:</strong> ${rec.general.join(", ")}</p>
        </div>`;
    });

    document.getElementById("historyList").innerHTML = historyHtml;
}
