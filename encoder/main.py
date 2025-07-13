
from fastapi import FastAPI
from pydantic import BaseModel
from fastembed import TextEmbedding


app = FastAPI()

model = TextEmbedding("sentence-transformers/all-MiniLM-L6-v2")

class EncodeRequest(BaseModel):
    text: str


class EncodeResponse(BaseModel):
    embedding: list[float]


@app.post('/encode')
async def encode(request_body: EncodeRequest) -> EncodeResponse:
    embedding = next(iter(model.embed(request_body.text))).tolist()
    return {'embedding': embedding}
