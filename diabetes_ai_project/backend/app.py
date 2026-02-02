from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import sqlite3
from recommender import generate_recommendations
from datetime import datetime
import os

# -------------------------
# Flask app setup
# -------------------------
app = Flask(__name__, static_folder="../frontend", static_url_path="")
CORS(app)

# -------------------------
# Database connection
# -------------------------
conn = sqlite3.connect("database.db", check_same_thread=False)
cursor = conn.cursor()

# -------------------------
# Serve frontend index.html
# -------------------------
@app.route("/")
def home():
    return send_from_directory(app.static_folder, "index.html")

# -------------------------
# Recommendations endpoint
# -------------------------
@app.route("/recommend", methods=["POST"])
def recommend():
    data = request.json
    try:
        age = int(data.get("age"))
        weight = float(data.get("weight"))
        height = float(data.get("height"))
        activity = data.get("activity_level")
        diet = data.get("diet_preference")
    except (TypeError, ValueError):
        return jsonify({"error": "Invalid input"}), 400

    # Generate recommendations
    recommendations = generate_recommendations({
        "age": age,
        "weight": weight,
        "height": height,
        "activity_level": activity,
        "diet_preference": diet
    })

    # Save to database
    cursor.execute("""
        INSERT INTO recommendations (user_id, bmi, diet, exercise, general)
        VALUES (?, ?, ?, ?, ?)
    """, (
        None,
        recommendations["bmi"],
        ", ".join(recommendations["diet"]),
        ", ".join(recommendations["exercise"]),
        ", ".join(recommendations["general"])
    ))
    conn.commit()

    return jsonify(recommendations)

# -------------------------
# Past recommendations endpoint (last 3)
# -------------------------
@app.route("/history", methods=["GET"])
def history():
    cursor.execute("""
        SELECT bmi, diet, exercise, general
        FROM recommendations
        ORDER BY id DESC
        LIMIT 3
    """)
    rows = cursor.fetchall()
    history_list = []
    for row in rows:
        history_list.append({
            "bmi": row[0],
            "diet": row[1].split(", "),
            "exercise": row[2].split(", "),
            "general": row[3].split(", ")
        })
    return jsonify(history_list)

# -------------------------
# Charts data endpoint (last 3)
# -------------------------
@app.route("/charts-data", methods=["GET"])
def charts_data():
    cursor.execute("""
        SELECT bmi, diet, exercise, general
        FROM recommendations
        ORDER BY id DESC
        LIMIT 3
    """)
    rows = cursor.fetchall()
    data = {
        "bmi": [],
        "diet_items": [],
        "exercise_items": [],
        "general_items": []
    }
    # Reverse so oldest first
    for row in rows[::-1]:
        data["bmi"].append(row[0])
        data["diet_items"].extend(row[1].split(", "))
        data["exercise_items"].extend(row[2].split(", "))
        data["general_items"].extend(row[3].split(", "))
    return jsonify(data)

# -------------------------
# Run the app
# -------------------------
if __name__ == "__main__":
    app.run(debug=True)
