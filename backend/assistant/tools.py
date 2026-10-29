import requests
from .tool_schema import TOOL_SCHEMA

BASE_URL = "http://localhost:8000"

def execute_tool(tool_name: str, params: dict):
    if tool_name not in TOOL_SCHEMA:
        return {"error": f"Unknown tool: {tool_name}"}
    
    schema = TOOL_SCHEMA[tool_name]
    
    # Check required parameters
    for param_meta in schema.get("parameters", []):
        if param_meta.get("required") and param_meta["name"] not in params:
            return {"error": f"Missing required parameter: {param_meta['name']}"}
            
    # Construct endpoint
    endpoint = schema["endpoint"]
    path_params = {}
    query_params = {}
    body_payload = {}
    
    for param_meta in schema.get("parameters", []):
        name = param_meta["name"]
        if name in params:
            val = params[name]
        else:
            if "default" in param_meta:
                val = param_meta["default"]
            else:
                continue
                
        if param_meta.get("in_path"):
            path_params[name] = val
        elif schema["method"] == "GET":
            query_params[name] = val
        else:
            body_payload[name] = val
            
    # Special handling for routing alternatives
    if tool_name == "routing" and "blocked" in query_params:
        endpoint = "/route/{origin}/{destination}/alternatives"
        
    try:
        url = BASE_URL + endpoint.format(**path_params)
    except KeyError as e:
        return {"error": f"Missing path parameter: {e}"}
        
    try:
        if schema["method"] == "GET":
            response = requests.get(url, params=query_params)
        elif schema["method"] == "POST":
            response = requests.post(url, json=body_payload)
        else:
            return {"error": f"Unsupported HTTP method: {schema['method']}"}
            
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        return {"error": f"API request failed: {str(e)}"}
