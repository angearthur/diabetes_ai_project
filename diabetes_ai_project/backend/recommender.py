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

def generate_recommendations(data):
    bmi = calculate_bmi(data.get("weight"), data.get("height"))

    recommendations = {
        "bmi": bmi,
        "diet": ["Maintain a balanced diabetic-friendly diet", "Include lentils, beans, leafy greens"],
        "exercise": [],
        "general": ["Monitor blood glucose levels regularly", "Stay hydrated and manage stress"]
    }

    activity = data.get("activity_level", "low")
    if activity == "low":
        recommendations["exercise"].append("Start with 30 minutes of walking daily and increase gradually")
    elif activity == "medium":
        recommendations["exercise"].append("Continue moderate exercise, such as 30-45 minutes of brisk walking")
    else:
        recommendations["exercise"].append("Maintain your high activity routine, ensure proper rest and hydration")

    diet_pref = data.get("diet_preference", "vegetarian")
    if diet_pref == "non-vegetarian":
        recommendations["diet"].append("Include lean meats and fish in your diet")

    return recommendations
