"""
🏃 APEX — Endurance Sports AI Coach
Simple Gradio UI

Run:
    pip install gradio openai chromadb sentence-transformers python-dotenv
    python gradio_app.py
"""

import os
import gradio as gr
import openai
import chromadb
from chromadb.utils import embedding_functions
from sentence_transformers import CrossEncoder
from dotenv import load_dotenv

load_dotenv()

# ─────────────────────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────────────────────
OPENAI_KEY      = os.getenv("OPENAI_API_KEY", "")
DB_PATH         = "./endurance_db"
COLLECTION_NAME = os.getenv("CHROMA_COLLECTION", "endurance_knowledge_base")
EMBED_MODEL     = "text-embedding-3-small"
RERANKER_MODEL  = "BAAI/bge-reranker-base"
CHAT_MODEL      = "gpt-4o-mini"
COARSE_K        = 8
FINAL_K         = 3

if not OPENAI_KEY:
    raise SystemExit("❌ OPENAI_API_KEY not set in .env file")

# ─────────────────────────────────────────────────────────────
# SINGLETONS — loaded once at startup
# ─────────────────────────────────────────────────────────────
print("🧠 Connecting to ChromaDB...")
oai_client   = openai.OpenAI(api_key=OPENAI_KEY)
chroma       = chromadb.PersistentClient(path=DB_PATH)
openai_ef    = embedding_functions.OpenAIEmbeddingFunction(
    api_key=OPENAI_KEY, model_name=EMBED_MODEL
)

try:
    collection = chroma.get_collection(name=COLLECTION_NAME, embedding_function=openai_ef)
    print(f"✅ Loaded {collection.count():,} chunks")
except Exception as e:
    raise SystemExit(f"❌ ChromaDB collection not found: {e}\n   Run: python rag_engine.py --rebuild")

print(f"⏳ Loading reranker ({RERANKER_MODEL})...")
reranker = CrossEncoder(RERANKER_MODEL)
print("✅ Ready")

# ─────────────────────────────────────────────────────────────
# DOMAIN CLASSIFIER
# ─────────────────────────────────────────────────────────────
SPORT_KW = {
    "running":   ["run", "jog", "marathon", "ultra", "5k", "10k", "trail", "pace"],
    "cycling":   ["cycl", "bike", "watt", "ftp", "velo"],
    "triathlon": ["tri", "ironman", "70.3", "brick"],
    "swimming":  ["swim", "pool", "open water"],
    "rowing":    ["row", "erg"],
}

def detect_sport(query: str):
    q = query.lower()
    return next((s for s, kws in SPORT_KW.items() if any(k in q for k in kws)), None)

# ─────────────────────────────────────────────────────────────
# QUERY REWRITER
# ─────────────────────────────────────────────────────────────
def rewrite_query(user_msg: str) -> str:
    resp = oai_client.chat.completions.create(
        model="gpt-4o-mini",
        temperature=0.1,
        messages=[{
            "role": "user",
            "content": (
                "You are an expert endurance sports data engineer. "
                "Convert the user's conversational message into a highly specific "
                "search query for a database of scientific sports abstracts and workout logs.\n\n"
                f'User message: "{user_msg}"\n\n'
                "Output ONLY the rewritten search query. No quotes, no explanation."
            )
        }]
    )
    return resp.choices[0].message.content.strip()

# ─────────────────────────────────────────────────────────────
# RETRIEVAL — vector search + rerank
# ─────────────────────────────────────────────────────────────
def retrieve(query: str, sport: str | None) -> list[dict]:
    kwargs = dict(
        query_texts=[query],
        n_results=COARSE_K,
        include=["documents", "metadatas", "distances"],
    )
    if sport:
        kwargs["where"] = {"sport_type": {"$in": [sport, "multi", "other"]}}

    try:
        res = collection.query(**kwargs)
    except Exception:
        kwargs.pop("where", None)
        res = collection.query(**kwargs)

    docs  = res["documents"][0]
    metas = res["metadatas"][0]

    if not docs:
        return []

    scores = reranker.predict([[query, d] for d in docs])
    ranked = sorted(zip(scores, docs, metas), key=lambda x: x[0], reverse=True)

    return [
        {"content": doc, "metadata": meta, "score": float(score)}
        for score, doc, meta in ranked[:FINAL_K]
    ]

# ─────────────────────────────────────────────────────────────
# SYSTEM PROMPT
# ─────────────────────────────────────────────────────────────
SYSTEM_PROMPT = """\
You are APEX — an elite AI endurance coach and sports scientist with expertise in
triathlon, marathon, cycling, swimming, exercise physiology, sports nutrition, and training methodology.

Rules:
- Answer using ONLY the provided context chunks.
- Cite source type (scientific study vs workout log) where relevant.
- Give practical, actionable advice.
- If context doesn't cover the question, say so clearly.
- Use markdown formatting for clarity.
"""

