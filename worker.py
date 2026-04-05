import os
import fitz
import pickle
import json
import re
import math
from collections import Counter
from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------------
# TF-IDF implementation (zero external dependencies, ~0 MB RAM overhead)
# Replaces sentence-transformers (~400MB) + faiss-cpu (~50MB)
# ---------------------------------------------------------------------------

def tokenize(text):
    """Simple tokenizer: lowercase, split on non-alphanumeric, remove stopwords."""
    STOPWORDS = {
        'the','a','an','is','are','was','were','be','been','being','have','has','had',
        'do','does','did','will','would','could','should','may','might','shall','can',
        'of','in','to','for','with','on','at','by','from','as','into','through','during',
        'before','after','above','below','between','under','again','further','then','once',
        'and','but','or','nor','not','no','so','if','than','that','this','these','those',
        'it','its','he','she','they','we','you','i','me','my','your','his','her','their',
        'our','what','which','who','whom','how','when','where','why','all','each','every',
        'both','few','more','most','other','some','such','only','own','same','too','very',
    }
    words = re.findall(r'[a-z0-9]+', text.lower())
    return [w for w in words if w not in STOPWORDS and len(w) > 1]

def build_tfidf_index(chunks):
    """Build a TF-IDF index from a list of text chunks."""
    # Document frequency
    df = Counter()
    chunk_tokens = []
    for chunk in chunks:
        tokens = tokenize(chunk)
        chunk_tokens.append(tokens)
        unique_tokens = set(tokens)
        for t in unique_tokens:
            df[t] += 1

    n_docs = len(chunks)
    # IDF
    idf = {}
    for term, freq in df.items():
        idf[term] = math.log((n_docs + 1) / (freq + 1)) + 1

    # TF-IDF vectors (sparse, stored as dicts)
    tfidf_vectors = []
    for tokens in chunk_tokens:
        tf = Counter(tokens)
        max_tf = max(tf.values()) if tf else 1
        vec = {}
        for term, count in tf.items():
            if term in idf:
                vec[term] = (count / max_tf) * idf[term]
        # Normalize
        norm = math.sqrt(sum(v*v for v in vec.values())) if vec else 1
        vec = {k: v/norm for k, v in vec.items()}
        tfidf_vectors.append(vec)

    return {"idf": idf, "vectors": tfidf_vectors}

def tfidf_search(query, chunks, index, top_k=8):
    """Search chunks using TF-IDF cosine similarity."""
    idf = index["idf"]
    vectors = index["vectors"]

    # Query vector
    tokens = tokenize(query)
    tf = Counter(tokens)
    max_tf = max(tf.values()) if tf else 1
    q_vec = {}
    for term, count in tf.items():
        if term in idf:
            q_vec[term] = (count / max_tf) * idf[term]
    norm = math.sqrt(sum(v*v for v in q_vec.values())) if q_vec else 1
    q_vec = {k: v/norm for k, v in q_vec.items()}

    # Cosine similarity
    scores = []
    for i, doc_vec in enumerate(vectors):
        score = sum(q_vec.get(t, 0) * doc_vec.get(t, 0) for t in q_vec)
        scores.append((score, i))

    scores.sort(reverse=True)
    top_k = min(top_k, len(scores))
    return [(chunks[idx], idx, score) for score, idx in scores[:top_k] if score > 0]


# ---------------------------------------------------------------------------
# OCR helpers
# ---------------------------------------------------------------------------
try:
    from PIL import Image
    import pytesseract
    import io
    HAS_OCR = True
except ImportError:
    HAS_OCR = False
    print("[worker] pytesseract/Pillow not found — OCR disabled, text-only extraction.")


def extract_page_text(page, doc):
    """Extract text from a page, including OCR on embedded images."""
    text = page.get_text("text")

    if HAS_OCR:
        try:
            image_list = page.get_images(full=True)
            for img_info in image_list:
                xref = img_info[0]
                try:
                    base_image = doc.extract_image(xref)
                    image_bytes = base_image["image"]
                    image = Image.open(io.BytesIO(image_bytes))
                    if image.width > 50 and image.height > 50:
                        ocr_text = pytesseract.image_to_string(image)
                        if ocr_text.strip():
                            text += "\n[Image content]: " + ocr_text.strip()
                except Exception:
                    continue
        except Exception:
            pass

        if len(text.strip()) < 100:
            try:
                pix = page.get_pixmap(dpi=200)
                img = Image.open(io.BytesIO(pix.tobytes("png")))
                ocr_text = pytesseract.image_to_string(img)
                if ocr_text.strip():
                    text = ocr_text.strip()
            except Exception:
                pass

    return text.strip()


def process_pdf(path: str, file_id: str) -> str:
    """Extract text from PDF (with OCR), chunk, build TF-IDF index, and store."""
    if not os.path.exists(path):
        raise FileNotFoundError(f"PDF file not found: {path}")

    all_text = []
    with fitz.open(path) as doc:
        for page_num, page in enumerate(doc):
            page_text = extract_page_text(page, doc)
            if page_text:
                all_text.append(f"[Page {page_num + 1}]\n{page_text}")

    text = "\n\n".join(all_text)

    if not text.strip():
        raise ValueError("No extractable text found in this PDF.")

    # Chunk text broadly (2000 chars with 400 char overlap) to preserve massive tables/paragraphs
    chunk_size = 2000
    overlap = 400
    chunks = []
    for i in range(0, len(text), chunk_size - overlap):
        chunk = text[i : i + chunk_size]
        if chunk.strip():
            chunks.append(chunk)

    if not chunks:
        raise ValueError("Could not create text chunks from this PDF.")

    # Build TF-IDF index (replaces FAISS + sentence-transformers)
    index = build_tfidf_index(chunks)

    # Save
    os.makedirs("./vectorstores", exist_ok=True)
    with open(f"./vectorstores/{file_id}.pkl", "wb") as f:
        pickle.dump({"chunks": chunks, "index": index}, f)

    return "done"