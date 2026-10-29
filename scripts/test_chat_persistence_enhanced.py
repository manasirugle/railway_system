import requests
import json
import uuid

BASE_URL = "http://localhost:8000"

def test_chat_persistence():
    print("--- Testing Chat Persistence ---")
    
    # 1. Create a session
    print("\n1. Creating Session...")
    res = requests.post(f"{BASE_URL}/chat/session")
    session = res.json()
    session_id = session['session_id']
    print(f"Created Session: {session_id}")

    # 2. List sessions
    print("\n2. Listing Sessions...")
    res = requests.get(f"{BASE_URL}/chat/sessions")
    sessions = res.json()
    found = any(s['session_id'] == session_id for s in sessions)
    print(f"Session found in list: {found}")

    # 3. Send first message (should generate title)
    print("\n3. Sending First Message...")
    query = "What is the delay status at NDLS?"
    payload = {"query": query, "session_id": session_id, "mode": "passenger"}
    res = requests.post(f"{BASE_URL}/chat", json=payload)
    chat_res = res.json()
    print(f"AI Response: {chat_res['response'][:100]}...")
    print(f"Generated Title: {chat_res['title']}")

    # 4. Verify title updated in session list
    print("\n4. Verifying Title Update...")
    res = requests.get(f"{BASE_URL}/chat/sessions")
    sessions = res.json()
    session_data = next(s for s in sessions if s['session_id'] == session_id)
    print(f"Updated Title in list: {session_data['title']}")

    # 5. Send second message (check if history is handled by LLM indirectly)
    print("\n5. Sending Second Message...")
    query = "And how about HWH?"
    payload = {"query": query, "session_id": session_id, "mode": "passenger"}
    res = requests.post(f"{BASE_URL}/chat", json=payload)
    chat_res2 = res.json()
    print(f"AI Response 2: {chat_res2['response'][:100]}...")

    # 6. Delete session
    print("\n6. Deleting Session...")
    res = requests.delete(f"{BASE_URL}/chat/session/{session_id}")
    print(f"Delete Status: {res.json()}")

    # 7. Verify deletion
    print("\n7. Verifying Deletion...")
    res = requests.get(f"{BASE_URL}/chat/sessions")
    sessions = res.json()
    found = any(s['session_id'] == session_id for s in sessions)
    print(f"Session still exists: {found}")

if __name__ == "__main__":
    try:
        test_chat_persistence()
    except Exception as e:
        print(f"ERROR: {e}")
