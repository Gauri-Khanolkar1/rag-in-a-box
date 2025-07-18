# RAG-in-a-Box

A modular Retrieval-Augmented Generation (RAG) system built using microservices for document ingestion, encoding, and orchestration.

## 🚀 Features

- 🧱 Microservice architecture using **FastAPI**
- 🧠 **Encoder**: Converts text into vectors using `fastembed`
- 🧩 **Orchestrator**: Handles end-to-end RAG workflow
- 📥 **Ingestion**: Includes RabbitMQ-based document submission via producer; consumer runs separately
- 🐳 Fully **Dockerized** for reproducible deployment
- ⚡ Spin up the full system with **Docker Compose**

## 🐳 Running the app with Docker Compose

1. Clone the repo

```shell
git clone https://github.com/Gauri-Khanolkar1/rag-in-a-box

cd rag-in-a-box
```

2.Start the services

```shell
docker compose up --build

# or, if using older Docker versions 

docker-compose up --build
```

3.Access the services:
- 🔁 Submit a document to the ingestion service (check RabbitMQ for the message):

```shell
curl --location 'http://localhost:8002/ingest' \
 \
--header 'Content-Type: application/json' \
 \
--data '{"text":"The Hot Rat Summer mosaic at Cal Anderson park shines in the sunlight."}' \

```

- 🧵 Start the consumer (to process and store in Qdrant):

```shell
uv run .\ingestion_worker.py
```

- ❓ Ask a question (handled by Orchestrator):

```shell
curl -X \
 POST http://localhost:8000/ask \
     -H \
 "Content-Type: application/json" \
     -d '{"query": "What does summer in Seattle look like?"}'

```

\* ⚠️ Note: See the Notes section below if you run into errors with Ollama.

## Following are the sequence charts - 

### User flow for submitting document
![User flow for submitting document](/images/RAG_in_a_box_sequence_diags-1_ingestion.png)

### User flow for asking a question
![User flow for asking a question](/images/RAG_in_a_box_sequence_diags-3.drawio.png)


## Notes

Currently the OLLAMA docker container doesn't pull the model on docker compose. Use the following commands to pull the model.

```shell
curl --location 'http://localhost:11434/api/pull' \
--header 'Content-Type: text/plain' \
--data '{
    "name": "smollm",
    "stream": false
}'
```