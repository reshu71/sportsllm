"""
PubMed Endurance Sports Corpus Collector
=========================================
Collects scientific abstracts across ALL key endurance sport domains:
nutrition, training, physiology, recovery, biomechanics, psychology, and more.
"""

import requests
import json
import time
import xml.etree.ElementTree as ET
from datetime import datetime

# ─────────────────────────────────────────────
#  CONFIGURATION
# ─────────────────────────────────────────────
OUTPUT_FILE = "endurance_science_corpus.json"
MAX_RESULTS_PER_QUERY = 200   # Per query; scale up when you have an API key
SLEEP_BETWEEN_REQUESTS = 0.4  # PubMed allows ~3 req/s without API key

# ─────────────────────────────────────────────
#  MULTI-DOMAIN QUERY MAP
#  Each entry: (search_query, topic_tag, sport_tag)
# ─────────────────────────────────────────────
QUERY_MAP = [
    # ── PHYSIOLOGY ─────────────────────────────────────────────────────────
    ('"VO2 max" endurance athlete', "physiology", "multi"),
    ('"lactate threshold" endurance training', "physiology", "multi"),
    ('"aerobic capacity" marathon OR triathlon OR cycling', "physiology", "multi"),
    ('"cardiac output" endurance exercise', "physiology", "multi"),

    # ── NUTRITION ──────────────────────────────────────────────────────────
    ('"carbohydrate loading" endurance performance', "nutrition", "multi"),
    ('"sports nutrition" marathon OR ultramarathon', "nutrition", "running"),
    ('"fat adaptation" endurance athlete', "nutrition", "multi"),
    ('"protein intake" endurance OR triathlon', "nutrition", "multi"),
    ('"hydration" endurance exercise performance', "nutrition", "multi"),
    ('"electrolyte" marathon OR Ironman performance', "nutrition", "multi"),
    ('"caffeine" endurance performance', "nutrition", "multi"),
    ('"beetroot" OR "nitrate" endurance exercise', "nutrition", "multi"),

    # ── TRAINING METHODOLOGY ───────────────────────────────────────────────
    ('"polarized training" endurance athlete', "training", "multi"),
    ('"periodization" endurance OR cycling OR running', "training", "multi"),
    ('"high intensity interval training" endurance', "training", "multi"),
    ('"zone 2" training aerobic base', "training", "multi"),
    ('"overtraining syndrome" endurance athlete', "training", "multi"),
    ('"training load" monitoring endurance', "training", "multi"),
    ('"tapering" marathon OR triathlon performance', "training", "multi"),
    ('"concurrent training" strength endurance', "training", "multi"),

    # ── RECOVERY ───────────────────────────────────────────────────────────
    ('"sleep" recovery endurance athlete', "recovery", "multi"),
    ('"muscle damage" marathon OR ultramarathon recovery', "recovery", "running"),
    ('"cold water immersion" OR "ice bath" recovery endurance', "recovery", "multi"),
    ('"compression garment" endurance recovery', "recovery", "multi"),
    ('"heart rate variability" recovery training', "recovery", "multi"),

    # ── SPORT-SPECIFIC ─────────────────────────────────────────────────────
    ('"marathon" running performance physiology', "physiology", "running"),
    ('"ultramarathon" performance fatigue', "physiology", "running"),
    ('"cycling" power output endurance', "physiology", "cycling"),
    ('"triathlon" Ironman performance', "physiology", "triathlon"),
    ('"open water swimming" endurance', "physiology", "swimming"),
    ('"cross-country skiing" endurance physiology', "physiology", "skiing"),
    ('"rowing" endurance performance physiology', "physiology", "rowing"),

    # ── BIOMECHANICS ───────────────────────────────────────────────────────
    ('"running economy" endurance performance', "biomechanics", "running"),
    ('"cycling efficiency" power output', "biomechanics", "cycling"),
    ('"stride length" OR "cadence" running economy', "biomechanics", "running"),

    # ── PSYCHOLOGY & MENTAL PERFORMANCE ───────────────────────────────────
    ('"motivation" OR "mental toughness" endurance athlete', "psychology", "multi"),
    ('"pacing strategy" endurance performance', "psychology", "multi"),
    ('"RPE" perceived exertion endurance', "psychology", "multi"),

    # ── ALTITUDE & ENVIRONMENT ─────────────────────────────────────────────
    ('"altitude training" endurance performance', "physiology", "multi"),
    ('"heat stress" endurance exercise performance', "physiology", "multi"),

    # ── INJURY & HEALTH ────────────────────────────────────────────────────
    ('"running injury" prevention endurance', "injury", "running"),
    ('"bone stress injury" endurance athlete', "injury", "running"),
    ('"relative energy deficiency" RED-S endurance', "nutrition", "multi"),

    # ── WEARABLES & MONITORING ─────────────────────────────────────────────
    ('"wearable" OR "GPS" endurance athlete monitoring', "technology", "multi"),
    ('"lactate" field testing endurance athlete', "physiology", "multi"),
]


