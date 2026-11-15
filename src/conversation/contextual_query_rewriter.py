"""Rewrite elliptical follow-ups but never treat chat as the evidence source."""
from src.generation.groq_client import chat

def rewrite(question, history, api_key=None):
    if not history:
        return question
    recent = '\n'.join(f'{x["role"]}: {x["content"][:500]}' for x in history[-6:])
    prompt = ('Rewrite the last question into a standalone search query using conversation context. '
              'Do not answer it, do not add facts. Return only the query.\nHistory:\n'
              + recent + '\nQuestion: ' + question)
    return chat([{'role':'user','content':prompt}], api_key=api_key).strip() or question
