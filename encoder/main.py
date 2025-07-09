
from fastapi import FastAPI
from pydantic import BaseModel
from sentence_transformers import SentenceTransformer


app = FastAPI()

model = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")

class EncodeRequest(BaseModel):
    text: str


class EncodeResponse(BaseModel):
    embedding: list[float]


@app.post('/encode')
async def encode(request_body: EncodeRequest) -> EncodeResponse:
    embedding = (
        model
        .encode(request_body.text, convert_to_numpy=True)
        .tolist()
    )
    return {'embedding': embedding}