def search_pubmed(query: str, max_results: int) -> list[str]:
    """Returns list of PMIDs for a query."""
    url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
    params = {
        "db": "pubmed",
        "term": query,
        "retmax": max_results,
        "retmode": "json",
        "sort": "relevance",
    }
    r = requests.get(url, params=params, timeout=15)
    r.raise_for_status()
    return r.json()["esearchresult"]["idlist"]


def fetch_abstracts_batch(pmids: list[str], topic: str, sport: str) -> list[dict]:
    """Fetches and parses abstracts for a batch of PMIDs."""
    url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
    params = {
        "db": "pubmed",
        "id": ",".join(pmids),
        "retmode": "xml",
    }
    r = requests.get(url, params=params, timeout=30)
    r.raise_for_status()

    root = ET.fromstring(r.content)
    documents = []

    for article in root.findall(".//PubmedArticle"):
        try:
            pmid = article.find(".//PMID").text

            title_el = article.find(".//ArticleTitle")
            title = (title_el.text or "").strip() if title_el is not None else ""

            # Structured abstract (Background / Methods / Results / Conclusions)
            abstract_parts = []
            for elem in article.findall(".//AbstractText"):
                label = elem.get("Label", "")
                text = elem.text or ""
                if label:
                    abstract_parts.append(f"{label}: {text}")
                elif text:
                    abstract_parts.append(text)
            abstract = " ".join(abstract_parts).strip()

            if not abstract:
                continue

            # Journal & year
            journal_el = article.find(".//Journal/Title")
            journal = journal_el.text if journal_el is not None else "Unknown"

            year_el = article.find(".//PubDate/Year")
            year = int(year_el.text) if year_el is not None else None

            # Author keywords
            keywords = [
                kw.text for kw in article.findall(".//Keyword") if kw.text
            ]

            # MeSH headings for richer semantic context
            mesh_terms = [
                mh.find("DescriptorName").text
                for mh in article.findall(".//MeshHeading")
                if mh.find("DescriptorName") is not None
            ]

            # ── Build the content field ──────────────────────────────────
            # Combine title + abstract + mesh terms so the vector embedding
            # captures the full semantic meaning of the paper.
            content_parts = [f"Title: {title}", f"Abstract: {abstract}"]
            if keywords:
                content_parts.append(f"Keywords: {', '.join(keywords)}")
            if mesh_terms:
                content_parts.append(f"MeSH Terms: {', '.join(mesh_terms)}")

            doc = {
                "id": f"pubmed_{pmid}",
                "content": "\n".join(content_parts),
                "metadata": {
                    "source": "pubmed",
                    "document_type": "scientific_abstract",
                    "pmid": pmid,
                    "title": title,
                    "journal": journal,
                    "year": year,
                    "topic": topic,
                    "sport_type": sport,
                    "keywords": keywords,
                    "mesh_terms": mesh_terms[:10],  # cap to avoid bloat
                    "collected_at": datetime.utcnow().isoformat(),
                },
            }
            documents.append(doc)

        except (AttributeError, TypeError):
            continue

    return documents


def main():
    all_docs: dict[str, dict] = {}  # keyed by PMID to auto-deduplicate
    total_queries = len(QUERY_MAP)

    print(f"🚀 Starting multi-domain PubMed collection ({total_queries} queries)\n")

    for i, (query, topic, sport) in enumerate(QUERY_MAP, 1):
        print(f"[{i:02d}/{total_queries}] 🔍 {topic.upper()} | {query[:60]}...")

        try:
            pmids = search_pubmed(query, MAX_RESULTS_PER_QUERY)
            if not pmids:
                print("  ⚠️  No results.")
                continue

            # Remove already-fetched PMIDs to save API calls
            new_pmids = [p for p in pmids if f"pubmed_{p}" not in all_docs]
            print(f"  Found {len(pmids)} | New: {len(new_pmids)}")

            if new_pmids:
                time.sleep(SLEEP_BETWEEN_REQUESTS)
                docs = fetch_abstracts_batch(new_pmids, topic, sport)
                for doc in docs:
                    all_docs[doc["id"]] = doc
                print(f"  ✅ Added {len(docs)} abstracts (total: {len(all_docs)})")

        except Exception as e:
            print(f"  ❌ Error: {e}")

        time.sleep(SLEEP_BETWEEN_REQUESTS)

    final_docs = list(all_docs.values())
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(final_docs, f, indent=2, ensure_ascii=False)

    print(f"\n🎉 Saved {len(final_docs)} unique scientific chunks → {OUTPUT_FILE}")
    print("💡 Tip: Add &api_key=YOUR_KEY to params for 10 req/s and higher retmax.")


if __name__ == "__main__":
    main()