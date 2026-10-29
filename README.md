# GLEIS - Railway Intelligence AI

Railway Intelligence AI is a comprehensive dashboard and backend API designed to assist both passengers and railway operators by providing advanced analytics, predictive modeling, and live insights into the Indian Railways network.

## Project Overview

The system features two main interfaces built with **Streamlit**:

1. **Passsenger Portal:** Includes smart ticket waitlist prediction, real-time station crowd tracking, and intelligent alternative route planning.
2. **Operator Dashboard:** Provides live network health monitoring, cascading delay simulations, congestion forecasting, and vulnerability analysis across the railway network.
3. **AI Assistant:** An intelligent chatbot interface that answers queries about schedules, delay risks, congestion, and ticket confirmation using advanced tools.

The backend is powered by **FastAPI** and utilizes machine learning libraries (Scikit-Learn, XGBoost, Prophet), graph analytics (NetworkX), and real-time live data endpoints to offer actionable intelligence. The application also integrates with Firebase Firestore for user session management and authentication.

## Key Features

### Passenger Portal

- **Smart Booking (Ticket Waitlist Prediction):** AI-driven prediction model to determine ticket confirmation probabilities based on waitlist position, class, distance, seasonal peaks, and days until travel. Provides days-ahead booking guidance.
- **Crowd Check:** Real-time and 24-hour predictions for crowd levels at different stations.
- **Route Finder:** Finds the most optimal routes between origin and destination stations, including alternative routes avoiding specific blocked/congested stations.

### Operator Command Center

- **Live Delay Cascades:** Integrates with real-time data to identify delayed trains and simulate using NetworkX how these delays cascade across multiple connected stations.
- **Congestion Forecasting:** Predicts peak loads in major corridors (e.g., NDLS-CNB, CSTM-ADI).
- **Vulnerability Analysis:** Models the structural importance of stations (Betweenness Centrality) to simulate network impact if a critical station goes offline.
- **Manual Simulate:** A sandbox environment to manually simulate delays at any station and observe the multi-hop ripple effect.

### AI Assistant (Chat)

A context-aware intelligent assistant with distinct Passenger and Operator modes that can dynamically query live system tools to answer questions.

## Technology Stack

### Backend

- **FastAPI:** Core API serving endpoints for models, graphs, and live data.
- **Machine Learning:** `scikit-learn`, `xgboost`, `prophet`, `sentence-transformers`, `faiss-cpu`.
- **Graph Processing:** `networkx` optimized for temporal delay cascades and network vulnerabilities.
- **Database / Auth:** Firebase Admin SDK (Firestore) and Firebase Auth.
- **Data processing:** `pandas`, `numpy`.

### Frontend

- **Streamlit:** Interactive web UI for data visualization and chat.
- **Visuals:** `plotly`, `folium`, `streamlit-folium`.

## Setup Instructions

### Prerequisites

- Python 3.8+
- Firebase service account JSON (`backend/api/serviceAccountKey.json`)

### Installation

1. Clone the repository and navigate to the root directory.
2. Create and activate a Python virtual environment:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```
3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
4. Ensure your dataset files (`stations.csv`, `routes.csv`, `trains_full.csv`, `delays.csv`) are correctly placed inside the `data/` directory.
5. Provide valid Firebase database credentials at `backend/api/serviceAccountKey.json`.

### Running the Application

This project runs FastAPI and Streamlit concurrently. Ensure your setup handles running both.

**1. Start the FastAPI Backend Server**

```bash
# In one terminal window, from the root of the project:
uvicorn backend.api.main:app --host 0.0.0.0 --port 8001 --reload
```

The backend API documentation is available at `http://localhost:8000/docs`.

**2. Start the Streamlit Frontend Dashboard**

```bash
# In a second terminal window, from the root of the project:
streamlit run app.py
```

The Streamlit application will open automatically in your browser (default `http://localhost:8501`).

## Directory Structure

- `app.py`: Streamlit main dashboard application.
- `backend/`: FastAPI API routes (`main.py`), ML models (`models/`), Graph logic (`graph/`), and Live API integrations (`live/`).
- `data/`: CSV datasets containing station geometry, routes, trains, and historical delay data.
- `frontend/`: Contains static web assets if any.
- `scripts/`: Helper scripts for data adaptation and rebuilding models.
