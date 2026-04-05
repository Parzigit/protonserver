import os
import re
import pickle
from groq import Groq
from dotenv import load_dotenv
from worker import tfidf_search

load_dotenv()

# ---------------------------------------------------------------------------
# Groq client (free tier — llama-3.3-70b-versatile)
# ---------------------------------------------------------------------------
client = Groq(api_key=os.getenv("GROQ_API_KEY"))
MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")


def extract_page_number(chunk_text):
    """Extract page number from a chunk that starts with [Page N]."""
    match = re.match(r'\[Page (\d+)\]', chunk_text)
    if match:
        return int(match.group(1))
    return None


def answer_question(job_id: str, question: str, history: list = None):
    """RAG-powered Q&A using TF-IDF retrieval + Groq LLM generation.
    Returns dict with 'answer' and 'sources'."""
    if history is None:
        history = []
    
    try:
        vec_path = f"./vectorstores/{job_id}.pkl"
        if not os.path.exists(vec_path):
            return {
                "answer": "This PDF is still being processed. Please wait a moment and try again.",
                "sources": []
            }

        with open(vec_path, "rb") as f:
            data = pickle.load(f)

        # Support both old format (tuple) and new format (dict)
        if isinstance(data, dict):
            chunks = data["chunks"]
            index = data["index"]
        else:
            # Old format: (chunks, faiss_index) — fallback
            chunks = data[0]
            # Can't use old FAISS index with TF-IDF, just do substring matching
            from worker import build_tfidf_index
            index = build_tfidf_index(chunks)

        # Retrieve top-k relevant chunks via TF-IDF (chunks are highly dense 2000 chars now)
        results = tfidf_search(question, chunks, index, top_k=5)
        
        if not results:
            return {
                "answer": "I couldn't find relevant content in the document for your question. Try rephrasing or asking about a different topic.",
                "sources": []
            }

        context_chunks = [r[0] for r in results]
        context = "\n---\n".join(context_chunks)

        # Build sources list with page numbers and preview text
        sources = []
        seen_pages = set()
        for chunk_text, chunk_idx, score in results:
            page_num = extract_page_number(chunk_text)
            if page_num and page_num not in seen_pages and score > 0.05:
                seen_pages.add(page_num)
                # Clean preview: remove [Page N] prefix, truncate
                preview = re.sub(r'^\[Page \d+\]\n?', '', chunk_text).strip()
                preview = preview[:200] + "..." if len(preview) > 200 else preview
                sources.append({
                    "page": page_num,
                    "text": preview,
                    "relevance": round(score, 3)
                })

        # Sort sources by page number
        sources.sort(key=lambda s: s["page"])

        # Build messages list
        messages = [
            {
                "role": "system",
                "content": (
                    "You are ProtonPDF AI, an expert document analyst. "
                    "You answer questions based ONLY on the provided document context.\n\n"
                    "RESPONSE LENGTH RULES — follow these strictly:\n"
                    "- For simple factual questions (who, when, what year, yes/no): give a brief 1-3 sentence answer.\n"
                    "- For 'explain', 'describe', 'how does', 'elaborate' questions: give a detailed, multi-paragraph answer.\n"
                    "- For 'list', 'what are the' questions: provide a complete numbered or bulleted list.\n"
                    "- For formula/equation questions: reproduce ALL formulas found in context, with full variable definitions.\n"
                    "- For summary questions: provide a comprehensive summary covering all key points.\n"
                    "- NEVER truncate or cut short. If the user asks for detail, provide ALL relevant detail from the context.\n\n"
                    "FORMATTING RULES:\n"
                    "- ALWAYS use standard Markdown syntax for tables. Do not use pseudo-tables.\n"
                    "- ALWAYS use exactly `$` for inline math formatting (e.g., $ E = mc^2 $).\n"
                    "- ALWAYS use exactly `$$` on separate lines for block physics/math formulas. DO NOT use `\\[` or `\\]`.\n"
                    "- Use **bold** for key terms and headings.\n"
                    "- Use bullet points and numbered lists for clarity.\n"
                    "- Include page references when available (e.g., 'As stated on Page 3...').\n"
                    "- If the context contains [Image content] describing formulas, treat them as regular text.\n\n"
                    "If the context doesn't contain the answer, say so clearly and suggest what the user might search for instead."
                ),
            }
        ]

        # Append previous conversation history
        for msg in history:
            messages.append({
                "role": msg.get("role", "user"),
                "content": msg.get("content", "")
            })

        # Append the new user question and context
        messages.append({
            "role": "user",
            "content": (
                f"**Document Context (from retrieved pages):**\n\n{context}\n\n"
                f"---\n\n**User Question:** {question}\n\n"
                "Provide a thorough answer based on the context above. "
                "Match your response length to the complexity of the question."
            ),
        })

        # Generate answer via Groq
        response = client.chat.completions.create(
            model=MODEL,
            messages=messages,
            temperature=0.3,
            max_tokens=4096,
        )

        return {
            "answer": response.choices[0].message.content,
            "sources": sources
        }

    except Exception as e:
        print(f"[ERROR in answer_question] {e}")
        return {
            "answer": f"Sorry, I encountered an error: {str(e)}",
            "sources": []
        }
