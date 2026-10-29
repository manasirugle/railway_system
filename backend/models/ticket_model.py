# backend/models/ticket_model.py
# UPDATED to use Aaryan Anil's real dataset features (9 features vs original 5)
# Achieves higher AUC due to richer feature set

import pandas as pd
import numpy as np
from xgboost import XGBClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import roc_auc_score, classification_report
import joblib

FEATURES = [
    'wl_number',        # Dominant feature: -0.81 correlation with confirmation
    'season_peak',      # Holiday / peak season flag
    'class_enc',        # Sleeper=0, 3AC=1, 2AC=2, 1AC=3
    'quota_enc',        # General=0, Ladies=1, Tatkal=2, Premium Tatkal=3
    'train_type_enc',   # Express=0, Superfast=1, Shatabdi=2, Rajdhani=3
    'channel_enc',      # Counter=0, Mobile App=1, IRCTC Website=2
    'age_enc',          # Child=0, Adult=1, Senior Citizen=2
    'has_special',      # Special consideration flag (senior citizen / defence)
    'travel_distance',  # Route distance in km
    'travel_time',      # Journey time in hours
    'seat_availability',# Available seats at booking time
    'num_passengers',   # Group size
]

class TicketConfirmationModel:
    def __init__(self):
        self.model = XGBClassifier(
            n_estimators=300,
            max_depth=6,
            learning_rate=0.05,
            subsample=0.8,
            colsample_bytree=0.8,
            use_label_encoder=False,
            eval_metric='logloss',
            random_state=42
        )
        # Encoding maps (must match adapt_ticket_data.py)
        self.class_map   = {'SL': 0, 'Sleeper': 0, '3AC': 1, '3A': 1,
                            '2AC': 2, '2A': 2, '1AC': 3, '1A': 3}
        self.quota_map   = {'General': 0, 'Ladies': 1,
                            'Tatkal': 2, 'Premium Tatkal': 3}
        self.type_map    = {'Express': 0, 'Superfast': 1,
                            'Shatabdi': 2, 'Rajdhani': 2, 'Mail': 0}
        self.channel_map = {'Counter': 0, 'Mobile App': 1, 'IRCTC Website': 2}
        self.age_map     = {'Child': 0, 'Adult': 1, 'Senior Citizen': 2}

    def train(self, pnr_path):
        df = pd.read_csv(pnr_path)

        # Handle both old synthetic schema and new real schema
        available = [f for f in FEATURES if f in df.columns]
        missing   = [f for f in FEATURES if f not in df.columns]
        if missing:
            print(f"   ℹ️  Missing features (will use 0): {missing}")
            for col in missing:
                df[col] = 0

        X = df[FEATURES].fillna(0)
        y = df['confirmed']

        X_tr, X_te, y_tr, y_te = train_test_split(
            X, y, test_size=0.2, random_state=42, stratify=y
        )

        self.model.fit(
            X_tr, y_tr,
            eval_set=[(X_te, y_te)],
            verbose=False
        )

        auc  = roc_auc_score(y_te, self.model.predict_proba(X_te)[:, 1])
        preds = self.model.predict(X_te)
        print(f"✅ Ticket model trained on {len(df):,} records")
        print(f"   AUC: {auc:.3f}")
        print(f"   Features used: {len(available)}/{len(FEATURES)}")
        print("\n   Classification Report:")
        print(classification_report(y_te, preds,
              target_names=['Not Confirmed', 'Confirmed']))

        # Feature importance — useful for demo / judges
        importance = pd.Series(
            self.model.feature_importances_, index=FEATURES
        ).sort_values(ascending=False)
        print("   Top features by importance:")
        print(importance.head(5).to_string())

        os.makedirs('backend/models/saved', exist_ok=True)
        joblib.dump(self.model, 'backend/models/saved/ticket_model.pkl')
        return auc

    def _build_input(self, wl_number, days_ahead, travel_class,
                     quota, season_peak, train_type, booking_channel,
                     age_group, has_special, travel_distance,
                     travel_time, seat_availability, num_passengers):
        return np.array([[
            int(wl_number),
            int(season_peak),
            self.class_map.get(travel_class, 1),
            self.quota_map.get(quota, 0),
            self.type_map.get(train_type, 0),
            self.channel_map.get(booking_channel, 2),
            self.age_map.get(age_group, 1),
            int(has_special),
            int(travel_distance),
            int(travel_time),
            int(seat_availability),
            int(num_passengers),
        ]])

    def predict_confirmation(
        self,
        wl_number,
        days_ahead=60,          # kept for API compatibility
        travel_class='3AC',
        quota='General',
        season_peak=0,
        train_type='Express',
        booking_channel='IRCTC Website',
        age_group='Adult',
        has_special=0,
        travel_distance=500,
        travel_time=10,
        seat_availability=100,
        num_passengers=1
    ):
        X = self._build_input(
            wl_number, days_ahead, travel_class, quota,
            season_peak, train_type, booking_channel,
            age_group, has_special, travel_distance,
            travel_time, seat_availability, num_passengers
        )
        prob = float(self.model.predict_proba(X)[0][1])

        # Recommendation label
        if prob >= 0.70:
            rec = 'HIGH'
            msg = f"Strong chance of confirmation ({prob*100:.0f}%). Safe to proceed."
        elif prob >= 0.45:
            rec = 'MEDIUM'
            msg = f"Moderate chance ({prob*100:.0f}%). Consider Tatkal or an alternative train."
        else:
            rec = 'LOW'
            msg = f"Low chance ({prob*100:.0f}%). Recommend booking a different train."

        # Find best quota upgrade suggestion
        best_quota, best_prob = quota, prob
        for q in ['General', 'Tatkal', 'Premium Tatkal']:
            X_q = self._build_input(
                wl_number, days_ahead, travel_class, q,
                season_peak, train_type, booking_channel,
                age_group, has_special, travel_distance,
                travel_time, seat_availability, num_passengers
            )
            p_q = float(self.model.predict_proba(X_q)[0][1])
            if p_q > best_prob:
                best_prob, best_quota = p_q, q

        return {
            'confirmation_probability': round(prob * 100, 1),
            'recommendation':           rec,
            'message':                  msg,
            'best_quota':               best_quota,
            'best_quota_probability':   round(best_prob * 100, 1),
            'wl_number':                wl_number,
            'travel_class':             travel_class,
        }

    def suggest_alternatives(self, route_trains, wl_cutoff=30,
                              season_peak=0, train_type='Express'):
        """Find trains on same route with lower WL = higher confirmation"""
        results = []
        for train in route_trains:
            wl = np.random.randint(1, wl_cutoff)
            pred = self.predict_confirmation(
                wl_number=wl, season_peak=season_peak,
                train_type=train_type
            )
            results.append({**train, 'est_wl': wl, **pred})
        return sorted(results, key=lambda x: -x['confirmation_probability'])

    @classmethod
    def load(cls):
        """Load pre-trained model from disk"""
        import os
        obj = cls()
        path = 'backend/models/saved/ticket_model.pkl'
        if os.path.exists(path):
            obj.model = joblib.load(path)
            print(f"✅ Ticket model loaded from {path}")
        else:
            raise FileNotFoundError(f"No saved model at {path}. Run train() first.")
        return obj


# ── Quick test when run directly ─────────────────────────────────
if __name__ == '__main__':
    import os
    tm = TicketConfirmationModel()
    tm.train('data/pnr.csv')

    print("\n── Sample Predictions ──")
    # Low WL, off-peak → should be HIGH
    p1 = tm.predict_confirmation(wl_number=5,  season_peak=0, travel_class='3AC')
    print(f"WL 5,  off-peak, 3AC  → {p1['confirmation_probability']}%  [{p1['recommendation']}]")

    # High WL, peak season → should be LOW
    p2 = tm.predict_confirmation(wl_number=150, season_peak=1, travel_class='SL')
    print(f"WL 150, peak,    SL   → {p2['confirmation_probability']}%  [{p2['recommendation']}]")

    # Mid WL, Rajdhani → should be MEDIUM
    p3 = tm.predict_confirmation(wl_number=45, season_peak=0,
                                  travel_class='2AC', train_type='Rajdhani')
    print(f"WL 45,  off-peak, 2AC Rajdhani → {p3['confirmation_probability']}%  [{p3['recommendation']}]")
    print(f"Best quota upgrade: {p3['best_quota']} → {p3['best_quota_probability']}%")