import asyncio
from contextlib import asynccontextmanager
import hashlib
import json
import os
import uuid
from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
import httpx
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct


QDRANT_URL = os.environ.get('QDRANT_URL', "http://localhost:6333")
QDRANT_COLLECTION_NAME = "test"
ENCODER_URL = os.environ.get('ENCODER_URL', "http://localhost:8001")
OLLAMA_URL = os.environ.get('OLLAMA_URL', "http://localhost:11434")

qdrant_client: QdrantClient | None = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    global qdrant_client
    qdrant_client = QdrantClient(url=QDRANT_URL)

    if not qdrant_client.collection_exists(QDRANT_COLLECTION_NAME):
        qdrant_client.create_collection(
            collection_name=QDRANT_COLLECTION_NAME,
            vectors_config=VectorParams(size=384, distance=Distance.COSINE),
        )
    yield
    qdrant_client.close()

class SubmitDocumentRequest(BaseModel):
    document: str

class AskRequest(BaseModel):
    query: str

class AskResponse(BaseModel):
    answer: str

app = FastAPI(lifespan=lifespan)

@app.post("/submit-document")
async def submit_document(request_body: SubmitDocumentRequest):
    encoder_response = httpx.post(f'{ENCODER_URL}/encode', 
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
    encoder_response = httpx.post(f'{ENCODER_URL}/encode', 
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

    with httpx.stream(method="POST", url=f"{OLLAMA_URL}/api/generate", json=payload) as response:
        for line in response.iter_lines():
            if line:
                answer += json.loads(line)['response']

    return {"answer": answer}


@app.post("/ask/stream")
async def ask_stream(request_body: AskRequest):
    """
    Server-Sent-Events stream that sends one JSON chunk per token.
    Media-type 'text/event-stream' keeps the connection open.

    curl -N -s -H "Content-Type: application/json" -H "Accept: text/event-stream" -X POST http://localhost:8000/ask/stream -d '{"query":"What does summer in Seattle look like?"}'
    """

    encoder_response = httpx.post(f'{ENCODER_URL}/encode', 
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

    async def token_generator():
    
        payload = {
            "model": "smollm",
            "prompt":
            f"""Use context below to answer the question at the very end
            Context:
            {context}
            Question:
            {request_body.query}
            """,
            "stream": True
        }
        async with httpx.AsyncClient() as client:
            async with client.stream("POST", f"{OLLAMA_URL}/api/generate",
                                     json=payload, timeout=None) as r:
                async for line in r.aiter_lines():
                    yield json.loads(line)['response']
                    await asyncio.sleep(0.05)  # give event‑loop a chance

    return StreamingResponse(token_generator(),
                             media_type="text/event-stream")