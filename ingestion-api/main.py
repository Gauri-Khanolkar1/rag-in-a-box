import os
import json
import time
import uuid
from contextlib import asynccontextmanager
from typing import Literal, Optional

import pika
import pika.exceptions
import psycopg2
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel


# ------------------------------
# Configuration
# ------------------------------

class AppConfig:
    RABBITMQ_HOST = os.environ.get("RABBITMQ_HOST", "localhost")
    QUEUE_NAME = "ingestion_queue"
    POSTGRES_HOST = os.environ.get("POSTGRES_HOST", "localhost")
    POSTGRES_PORT = os.environ.get("POSTGRES_PORT", "5432")
    POSTGRES_DB = os.environ.get("POSTGRES_DB", "postgres")
    POSTGRES_USER = os.environ.get("POSTGRES_USER", "postgres")
    POSTGRES_PASSWORD = os.environ.get("POSTGRES_PASSWORD", "mysecretpassword")


# ------------------------------
# Application Context
# ------------------------------

class AppContext:
    def __init__(self, config: AppConfig):
        self.config = config
        self.rabbit_conn: Optional[pika.BlockingConnection] = None
        self.rabbit_channel: Optional[pika.adapters.blocking_connection.BlockingChannel] = None
        self.pg_conn: Optional[psycopg2.extensions.connection] = None
        self.pg_cursor: Optional[psycopg2.extensions.cursor] = None

    def publish(self, message: dict) -> None:
        """Open a short-lived connection, publish, close - avoids heartbeat timeouts."""
        try:
            with pika.BlockingConnection(
                pika.ConnectionParameters(
                    self.config.RABBITMQ_HOST,
                    heartbeat=0              # disable heartbeats for the short-lived conn
                )
            ) as conn:
                channel = conn.channel()
                channel.queue_declare(queue=self.config.QUEUE_NAME)
                channel.basic_publish(
                    exchange='',
                    routing_key=self.config.QUEUE_NAME,
                    body=json.dumps(message),
                    properties=pika.BasicProperties(
                        delivery_mode=2      # make message persistent
                    )
                )
        except pika.exceptions.AMQPError as e:
            raise RuntimeError(f"RabbitMQ publish failed: {e}") from e

    def connect_postgres(self):
        self.pg_conn = psycopg2.connect(
            host=self.config.POSTGRES_HOST,
            port=self.config.POSTGRES_PORT,
            database=self.config.POSTGRES_DB,
            user=self.config.POSTGRES_USER,
            password=self.config.POSTGRES_PASSWORD
        )
        self.pg_cursor = self.pg_conn.cursor()

    def _create_postgres_table_if_not_exists(self):
        self.pg_cursor.execute('''
            CREATE TABLE IF NOT EXISTS ingestion_status (
                id UUID PRIMARY KEY,
                status TEXT CHECK (status IN ('IN_PROGRESS', 'COMPLETED', 'FAILED')),
                error_message TEXT,
                updated_at TIMESTAMP DEFAULT NOW()
            );
        ''')
        self.pg_conn.commit()
        print("Connected to PostgreSQL and ensured table exists.")

    def close(self):
        if self.rabbit_conn and self.rabbit_conn.is_open:
            self.rabbit_conn.close()
            print("RabbitMQ connection closed.")

        if self.pg_cursor:
            self.pg_cursor.close()
        if self.pg_conn:
            self.pg_conn.close()
            print("PostgreSQL connection closed.")


# ------------------------------
# Global Instances
# ------------------------------

app_config = AppConfig()
app_context = AppContext(app_config)


# ------------------------------
# FastAPI with Lifespan
# ------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        app_context.connect_postgres()
        app_context._create_postgres_table_if_not_exists()
        yield
    finally:
        app_context.close()


app = FastAPI(lifespan=lifespan)


# ------------------------------
# Request & Response Models
# ------------------------------

class IngestRequest(BaseModel):
    text: str

class IngestResponse(BaseModel):
    token: str

class StatusRequest(BaseModel):
    token: str

class StatusResponse(BaseModel):
    status: Literal["IN_PROGRESS", "FAILED", "COMPLETED"]
    error_message: Optional[str] = None

# ------------------------------
# Route
# ------------------------------

@app.post("/ingest", response_model=IngestResponse)
async def ingest(request: IngestRequest):
    token = str(uuid.uuid4())
    message = {"token": token, "doc": request.text}

    try:
        app_context.publish(message)
        print(f"Published message: {message}")

        # Insert into DB with status IN_PROGRESS
        app_context.pg_cursor.execute(
            """
            INSERT INTO ingestion_status (id, status)
            VALUES (%s, %s)
            """,
            (token, 'IN_PROGRESS')
        )
        app_context.pg_conn.commit()
        print(f"Inserted status IN_PROGRESS for token: {token}")

    except Exception as e:
        print(f"Publishing failed: {e}")

        # Insert into DB with status FAILED
        app_context.pg_cursor.execute(
            """
            INSERT INTO ingestion_status (id, status, error_message)
            VALUES (%s, %s, %s)
            """,
            (token, 'FAILED', str(e))
        )
        app_context.pg_conn.commit()
        print(f"Inserted status FAILED for token: {token}")

    return IngestResponse(token=token)

@app.post("/status", response_model=StatusResponse)
async def status(request: StatusRequest):
    # take the token from request and check for it exists in postgres and return the status in response
    try:
        app_context.pg_cursor.execute(
            """
            SELECT status FROM ingestion_status
            WHERE id = (%s)
            """,
            (request.token,)
        )
        result = app_context.pg_cursor.fetchone()
        # select returned empty then return wrong token error message to user
        if status:
            return StatusResponse(status=result[0])
        else:
            return StatusResponse(status=None, error_message="Wrong token")
    except Exception as e:
        # if select threw an exception? That means table does not exist?
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
    
