"""
Kaggle Endurance Metrics Corpus Collector
==========================================
Downloads multiple Kaggle datasets covering running, cycling, triathlon,
swimming and more — then converts raw rows into rich semantic RAG chunks.
"""

import os
import json
import glob
import math
import pandas as pd
from datetime import datetime

# ─────────────────────────────────────────────
#  KAGGLE SETUP CHECK
# ─────────────────────────────────────────────
try:
    import kaggle
except OSError:
    print("❌ KAGGLE API ERROR: kaggle.json not found!")
    print("   → Kaggle → Settings → Create New Token → save to ~/.kaggle/kaggle.json")
    exit(1)

# ─────────────────────────────────────────────
#  CONFIGURATION
# ─────────────────────────────────────────────
DOWNLOAD_DIR = "./kaggle_data"
OUTPUT_FILE = "endurance_metrics_corpus.json"
MAX_RECORDS_PER_DATASET = 1000

# ─────────────────────────────────────────────
#  DATASETS — add more slugs here as you find them
# ─────────────────────────────────────────────
DATASETS = [
    {
        "slug": "deependraverma13/cardio-activities",
        "label": "cardio_activities",
        "description": "Mixed cardio workout logs (running, cycling, walking)",
    },
    {
        "slug": "kukuroo3/body-performance-data",
        "label": "body_performance",
        "description": "Athletic body composition and performance metrics",
    },
    {
        "slug": "aroojanwarkhan/running-data",
        "label": "running_data",
        "description": "Detailed running session logs",
    },
    # ── Add more datasets below as needed ──────────────────────────────────
    # {"slug": "...", "label": "...", "description": "..."},
]

# ─────────────────────────────────────────────
#  SPORT TYPE AUTO-TAGGER
# ─────────────────────────────────────────────
SPORT_KEYWORDS = {
    "running":   ["run", "jog", "sprint", "marathon", "trail"],
    "cycling":   ["cycl", "bike", "bik", "velo"],
    "swimming":  ["swim", "pool", "open water"],
    "triathlon": ["tri", "ironman", "brick"],
    "rowing":    ["row", "ergometer"],
    "skiing":    ["ski", "cross-country"],
    "hiking":    ["hike", "trek"],
    "walking":   ["walk"],
}

def tag_sport(raw_type: str) -> str:
    t = str(raw_type).lower()
    for sport, keywords in SPORT_KEYWORDS.items():
        if any(k in t for k in keywords):
            return sport
    return "other"


# ─────────────────────────────────────────────
#  INTENSITY ZONE CLASSIFIER
# ─────────────────────────────────────────────
def classify_intensity(avg_hr: float, max_hr: float = 190.0) -> str:
    """Maps avg HR to a training zone label (simplified 5-zone model)."""
    pct = (avg_hr / max_hr) * 100
    if pct < 60:   return "zone_1_recovery"
    if pct < 70:   return "zone_2_aerobic_base"
    if pct < 80:   return "zone_3_tempo"
    if pct < 90:   return "zone_4_threshold"
    return "zone_5_vo2max"


# ─────────────────────────────────────────────
#  SEMANTIC TEXT BUILDER
# ─────────────────────────────────────────────
def build_semantic_text(row: dict, dataset_label: str) -> str:
    """
    Converts a workout row into a rich natural-language description.
    The richer the text, the better the vector embedding will capture
    the semantic meaning for RAG retrieval.
    """
    parts = []

    # ── Core activity description ──────────────────────────────────────────
    sport = row.get("sport_type", "unknown")
    date  = row.get("date", "an unspecified date")
    parts.append(f"Workout Type: {sport.replace('_', ' ').title()}")
    parts.append(f"Date: {date}")

    # ── Distance & Pace ────────────────────────────────────────────────────
    dist = row.get("distance_km")
    if dist and not math.isnan(float(dist)):
        parts.append(f"Distance: {dist:.2f} km ({dist * 0.621:.2f} miles)")

    duration = row.get("duration")
    if duration:
        parts.append(f"Duration: {duration}")

    pace = row.get("avg_pace_min_per_km")
    if pace and not math.isnan(float(pace)):
        parts.append(f"Average Pace: {pace:.2f} min/km")

    # ── Heart Rate & Intensity ─────────────────────────────────────────────
    avg_hr = row.get("avg_hr")
    if avg_hr and not math.isnan(float(avg_hr)):
        zone = classify_intensity(float(avg_hr))
        parts.append(
            f"Average Heart Rate: {avg_hr:.0f} bpm "
            f"(Training Zone: {zone.replace('_', ' ')})"
        )

    max_hr = row.get("max_hr")
    if max_hr and not math.isnan(float(max_hr)):
        parts.append(f"Max Heart Rate: {max_hr:.0f} bpm")

    # ── Power (cycling) ────────────────────────────────────────────────────
    power = row.get("avg_power_watts")
    if power and not math.isnan(float(power)):
        parts.append(f"Average Power: {power:.0f} watts")

    # ── Elevation ─────────────────────────────────────────────────────────
    elevation = row.get("elevation_gain_m")
    if elevation and not math.isnan(float(elevation)):
        parts.append(f"Elevation Gain: {elevation:.0f} m")

    # ── Calories ──────────────────────────────────────────────────────────
    calories = row.get("calories")
    if calories and not math.isnan(float(calories)):
        parts.append(f"Calories Burned: {calories:.0f} kcal")

    # ── Narrative summary (makes the chunk more retrievable by LLMs) ───────
    narrative = (
        f"This {sport} session "
        + (f"covered {dist:.2f} km " if dist and not math.isnan(float(dist)) else "")
        + (f"in {duration} " if duration else "")
        + (f"at an average heart rate of {avg_hr:.0f} bpm ({zone}). " if avg_hr and not math.isnan(float(avg_hr)) else ". ")
    )
    parts.append(f"Summary: {narrative.strip()}")
    parts.append(f"Data Source: {dataset_label}")

    return "\n".join(parts)


