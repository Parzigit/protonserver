import os
import pickle
import faiss
import google.generativeai as genai
from dotenv import load_dotenv
from sentence_transformers import SentenceTransformer

load_dotenv()
genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))

model = genai.GenerativeModel("gemini-1.5-flash")

embedder = SentenceTransformer('all-MiniLM-L6-v2')

def answer_question(job_id, question):
    try:
        with open(f"./vectorstores/{job_id}.pkl", "rb") as f:
            chunks, index = pickle.load(f)

        q_embedding = embedder.encode([question])
        top_k = 5
        _, indices = index.search(q_embedding, top_k)
        context_chunks = [chunks[i] for i in indices[0]]
        context = "\n".join(context_chunks)

        prompt = f"""
        You are a helpful assistant answering questions based on a user-uploaded document.
        Context:
        {context}
        Question: {question}
        Instructions:
        - Answer based only on the above context.
        - If asked for specific content (like "100 lines"), extract and return that many SRTICTLY lines from context.
        - If the question is straightforward, give a short or one-word answer.
        - If the document doesn't contain the answer, say "Not mentioned in the document."
        """
        response = model.generate_content(prompt)
        return response.text

    except Exception as e:
        print(f"[ERROR in answer_question] {e}")
        return "Error processing the question."
