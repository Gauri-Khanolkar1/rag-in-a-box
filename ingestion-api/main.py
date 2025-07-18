import os
import json
import time
import uuid
from contextlib import asynccontextmanager
from typing import Optional

import pika
from fastapi import FastAPI, Depends
import pika.exceptions
from pydantic import BaseModel


# ------------------------------
# Configuration and Context
# ------------------------------

class AppConfig:
    RABBITMQ_HOST = os.environ.get("RABBITMQ_HOST", "localhost")  # docker: "rabbitmq", local: "localhost"
    QUEUE_NAME = "ingestion_queue"


class AppContext:
    def __init__(self, config: AppConfig):
        self.config = config
        self.connection: Optional[pika.BlockingConnection] = None
        self.channel: Optional[pika.adapters.blocking_connection.BlockingChannel] = None

    def connect(self, retries=5, delay=3):
        for attempt in range(1, retries + 1):
            try:
                self.connection = pika.BlockingConnection(
                    pika.ConnectionParameters(self.config.RABBITMQ_HOST)
                )
                self.channel = self.connection.channel()
                self.channel.queue_declare(self.config.QUEUE_NAME)
                return
            except pika.exceptions.AMQPConnectionError as e:
                print(f"RabbitMQ connection failed: {e}")
                if attempt < retries:
                    print(f"Retrying in {delay} seconds...")
                    time.sleep(delay)
                else:
                    print("Giving up on connecting to RabbitMQ.")
                    raise


    def close(self):
        if self.connection and self.connection.is_open:
            self.connection.close()

    def publish(self, message: dict):
        if not self.channel:
            raise RuntimeError("RabbitMQ channel is not initialized")
        body = json.dumps(message)
        self.channel.basic_publish(exchange='', routing_key=self.config.QUEUE_NAME, body=body)


# Instantiate config and context globally
app_config = AppConfig()
app_context = AppContext(app_config)


# ------------------------------
# FastAPI App with Lifespan
# ------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    app_context.connect()
    print(f"Connected to RabbitMQ at {app_config.RABBITMQ_HOST}")
    try:
        yield
    finally:
        app_context.close()
        print("RabbitMQ connection closed.")


app = FastAPI(lifespan=lifespan)


# ------------------------------
# Request & Response Models
# ------------------------------

class IngestRequest(BaseModel):
    text: str


class IngestResponse(BaseModel):
    token: str


# ------------------------------
# Route
# ------------------------------

@app.post("/ingest", response_model=IngestResponse)
async def ingest(request: IngestRequest):
    token = str(uuid.uuid4())
    message = {"token": token, "doc": request.text}

    app_context.publish(message)
    print(f"Sent message to queue: {message}")

    return IngestResponse(token=token)