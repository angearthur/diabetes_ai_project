def calculate_bmi(weight, height):
    try:
        weight = float(weight)
        height = float(height)
    except (TypeError, ValueError):
        return 0

    if height <= 0:
        return 0

    height_m = height / 100
    return round(weight / (height_m ** 2), 2)


def get_user_feedback_score(user_id, cursor):
    cursor.execute("SELECT AVG(score) FROM feedback WHERE user_id = ?", (user_id,))
    result = cursor.fetchone()[0]
    return float(result) if result is not None else 3.0  # neutral default


def generate_adaptive_recommendations(user_id, data, cursor):
    bmi = calculate_bmi(data.get("weight"), data.get("height"))
    activity = data.get("activity_level", "Low")
    diet_pref = data.get("diet_preference", "Vegetarian")

    avg_feedback = get_user_feedback_score(user_id, cursor)

    recommendations = {
        "bmi": bmi,
        "diet": [],
        "exercise": [],
        "general": []
    }

    # Base diet + general
    recommendations["diet"].append("Follow a balanced diabetic-friendly diet with controlled carbohydrates")
    recommendations["general"].extend([
        "Monitor blood glucose levels regularly",
        "Maintain adequate hydration"
    ])

    # Adaptive feedback logic
    if avg_feedback >= 4:
        recommendations["general"].append("You are doing well — continue following the current lifestyle plan")
    elif avg_feedback >= 3:
        recommendations["diet"].append("Introduce healthy food variety to prevent dietary fatigue")
        recommendations["general"].append("Gradual lifestyle improvements can increase long-term adherence")
    else:
        recommendations["diet"].append("Reduce sugar intake strictly and avoid processed foods")
        recommendations["general"].append("Focus on small, achievable goals to rebuild consistency")

    # Activity adaptation
    if activity == "Low":
        recommendations["exercise"].append("Aim for at least 30 minutes of walking per day" if avg_feedback >= 3
                                           else "Begin with 15–20 minutes of light walking daily")
    elif activity == "High":
        recommendations["exercise"].append("Maintain regular exercise but ensure adequate recovery")
    else:
        recommendations["exercise"].append("Continue moderate exercise, ensure consistency and rest")

    # Diet preference
    if diet_pref == "Non-Vegetarian":
        recommendations["diet"].append("Include lean protein sources such as fish or grilled chicken")
    else:
        recommendations["diet"].append("Include lentils, beans, and leafy vegetables as protein sources")

    return recommendations
