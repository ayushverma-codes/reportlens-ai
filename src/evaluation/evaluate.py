"""RAG evaluation entry point; requires original ground truth and configured Groq."""
import json
from pathlib import Path
from .dataset_loader import load_ground_truth

def main():
    dataset = load_ground_truth()
    print(f'Loaded {len(dataset)} evaluation records. Preserve their original fields and reference answers.')
    print('Full RAGAS scoring requires a verified question/answer schema, running index, and evaluator LLM. No scores were computed.')

if __name__ == '__main__':
    main()
