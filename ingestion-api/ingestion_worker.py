import json
import uuid
import pika
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct
from fastembed import TextEmbedding


class AppConfig:
    QDRANT_URL = "http://localhost:6333"
    QDRANT_COLLECTION_NAME = "test"
    EMBEDDING_MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
    RABBITMQ_HOST = "localhost"
    QUEUE_NAME = "ingestion_queue"
    VECTOR_SIZE = 384
    VECTOR_DISTANCE = Distance.COSINE


class Application:
    def __init__(self, config: AppConfig):
        self.config = config
        self.qdrant = None
        self.model = None
        self.connection = None
        self.channel = None

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
        self.connection = pika.BlockingConnection(
            pika.ConnectionParameters(self.config.RABBITMQ_HOST)
        )
        self.channel = self.connection.channel()
        self.channel.queue_declare(queue=self.config.QUEUE_NAME)
        self.channel.basic_qos(prefetch_count=1)

    def encode(self, text: str) -> list[float]:
        return next(iter(self.model.embed(text))).tolist()

    def store_in_qdrant(self, text: str, embedding: list[float]) -> None:
        self.qdrant.upsert(
            collection_name=self.config.QDRANT_COLLECTION_NAME,
            points=[
                PointStruct(
                    id=str(uuid.uuid4()),
                    vector=embedding,
                    payload={"text": text}
                )
            ]
        )

    def on_message(self, ch, method, properties, body):
        try:
            body_json = json.loads(body.decode("utf-8"))
            text = body_json["doc"]
            print("Received:", body_json)

            embedding = self.encode(text)
            self.store_in_qdrant(text, embedding)

            ch.basic_ack(delivery_tag=method.delivery_tag)
            print("Message processed and acknowledged")

        except Exception as e:
            print(f"Error processing message: {e}")
            ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)

    def start(self):
        self.initialize_services()
        self.channel.basic_consume(
            queue=self.config.QUEUE_NAME,
            on_message_callback=self.on_message
        )
        print("Starting message consumption...")
        try:
            self.channel.start_consuming()
        except KeyboardInterrupt:
            print("Shutting down...")
            self.stop()

    def stop(self):
        if self.connection and self.connection.is_open:
            self.connection.close()
            print("RabbitMQ connection closed.")


if __name__ == "__main__":
    app = Application(AppConfig())
    app.start()