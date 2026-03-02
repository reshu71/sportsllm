import math
from datetime import datetime, timedelta

# ==========================================
# SPORT CLASSIFICATION
# ==========================================

# Sports that have meaningful distance (show km/miles)
DISTANCE_SPORTS = {
    "Run", "TrailRun", "VirtualRun",
    "Ride", "MountainBikeRide", "GravelRide", "EBikeRide",
    "EMountainBikeRide", "VirtualRide", "Handcycle", "Velomobile",
    "Swim", "Walk", "Hike", "Snowshoe", "NordicSki",
    "RollerSki", "Rowing", "VirtualRow", "Kayaking",
    "StandUpPaddling", "Canoeing", "Surfing",
}

# Sports where distance is irrelevant — show duration + HR instead
NO_DISTANCE_SPORTS = {
    "Yoga", "Pilates", "WeightTraining", "Workout", "Crossfit",
    "HighIntensityIntervalTraining", "Elliptical", "StairStepper",
    "Badminton", "Tennis", "TableTennis", "Squash", "Racquetball",
    "Soccer", "Pickleball", "RockClimbing", "Golf", "IceSkate",
    "InlineSkate", "Skateboard", "Windsurf", "Kitesurf", "Sail",
    "Snowboard", "AlpineSki", "BackcountrySki",
}

# Category grouping for analytics
SPORT_CATEGORIES = {
    "Run": "running", "TrailRun": "running", "VirtualRun": "running",
    "Ride": "cycling", "MountainBikeRide": "cycling", "GravelRide": "cycling",
    "EBikeRide": "cycling", "EMountainBikeRide": "cycling", "VirtualRide": "cycling",
    "Swim": "swimming",
    "Walk": "walking", "Hike": "hiking",
    "Yoga": "flexibility", "Pilates": "flexibility",
    "WeightTraining": "strength", "Crossfit": "strength",
    "HighIntensityIntervalTraining": "strength", "Workout": "strength",
    "Elliptical": "crosstraining", "StairStepper": "crosstraining",
    "Rowing": "crosstraining", "VirtualRow": "crosstraining",
}

# Icons for UI display
SPORT_ICONS = {
    "running": "🏃", "cycling": "🚴", "swimming": "🏊",
    "walking": "🚶", "hiking": "🥾", "flexibility": "🧘",
    "strength": "💪", "crosstraining": "⚡", "water": "🚣",
    "other": "🏅",
}

def classify_sport(sport_type: str) -> dict:
    """
    Takes a raw Strava sport_type string and returns full classification.
    Never returns 0km for yoga/strength — returns None for distance instead.
    """
    has_distance = sport_type in DISTANCE_SPORTS
    category = SPORT_CATEGORIES.get(sport_type, "other")
    return {
        "sport_type": sport_type,
        "category": category,
        "has_distance": has_distance,
        "display_metric": "distance" if has_distance else "duration",
        "icon": SPORT_ICONS.get(category, "🏅"),
        "label": sport_type_to_label(sport_type),
    }

def sport_type_to_label(sport_type: str) -> str:
    """Converts PascalCase Strava type to human-readable label."""
    import re
    return re.sub(r'(?<!^)(?=[A-Z])', ' ', sport_type)

# ==========================================
# JACK DANIELS VDOT FORMULAS
# ==========================================
def calculate_vdot(distance_meters: float, time_seconds: float) -> float:
    """
    Calculates the VDOT (effective VO2 max) based on a race performance.
    Uses the Daniels/Gilbert formula approximation.
    """
    if distance_meters <= 0 or time_seconds <= 0:
        return 0.0

    time_minutes = time_seconds / 60.0
    velocity_m_min = distance_meters / time_minutes

    vo2_demand = 0.182258 * velocity_m_min + 0.000104 * (velocity_m_min ** 2) - 4.60
    profile = 0.8 + 0.1894393 * math.exp(-0.012778 * time_minutes) + 0.2989558 * math.exp(-0.1932605 * time_minutes)

    vdot = vo2_demand / profile
    return round(vdot, 2)


# ==========================================
# RACE PREDICTIONS (RIEGEL FORMULA)
# ==========================================
def predict_race_time(recent_distance_meters: float, recent_time_seconds: float, target_distance_meters: float) -> float:
    """
    Predicts race finish time using Pete Riegel's formula.
    T2 = T1 * (D2 / D1)^1.06
    """
    if recent_distance_meters <= 0:
        return 0.0
    predicted_time = recent_time_seconds * ((target_distance_meters / recent_distance_meters) ** 1.06)
    return round(predicted_time, 2)

