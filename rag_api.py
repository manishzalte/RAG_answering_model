# filename: main.py
from fastapi import FastAPI, Body, HTTPException
from sentence_transformers import SentenceTransformer, util
from transformers import pipeline
import json
import re
import torch

# --- INITIALIZATION ---

app = FastAPI(
    title="Simple RAG API",
    description="An API for uploading context and asking questions against it.",
    version="1.0.0",
)

# Load models
print("Loading embedding model...")
# Forcing CPU for SentenceTransformer as well for consistency
embedder = SentenceTransformer("all-MiniLM-L6-v2", device="cpu")

print("Loading LLM model (phi-2)...")
llm = pipeline(
    "text-generation",
    model="TinyLlama/TinyLlama-1.1B-Chat-v1.0",
    # FIX: Force CPU execution to avoid MPS instability on Apple Silicon.
    device="cpu",
    trust_remote_code=True,
    # Use bfloat16 on CPU for a good balance of speed and precision.
    # Note: The new argument is 'dtype', not 'torch_dtype'.
    dtype=torch.bfloat16
)
print("Models loaded successfully.")


# In-memory storage
contexts = []
context_embeddings = []

# --- API ENDPOINTS ---

@app.post("/upload_context")
def upload_context(doc: str = Body(..., embed=True, description="The document text to be stored.")):
    if not doc or not isinstance(doc, str) or len(doc.strip()) == 0:
        raise HTTPException(status_code=400, detail="Document cannot be empty.")
        
    contexts.append(doc)
    # Ensure embeddings are on the CPU
    embedding = embedder.encode(doc, convert_to_tensor=True).cpu()
    context_embeddings.append(embedding)
    
    return {"status": "Context uploaded successfully", "total_docs": len(contexts)}

@app.post("/ask")
def ask(question: str = Body(..., embed=True, description="The question to ask about the stored contexts.")):
    if not contexts:
        raise HTTPException(status_code=400, detail="No context has been uploaded yet.")

    # 1. RETRIEVAL
    query_emb = embedder.encode(question, convert_to_tensor=True).cpu()
    scores = [util.pytorch_cos_sim(query_emb, emb).item() for emb in context_embeddings]
    best_idx = scores.index(max(scores))
    best_context = contexts[best_idx]

    # 2. PROMPT & GENERATION
    prompt = (
        "You are a strict and precise information extractor. Your task is to analyze the provided document "
        "and answer the user's question based ONLY on the information present in that document.\n"
        "Do not infer, guess, or use any external knowledge.\n"
        "Your response MUST be a single JSON object with a single key: 'answer'.\n"
        "If the information is available, the value should be the extracted answer.\n"
        "If the information is not available in the document, the value must be the string 'Not Found'.\n\n"
        f"--- Document ---\n{best_context}\n\n"
        f"--- Question ---\n{question}\n\n"
        "--- JSON Output ---\n"
    )

    # The warning "Setting `pad_token_id` to `eos_token_id`..." is normal.
    generated_outputs = llm(prompt, max_new_tokens=150, return_full_text=False)
    result_text = generated_outputs[0]["generated_text"]
   
    # 3. PARSING
    match = re.search(r"\{.*\}", result_text, re.DOTALL)
    
    if match:
        json_string = match.group(0)
        try:
            parsed_answer = json.loads(json_string)
        except json.JSONDecodeError:
            return {
                "error": "Failed to parse JSON from model output.",
                "raw_output": result_text,
                "context_used": best_context
            }
    else:
        return {
            "error": "No JSON object found in model output.",
            "raw_output": result_text,
            "context_used": best_context
        }

    response = parsed_answer
    response["context_used"] = best_context
    response["similarity_score"] = max(scores)
    
    return response