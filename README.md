# rag-in-a-box

A modular Retrieval-Augmented Generation (RAG) system with separate microservices for encoding and orchestration.

## 🚀 Features
- Microservice architecture with FastAPI

- Encoder: Converts text to vector using fastembed

- Orchestrator: Handles end-to-end RAG workflow

- Dockerized for easy deployment

- Run everything using docker-compose

## 🐳 Running the app with Docker Compose

1. Clone the repo

```shell
git clone https://github.com/Gauri-Khanolkar1/rag-in-a-box

cd rag-in-a-box
```

2.Start the services

```shell
docker compose up --build
```

OR 

```shell
docker-compose up --build
```

3.Access the services:
- Submit a document to the orchestrator service: 

```shell
curl -X \
 POST http://localhost:8000/submit-document \
     -H \
 "Content-Type: application/json" \
     -d '{"document": "Some cats like Matcha, other cats meown't"}'

```

- Ask a question:

```shell
curl -X \
 POST http://localhost:8000/ask \
     -H \
 "Content-Type: application/json" \
     -d '{"query": "What do cats drink?"}'

```

\* Check Notes section for error

## Following are the sequence charts - 

### User flow for submitting document
![User flow for submitting document](/images/RAG_in_a_box_sequence_diags-2.drawio.png)

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