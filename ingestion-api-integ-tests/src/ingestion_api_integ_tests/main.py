from collections.abc import Generator
import logging
import os
import re
import time
from typing import Any, Literal, Mapping, TypedDict
import httpx
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from .models import IngestionStatus


INGESION_API_URL = os.environ.get('INGESION_API_URL', 'http://localhost:8002')
QDRANT_URL = os.environ.get('QDRANT_URL', "http://localhost:6333")
QDRANT_COLLECTION_NAME = "test"

POSTGRES_HOST = os.environ.get("POSTGRES_HOST", "localhost")
POSTGRES_PORT = os.environ.get("POSTGRES_PORT", "5432")
POSTGRES_DB = os.environ.get("POSTGRES_DB", "postgres")
POSTGRES_USER = os.environ.get("POSTGRES_USER", "postgres")
POSTGRES_PASSWORD = os.environ.get("POSTGRES_PASSWORD", "mysecretpassword")
QDRANT_HOST = os.environ.get("QDRANT_HOST", "localhost")
QDRANT_PORT = 6333


logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

logger = logging.getLogger(__name__)


class StatusRequest(TypedDict):
    token: str


class StatusResponse(TypedDict):
    status: Literal['IN_PROGRESS', 'COMPLETED', 'FAILED']
    error_message: str | None


def wait_for_status(token: str, *, timeout: int=20) -> StatusResponse:
    deadline = time.time() + timeout
    params: StatusRequest = {
        'token': token
    }
    while time.time() < deadline:
        response: StatusResponse = httpx.post(f"{INGESION_API_URL}/status", json=params, timeout=5).json()
        logger.info(f"Polling Ingestion Status: {response = }")
        if response["status"] in {"COMPLETED", "FAILED"}:
            return response
        time.sleep(1)
    raise TimeoutError(f"{token} not finished in {timeout}s")


@pytest.fixture
def cleanup_ingestion() -> Generator[list[str], None, None]:
    tokens = []
    yield tokens  # give the test access to `tokens`

    engine_postgres = create_engine(f'postgresql://{POSTGRES_USER}:{POSTGRES_PASSWORD}@{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}')
    Session_postgres = sessionmaker(bind=engine_postgres)
    session_postgres = Session_postgres()

    if tokens:
        for token in tokens:
            session_postgres.query(IngestionStatus).filter(IngestionStatus.id == token).delete()
            logger.info(f"Record with token: {token} was removed from Database")

            # TODO: add qdrant delete for the token in collection test
            httpx.post(f"http://{QDRANT_HOST}:{QDRANT_PORT}/collections/{QDRANT_COLLECTION_NAME}/points/delete", json={'points': [token]})
        session_postgres.commit()


def test_ingestion_api_returns_uuid_token_on_successful_ingest(cleanup_ingestion: list[str]) -> None:
    
    response = httpx.post(f"{INGESION_API_URL}/ingest", json={'text': 'testing'})
    assert response.status_code == 200
    response_data: Mapping[str, Any] = response.json()
    assert 'token' in response_data.keys(), "IngestionAPI's submit-document call does not return any token"
    token = response_data['token']
    cleanup_ingestion.append(token)

    uuid_regex = re.compile(r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}')
    assert uuid_regex.match(token), "IngestionAPI's submit-document call does not return valid UUID"

    status_response = wait_for_status(token=token)
    assert status_response['status'] == 'COMPLETED'
    

