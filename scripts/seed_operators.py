
import firebase_admin
from firebase_admin import credentials, firestore
import os

def seed_operators():
    cred_path = os.path.join('backend', 'api', 'serviceAccountKey.json')
    if not os.path.exists(cred_path):
        print(f"Error: {cred_path} not found.")
        return

    cred = credentials.Certificate(cred_path)
    if not firebase_admin._apps:
        firebase_admin.initialize_app(cred)
    
    db = firestore.client()
    
    operators = [
        "admin@railway.gov.in",
        "operator@gleis.ai",
        "aryankale1104@gmail.com",
        "prernak2326@gmail.com",
        "swathipillai607@gmail.com",
        "aryankulkarni1104@gmail.com"
    ]
    
    for email in operators:
        db.collection('authorized_operators').document(email).set({
            'email': email,
            'role': 'operator',
            'added_at': firestore.SERVER_TIMESTAMP
        })
        print(f"Added {email} to authorized_operators.")

if __name__ == "__main__":
    seed_operators()
