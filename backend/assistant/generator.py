import os
import json
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

client = OpenAI(
    api_key=os.getenv("OPENROUTER_API_KEY"),
    base_url="https://openrouter.ai/api/v1",
    default_headers={
        "HTTP-Referer": "http://localhost:8000",
        "X-Title": "Railway Intelligence System"
    }
)

def generate_chat_title(query: str):
    system_prompt = "You are a helpful assistant. Generate a concise 3-word title (e.g., 'NDLS Delay Analysis') for a chat session based on the user's first query. Return ONLY the title, no other text."
    try:
        response = client.chat.completions.create(
            model="openai/gpt-oss-120b",
            temperature=0,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": query}
            ]
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        print("TITLE GEN ERROR:", e)
        return "New Chat Session"

def generate_response(query: str, tool: str, api_result: dict, history: list = None):
    if "error" in api_result:
        return f"I encountered an error trying to process your request: {api_result['error']}"

    system_prompt = """
You are the official AI assistant for this railway intelligence system.
You have just used an API tool to get data to answer the user's query.

Your task is to convert the raw JSON result into a helpful, natural language response.
CRITICAL INSTRUCTIONS:
1. Explain the data in a way that any normal human traveler will easily understand.
2. Keep it short, concise, and to the point.
3. Be confident. You are the official system. DO NOT tell the user to check "official websites", "other apps", or "IRCTC". Provide the answer directly.
4. If there are probabilities or predictions, explain them simply (e.g., "There is an 85% chance"). Do not just dump the raw JSON.
5. Provide the exact text immediately. Do NOT use markdown formatting, bold text, italics, bullet points, greetings, or introductory/summary lines. Just write the raw, direct explanation as plain text.
6. SPECIAL CASE: If the tool is 'general_info' or 'unknown', the 'Raw API Result' will be empty or contain a topic. In this case, use your own extensive internal knowledge about the Indian Railway system to answer the user's query accurately and professionally while staying in character as the official system assistant.
"""

    prompt = f"User Query: {query}\nTool Used: {tool}\nRaw API Result:\n{json.dumps(api_result, indent=2)}\n\nPlease provide a natural language response based on the above result."

    try:
        response = client.chat.completions.create(
            model="openai/gpt-oss-120b",
            temperature=0.3,
            messages=[
                {"role": "system", "content": system_prompt}
            ] + (history or []) + [
                {"role": "user", "content": prompt}
            ]
        )

        return response.choices[0].message.content

    except Exception as e:
        print("LLM ERROR:", e)
        return f"Here is the raw data I found (failed to generate natural response): {json.dumps(api_result)}"