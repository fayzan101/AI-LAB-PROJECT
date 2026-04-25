def calculate_productivity(data):
    return (
        data.get("tasks_completed", 0) * 3 +
        data.get("attendance_days", 0) * 2 -
        data.get("idle_hours", 0)
    )
def detect_burnout(data):
    if data.get("working_hours", 0) > 9:
        return "High Risk"
    elif data.get("working_hours", 0) > 7:
        return "Medium Risk"
    return "Low Risk"
def predict_delay(data):
    if data.get("task_progress", 0) < 50 and data.get("days_left", 0) < 3:
        return "High Risk"
    elif data.get("task_progress", 0) < 70:
        return "Medium Risk"
    return "Low Risk"
def generate_summary(prod, burnout, delay):
    if burnout == "High Risk":
        return "Employee is overworked and needs rest."
    elif prod > 60:
        return "Employee performance is good."
    return "Performance needs improvement."