# ─────────────────────────────────────────────────────────────
# MAIN CHAT FUNCTION
# ─────────────────────────────────────────────────────────────
def chat(user_message: str, history: list) -> tuple[str, list, str]:
    """
    Returns: (answer, updated_history, sources_text)
    """
    if not user_message.strip():
        return "", history, ""

    # 1. Rewrite query
    search_query = rewrite_query(user_message)

    # 2. Retrieve
    sport  = detect_sport(user_message)
    chunks = retrieve(search_query, sport)

    # 3. Build sources display
    sources_md = f"**🔍 Rewritten query:** `{search_query}`\n\n"
    if sport:
        sources_md += f"**🏃 Sport detected:** {sport}\n\n"
    sources_md += "**📚 Sources used:**\n\n"
    for i, c in enumerate(chunks, 1):
        m = c["metadata"]
        sources_md += (
            f"**#{i}** · {m.get('document_type','?')} · "
            f"sport={m.get('sport_type','?')} · "
            f"score={c['score']:.3f}\n\n"
            f"> {c['content'][:200]}...\n\n"
        )

    # 4. Build messages with history
    context = "\n\n---\n\n".join(
        f"[{c['metadata'].get('document_type','?')} | sport={c['metadata'].get('sport_type','?')}]\n{c['content']}"
        for c in chunks
    )
    messages = [{"role": "system", "content": SYSTEM_PROMPT + f"\n\nCONTEXT:\n{context}"}]
    for human, assistant in history[-3:]:
        messages.append({"role": "user",      "content": human})
        messages.append({"role": "assistant", "content": assistant})
    messages.append({"role": "user", "content": user_message})

    # 5. Generate (streaming)
    answer = ""
    stream = oai_client.chat.completions.create(
        model=CHAT_MODEL,
        messages=messages,
        temperature=0.3,
        max_tokens=600,
        stream=True,
    )
    for chunk in stream:
        delta = chunk.choices[0].delta.content or ""
        answer += delta

    # 6. Update history as tuples (classic Gradio format)
    history.append((user_message, answer))

    return answer, history, sources_md

# ─────────────────────────────────────────────────────────────
# GRADIO UI
# ─────────────────────────────────────────────────────────────
EXAMPLES = [
    "What does science say about zone 2 training for marathon prep?",
    "How should I fuel a 4-hour cycling ride?",
    "I'm overtrained — what are the signs and recovery protocol?",
    "What's the optimal taper strategy for an Ironman?",
    "How does altitude training affect VO2 max?",
    "What's a normal heart rate for a 10km run?",
]

with gr.Blocks(title="APEX — Endurance AI Coach") as demo:

    gr.Markdown("""
    # 🏃 APEX — Endurance Sports AI Coach
    *Powered by RAG: scientific papers + real athlete workout data*
    Ask about **training · nutrition · recovery · physiology · biomechanics**
    """)

    with gr.Row():
        with gr.Column(scale=2):
            chatbot = gr.Chatbot(
                label="Coach APEX",
                height=520,
            )
            with gr.Row():
                msg_box = gr.Textbox(
                    placeholder="Ask anything about endurance sports...",
                    show_label=False,
                    scale=4,
                    container=False,
                )
                send_btn = gr.Button("Send", variant="primary", scale=1)

            gr.Examples(
                examples=EXAMPLES,
                inputs=msg_box,
                label="Quick Prompts",
            )

            clear_btn = gr.Button("🗑 Clear Chat", variant="secondary")

        with gr.Column(scale=1):
            sources_box = gr.Markdown(
                value="*Sources will appear here after your first question.*",
                label="Retrieved Sources",
            )

    # ── State ──────────────────────────────────────────────
    state = gr.State([])   # chat history

    # ── Event handlers ─────────────────────────────────────
    def on_send(user_msg, history):
        answer, updated_history, sources_md = chat(user_msg, history)
        # chatbot expects list of (user, bot) tuples
        return updated_history, updated_history, "", sources_md

    send_btn.click(
        fn=on_send,
        inputs=[msg_box, state],
        outputs=[chatbot, state, msg_box, sources_box],
    )
    msg_box.submit(
        fn=on_send,
        inputs=[msg_box, state],
        outputs=[chatbot, state, msg_box, sources_box],
    )
    clear_btn.click(
        fn=lambda: ([], [], "*Sources will appear here after your first question.*"),
        outputs=[chatbot, state, sources_box],
    )

if __name__ == "__main__":
    demo.launch(share=False, theme=gr.themes.Soft())