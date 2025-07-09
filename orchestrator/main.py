import hashlib
import json
import uuid
from fastapi import FastAPI
from pydantic import BaseModel
import httpx
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct


app = FastAPI()
qdrant_client = QdrantClient(url="http://localhost:6333")

QDRANT_COLLECTION_NAME = "test"

if not qdrant_client.collection_exists(QDRANT_COLLECTION_NAME):
    qdrant_client.create_collection(
        collection_name=QDRANT_COLLECTION_NAME,
        vectors_config=VectorParams(size=384, distance=Distance.COSINE),
    )

class SubmitDocumentRequest(BaseModel):
    document: str

class AskRequest(BaseModel):
    query: str

class AskResponse(BaseModel):
    answer: str

@app.post("/submit-document")
async def submit_document(request_body: SubmitDocumentRequest):
    encoder_response = httpx.post('http://localhost:8001/encode', 
        json={"text": request_body.document}, 
    ).json()

    qdrant_client.upsert(
        collection_name=QDRANT_COLLECTION_NAME,
        points=[
            PointStruct(
                id=str(uuid.uuid4()),
                vector=encoder_response['embedding'],
                payload={"text": request_body.document}
            )
        ]
    )
    return {}

@app.post("/ask")
async def ask(request_body: AskRequest) -> AskResponse:
    encoder_response = httpx.post('http://localhost:8001/encode', 
        json={"text": request_body.query}, 
    ).json()

    search_result = qdrant_client.query_points(
        collection_name=QDRANT_COLLECTION_NAME,
        query=encoder_response['embedding'],
        with_payload=True,
        limit=3,
        score_threshold=0.3,
    ).points

    print(search_result)
    

    # Extract the 'text' from each payload
    texts = [p.payload['text'] for p in search_result]

    # Optional: remove duplicates while preserving order
    texts = list(dict.fromkeys(texts))

    # Combine into a single string for smolLM context
    context = " ".join(texts)

    print(context)

    OLLAMA_URL = "http://localhost:11434/api/generate"
    payload = {
        "model": "smollm",
        "prompt":
        f"""Use context below to answer the question at the very end
        Context:
        {context}
        Question:
        {request_body.query}
        """
    }

    answer = ""

    with httpx.stream(method="POST", url=OLLAMA_URL, json=payload) as response:
        for line in response.iter_lines():
            if line:
                answer += json.loads(line)['response']

    return {"answer": answer}

