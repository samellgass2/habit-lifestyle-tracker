from Server.constants import CHALLENGE_MULT, IMPORTANCE_MULT

# GUIDING RULE: 1 task = 10% of a goal = 30 minutes of work = 100 points = $1
def compute_points(points_mode, base_value, challenge, importance, time_minutes=None, percent_value=None):
    base = float(base_value or 1.0)
    c = CHALLENGE_MULT[challenge]
    i = IMPORTANCE_MULT[int(importance)]
    if points_mode == "tasks":
        payload = 100.0 # 1 task = 100
    elif points_mode == "time":
        payload = 100.0 * (max(0, (time_minutes or 0)) / 30.0) # 30 mins = 100
    else:  # percent
        payload = 1000.0 * max(0.0, min(100.0, float(percent_value or 0))) # 10% = 100
    return round(base * c * i * payload, 2)


def potential_points_for_habit(points_mode, base_value, challenge, importance, time_target=None, percent_target=None):
    if points_mode == "tasks":
        return compute_points("tasks", base_value, challenge, importance, None, None)
    if points_mode == "time":
        return compute_points("time", base_value, challenge, importance, time_minutes=time_target or 0)
    return compute_points("percent", base_value, challenge, importance, percent_value=percent_target or 0)