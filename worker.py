import rq.timeouts
rq.timeouts.DEATH_PENALTY_CLASS = None  
print("Death penalty class:", rq.timeouts.DEATH_PENALTY_CLASS)
import os, fitz, faiss, pickle
from redis import Redis
from rq import SimpleWorker, Queue, Connection
from rq_win import WindowsWorker
from sentence_transformers import SentenceTransformer
redis_conn = Redis()
model = SentenceTransformer('all-MiniLM-L6-v2')
def process_pdf(path, file_id):
    with fitz.open(path) as doc:
        text="\n".join([page.get_text() for page in doc])
    text = text.replace("\n", " ").strip()
    if not text:
        raise ValueError("No extractable text in PDF.")
    chunks=[text[i:i+250] for i in range(0, len(text),250)]
    embeddings=model.encode(chunks, normalize_embeddings=True)
    index = faiss.IndexFlatIP(embeddings.shape[1])
    index.add(embeddings)
    os.makedirs("./vectorstores", exist_ok=True)
    with open(f"./vectorstores/{file_id}.pkl", "wb") as f:
        pickle.dump((chunks, index),f)
    return "done"

if __name__ == '__main__':
    with Connection(redis_conn):
        q = Queue('pdf-tasks')
        worker = WindowsWorker([q], connection=redis_conn) 
        worker.work()