# ─────────────────────────────────────────────
#  COLUMN NORMALISER
# Handles different column names across datasets
# ─────────────────────────────────────────────
COLUMN_ALIASES = {
    "distance_km":        ["Distance (km)", "distance_km", "Distance", "distance"],
    "duration":           ["Duration", "duration", "Elapsed Time", "Moving Time"],
    "avg_hr":             ["Average Heart Rate (bpm)", "avg_hr", "Avg HR", "heart_rate_avg"],
    "max_hr":             ["Max Heart Rate (bpm)", "max_hr", "Max HR", "heart_rate_max"],
    "date":               ["Date", "date", "Activity Date", "start_time"],
    "sport_type_raw":     ["Type", "type", "Activity Type", "sport"],
    "calories":           ["Calories", "calories", "Calories Burned"],
    "elevation_gain_m":   ["Climb (m)", "elevation_gain", "Total Ascent", "elevation_m"],
    "avg_pace_min_per_km":["Average Pace", "avg_pace", "pace_min_per_km"],
    "avg_power_watts":    ["Average Power", "avg_power", "power_watts"],
}

def normalise_df(df: pd.DataFrame) -> pd.DataFrame:
    """Renames columns to a standard schema regardless of source dataset."""
    rename_map = {}
    for standard_name, aliases in COLUMN_ALIASES.items():
        for alias in aliases:
            if alias in df.columns:
                rename_map[alias] = standard_name
                break
    return df.rename(columns=rename_map)


# ─────────────────────────────────────────────
#  MAIN PIPELINE
# ─────────────────────────────────────────────
def download_dataset(dataset: dict):
    dest = os.path.join(DOWNLOAD_DIR, dataset["label"])
    os.makedirs(dest, exist_ok=True)
    print(f"  📥 Downloading {dataset['slug']}...")
    kaggle.api.dataset_download_files(dataset["slug"], path=dest, unzip=True)
    print(f"  ✅ Done.")
    return dest


def process_dataset(folder: str, dataset: dict, max_records: int) -> list[dict]:
    """Finds CSVs in the folder and converts rows to RAG chunks."""
    csv_files = glob.glob(os.path.join(folder, "**", "*.csv"), recursive=True)
    if not csv_files:
        print(f"  ⚠️  No CSV found in {folder}")
        return []

    all_docs = []
    for csv_path in csv_files:
        print(f"  ⚙️  Processing {os.path.basename(csv_path)}...")
        try:
            df = pd.read_csv(csv_path, low_memory=False)
            df = normalise_df(df)

            # Drop rows without a distance or HR (useless for endurance context)
            required = [c for c in ["distance_km", "avg_hr"] if c in df.columns]
            if required:
                df = df.dropna(subset=required)

            df = df.head(max_records)

            for idx, row in df.iterrows():
                row_dict = row.to_dict()

                # Auto-tag sport type
                raw_sport = row_dict.get("sport_type_raw", "unknown")
                sport = tag_sport(str(raw_sport))
                row_dict["sport_type"] = sport

                dist   = row_dict.get("distance_km")
                avg_hr = row_dict.get("avg_hr")

                try:
                    content = build_semantic_text(row_dict, dataset["label"])
                except Exception:
                    continue

                doc = {
                    "id": f"{dataset['label']}_{idx}",
                    "content": content,
                    "metadata": {
                        "source": dataset["slug"],
                        "dataset_label": dataset["label"],
                        "document_type": "workout_log",
                        "sport_type": sport,
                        "distance_km": float(dist) if dist and not (isinstance(dist, float) and math.isnan(dist)) else None,
                        "avg_hr": float(avg_hr) if avg_hr and not (isinstance(avg_hr, float) and math.isnan(avg_hr)) else None,
                        "intensity_zone": classify_intensity(float(avg_hr)) if avg_hr and not (isinstance(avg_hr, float) and math.isnan(avg_hr)) else None,
                        "collected_at": datetime.utcnow().isoformat(),
                    },
                }
                all_docs.append(doc)

        except Exception as e:
            print(f"  ❌ Failed to process {csv_path}: {e}")

    return all_docs


def main():
    all_documents = []

    for dataset in DATASETS:
        print(f"\n{'─'*60}")
        print(f"📦 Dataset: {dataset['label']}")
        print(f"   {dataset['description']}")
        try:
            folder = download_dataset(dataset)
            docs   = process_dataset(folder, dataset, MAX_RECORDS_PER_DATASET)
            all_documents.extend(docs)
            print(f"  📊 Chunks added: {len(docs)} (running total: {len(all_documents)})")
        except Exception as e:
            print(f"  ❌ Dataset failed: {e}")

    if not all_documents:
        print("\n❌ No documents collected. Check your Kaggle credentials and dataset slugs.")
        return

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(all_documents, f, indent=2, ensure_ascii=False)

    print(f"\n{'═'*60}")
    print(f"🎉 Saved {len(all_documents)} physiological chunks → {OUTPUT_FILE}")
    print()
    print("💡 Tips for your RAG pipeline:")
    print("   • Chunk these docs by 'content' field — already sized for LLM context.")
    print("   • Use 'metadata.sport_type' as a Pinecone/Weaviate filter for sport-specific queries.")
    print("   • Use 'metadata.intensity_zone' to answer training-zone questions precisely.")


if __name__ == "__main__":
    main()