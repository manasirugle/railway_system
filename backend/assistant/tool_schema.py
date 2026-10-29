TOOL_SCHEMA = {
    "ticket_prediction": {
        "endpoint": "/ticket/predict",
        "method": "POST",
        "parameters": [
            {"name": "wl", "required": True, "type": "int"},
            {"name": "days", "required": False, "type": "int", "default": 60},
            {"name": "cls", "required": False, "type": "str", "default": "3AC"},
            {"name": "quota", "required": False, "type": "str", "default": "General"},
            {"name": "peak", "required": False, "type": "int", "default": 0},
            {"name": "passengers", "required": False, "type": "int", "default": 1}
        ]
    },
    "passenger_flow": {
        "endpoint": "/crowd/{station_id}",
        "method": "GET",
        "parameters": [
            {"name": "station_id", "required": True, "type": "str", "in_path": True},
            {"name": "date", "required": False, "type": "str"},
            {"name": "hour", "required": False, "type": "int"}
        ]
    },
    "delay_cascade": {
        "endpoint": "/cascade/{station}/{delay}",
        "method": "GET",
        "parameters": [
            {"name": "station", "required": True, "type": "str", "in_path": True},
            {"name": "delay", "required": False, "type": "int", "in_path": True, "default": 30}
        ]
    },
    "congestion": {
        "endpoint": "/congestion/{corridor}",
        "method": "GET",
        "parameters": [
            {"name": "corridor", "required": True, "type": "str", "in_path": True}
        ]
    },
    "routing": {
        "endpoint": "/route/{origin}/{destination}",
        "method": "GET",
        "parameters": [
            {"name": "origin", "required": True, "type": "str", "in_path": True},
            {"name": "destination", "required": True, "type": "str", "in_path": True},
            {"name": "blocked", "required": False, "type": "str"}
        ]
    },
    "travel_briefing": {
        "endpoint": "/intelligence/briefing",
        "method": "POST",
        "parameters": [
            {"name": "origin", "required": True, "type": "str"},
            {"name": "destination", "required": True, "type": "str"},
            {"name": "date", "required": False, "type": "str"},
            {"name": "travel_class", "required": False, "type": "str"},
            {"name": "wl_number", "required": False, "type": "int"},
            {"name": "season_peak", "required": False, "type": "int"}
        ]
    },
    "operational_adjustments": {
        "endpoint": "/intelligence/adjustments",
        "method": "GET",
        "parameters": []
    },
    "smart_booking": {
        "endpoint": "/intelligence/booking",
        "method": "POST",
        "parameters": [
            {"name": "origin", "required": True, "type": "str"},
            {"name": "destination", "required": True, "type": "str"},
            {"name": "date", "required": False, "type": "str", "default": "2025-12-25"},
            {"name": "travel_class", "required": False, "type": "str", "default": "3AC"},
            {"name": "wl_number", "required": False, "type": "int"}
        ]
    }
}