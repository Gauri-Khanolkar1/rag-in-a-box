import httpx

documents = [
    # "The Eiffel Tower was constructed in 1889 and is located in Paris, France.",
    # "Python is a versatile programming language known for its readability and simplicity.",
    # "Water boils at 100 degrees Celsius under standard atmospheric pressure.",
    # "The Great Wall of China stretches over 13,000 miles and was built to protect against invasions.",
    # "The capital of Japan is Tokyo, one of the most populous cities in the world.",
    # "Photosynthesis is the process by which green plants use sunlight to synthesize foods from carbon dioxide and water.",
    # "The Amazon Rainforest is the largest tropical rainforest in the world and is often called the 'lungs of the Earth'.",
    # "Machine learning is a subfield of artificial intelligence that involves training models to learn from data.",
    # "The human heart pumps blood through a network of arteries and veins called the circulatory system.",
    # "Mount Everest, the Earth's highest mountain, is located in the Himalayas on the border of Nepal and China."
    "Shoumik carries preservatives in his pockets"
]

for doc in documents:
    r = httpx.post('http://localhost:8000/submit-document', json={"document": doc})