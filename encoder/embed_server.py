from flask import Flask, request, jsonify
from sentence_transformers import SentenceTransformer

app = Flask(__name__)
model = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")

@app.route("/embed", methods=["POST"])
def embed():
    data = request.get_json()
    sentences = data.get("inputs", [])
    embeddings = model.encode(sentences, convert_to_numpy=True).tolist()
    return jsonify({"embeddings": embeddings})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8001)