def predict_all_race_times(known_dist_km: float, known_time_sec: float) -> dict:
    """Given one known race result, predict times for all standard distances."""
    targets = {
        "1K": 1, "5K": 5, "10K": 10, "15K": 15,
        "Half Marathon": 21.0975, "Marathon": 42.195,
        "50K": 50, "100K": 100
    }
    predictions = {}
    for name, dist in targets.items():
        pred_sec = predict_race_time(known_dist_km * 1000, known_time_sec, dist * 1000)
        predictions[name] = {"seconds": pred_sec, "formatted": format_time(pred_sec)}
    return predictions


# ==========================================
# TRAINING METRICS (TSS & ACUTE/CHRONIC LOAD)
# ==========================================
def calculate_tss(duration_seconds: float, avg_hr: int, max_hr: int, resting_hr: int) -> float:
    """
    Calculates a Training Stress Score (TSS) approximation based on Heart Rate Reserve (hrTSS).
    """
    if max_hr <= resting_hr or duration_seconds <= 0 or avg_hr <= resting_hr:
        return 0.0

    hr_reserve = max_hr - resting_hr
    avg_hr_reserve = avg_hr - resting_hr
    intensity_factor = avg_hr_reserve / hr_reserve
    duration_hours = duration_seconds / 3600.0
    tss = duration_hours * (intensity_factor ** 2) * 100
    adjusted_tss = tss * (1.0 + intensity_factor)
    return round(adjusted_tss, 1)


# ==========================================
# PERFORMANCE MANAGEMENT CHART (PMC)
# ==========================================
def compute_pmc_series(workouts: list[dict]) -> list[dict]:
    """
    Returns day-by-day CTL (Chronic Training Load / Fitness),
    ATL (Acute Training Load / Fatigue), TSB (Training Stress Balance / Form).
    workouts: list of {'date': str, 'tss': float}
    """
    if not workouts:
        return []
    sorted_w = sorted(workouts, key=lambda x: x['date'])
    start = datetime.strptime(sorted_w[0]['date'], '%Y-%m-%d')
    end = datetime.strptime(sorted_w[-1]['date'], '%Y-%m-%d')
    # Extend to today if the last workout is before today
    today = datetime.today()
    if end < today:
        end = today
    tss_map = {}
    for w in sorted_w:
        tss_map[w['date']] = tss_map.get(w['date'], 0) + w['tss']
    ctl, atl = 0.0, 0.0
    result = []
    current = start
    while current <= end:
        date_str = current.strftime('%Y-%m-%d')
        tss = tss_map.get(date_str, 0.0)
        ctl = ctl + (tss - ctl) * (1/42)
        atl = atl + (tss - atl) * (1/7)
        tsb = ctl - atl
        result.append({
            'date': date_str,
            'ctl': round(ctl, 1),
            'atl': round(atl, 1),
            'tsb': round(tsb, 1),
            'tss': round(tss, 1)
        })
        current += timedelta(days=1)
    return result

def compute_ramp_rate(pmc_series: list[dict]) -> float:
    """Weekly ramp rate = change in CTL over last 7 days. Safe: 5-8. Danger: >10."""
    if len(pmc_series) < 7:
        return 0.0
    return round(pmc_series[-1]['ctl'] - pmc_series[-7]['ctl'], 1)


# ==========================================
# HEART RATE ZONES (KARVONEN METHOD)
# ==========================================
def calculate_hr_zones(max_hr: int, resting_hr: int) -> dict:
    """
    Karvonen (Heart Rate Reserve) method for 5-zone model.
    Returns {zone_name: (min_hr, max_hr)}.
    """
    hrr = max_hr - resting_hr
    zones = {
        "Z1 Recovery":  (resting_hr + int(hrr * 0.50), resting_hr + int(hrr * 0.60)),
        "Z2 Aerobic":   (resting_hr + int(hrr * 0.60), resting_hr + int(hrr * 0.70)),
        "Z3 Tempo":     (resting_hr + int(hrr * 0.70), resting_hr + int(hrr * 0.80)),
        "Z4 Threshold": (resting_hr + int(hrr * 0.80), resting_hr + int(hrr * 0.90)),
        "Z5 VO2max":    (resting_hr + int(hrr * 0.90), max_hr),
    }
    return zones

def classify_workout_zone(avg_hr: int, max_hr: int, resting_hr: int) -> str:
    """Returns zone name for a given average HR."""
    zones = calculate_hr_zones(max_hr, resting_hr)
    for zone_name, (lo, hi) in zones.items():
        if lo <= avg_hr <= hi:
            return zone_name
    if avg_hr < list(zones.values())[0][0]:
        return "Z1 Recovery"
    return "Z5 VO2max"


# ==========================================
# UTILITIES
# ==========================================
def format_time(seconds: float) -> str:
    """Formats seconds into HH:MM:SS or MM:SS"""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    if h > 0:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"
