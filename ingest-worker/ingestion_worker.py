import json
import logging
import os
import sys
from typing import Optional, Self
import uuid
import pika
import pika.adapters.blocking_connection
import pika.exceptions
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct
from fastembed import TextEmbedding
import tenacity
import psycopg2

logging.basicConfig(stream=sys.stderr, level=logging.INFO)
logger = logging.getLogger(__name__)

class AppConfig:
    QDRANT_URL = os.environ.get("QDRANT_URL", "http://localhost:6333") 
    QDRANT_COLLECTION_NAME = "test"
    EMBEDDING_MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
    VECTOR_SIZE = 384
    VECTOR_DISTANCE = Distance.COSINE
    RABBITMQ_HOST = os.environ.get("RABBITMQ_HOST", "localhost")
    QUEUE_NAME = "ingestion_queue"
    POSTGRES_HOST = os.environ.get("POSTGRES_HOST", "localhost")
    POSTGRES_PORT = os.environ.get("POSTGRES_PORT", "5432")
    POSTGRES_DB = os.environ.get("POSTGRES_DB", "postgres")
    POSTGRES_USER = os.environ.get("POSTGRES_USER", "postgres")
    POSTGRES_PASSWORD = os.environ.get("POSTGRES_PASSWORD", "mysecretpassword")


class Application:
    def __init__(self, config: AppConfig):
        self.config = config
        self.qdrant = None
        self.model = None
        self.rabbit_conn: Optional[pika.BlockingConnection] = None
        self.rabbit_channel: Optional[pika.adapters.blocking_connection.BlockingChannel] = None
        self.pg_conn: Optional[psycopg2.extensions.cursor] = None
        self.pg_cursor: Optional[psycopg2.extensions.cursor] = None

    @tenacity.retry(
            retry=tenacity.retry_if_exception_type(pika.exceptions.AMQPConnectionError), 
            wait=tenacity.wait_fixed(3), 
            stop=tenacity.stop_after_attempt(5),
            before=tenacity.before_log(logger, logging.DEBUG),
            after=tenacity.after_log(logger, logging.DEBUG)
        )
    def _connect_rabbitmq(self: Self) -> pika.BlockingConnection:
        return pika.BlockingConnection(
            pika.ConnectionParameters(self.config.RABBITMQ_HOST)
        )
    
    def _connect_postgres(self):
        self.pg_conn = psycopg2.connect(
            host=self.config.POSTGRES_HOST,
            port=self.config.POSTGRES_PORT,
            database=self.config.POSTGRES_DB,
            user=self.config.POSTGRES_USER,
            password=self.config.POSTGRES_PASSWORD
        )
        self.pg_cursor = self.pg_conn.cursor()
        print("Connected to PostgreSQL")

    def _update_postgres_success(self, token: uuid):
        self.pg_cursor.execute('''
            UPDATE ingestion_status
            SET status = 'COMPLETED'
            WHERE id = (%s) and status = 'IN_PROGRESS'
        ''',(str(token),))
        self.pg_conn.commit()
        print('Updated status in Postgres')

    def _update_postgres_failure(self, token: uuid):
        self.pg_cursor.execute('''
            UPDATE ingestion_status
            SET status = 'FAILED'
            WHERE id = (%s) and status = 'IN_PROGRESS'
        ''',str(token),)
        self.pg_conn.commit()
        print('Updated status in Postgres')

    def initialize_services(self):
        # Qdrant
        self.qdrant = QdrantClient(url=self.config.QDRANT_URL)
        if not self.qdrant.collection_exists(self.config.QDRANT_COLLECTION_NAME):
            self.qdrant.create_collection(
                collection_name=self.config.QDRANT_COLLECTION_NAME,
                vectors_config=VectorParams(
                    size=self.config.VECTOR_SIZE,
                    distance=self.config.VECTOR_DISTANCE
                )
            )

        # Embedding model
        self.model = TextEmbedding(self.config.EMBEDDING_MODEL_NAME)

        # RabbitMQ
        self.connection = self._connect_rabbitmq()
        self.channel = self.connection.channel()
        self.channel.queue_declare(queue=self.config.QUEUE_NAME)
        self.channel.basic_qos(prefetch_count=1)

    def encode(self, text: str) -> list[float]:
        return next(iter(self.model.embed(text))).tolist()

    def store_in_qdrant(self, text: str, embedding: list[float], token: uuid) -> None:
        self.qdrant.upsert(
            collection_name=self.config.QDRANT_COLLECTION_NAME,
            points=[
                PointStruct(
                    id=token,
                    vector=embedding,
                    payload={"text": text}
                )
            ]
        )

    def on_message(self, ch: pika.adapters.blocking_connection.BlockingChannel, method, properties, body: bytes):
        try:
            body_json = json.loads(body.decode("utf-8"))
            text = body_json["doc"]
            token = body_json["token"]
            logger.info("Received:", body_json)

            embedding = self.encode(text)
            self.store_in_qdrant(text, embedding, token)
            self._connect_postgres()
            self._update_postgres_success(token)
            ch.basic_ack(delivery_tag=method.delivery_tag)
            logger.info("Message processed and acknowledged")

        except Exception as e:
            logger.info(f"Error processing message: {e}")
            ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)
            self._update_postgres_failure(token)

    def start(self):
        self.initialize_services()
        self.channel.basic_consume(
            queue=self.config.QUEUE_NAME,
            on_message_callback=self.on_message
        )
        logger.info("Starting message consumption...")
        try:
            self.channel.start_consuming()
        except KeyboardInterrupt:
            logger.info("Shutting down...")
            self.stop()

    def stop(self):
        if self.connection and self.connection.is_open:
            self.connection.close()
            logger.info("RabbitMQ connection closed.")


if __name__ == "__main__":
    app = Application(AppConfig())
    app.start()