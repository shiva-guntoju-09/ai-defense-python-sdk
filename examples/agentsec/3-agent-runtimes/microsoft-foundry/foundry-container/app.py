"""
Foundry Container Agent - Flask App Entry Point.

This module provides a Flask web application that wraps the SRE agent
for deployment as a container in Azure AI Foundry or Azure Container Apps.

The agent is protected by agentsec (Cisco AI Defense) for both LLM and MCP calls.

Usage:
    # Local development
    python app.py
    
    # Build and run locally
    docker build -t foundry-agent .
    docker run -p 8080:8080 --env-file ../../.env foundry-agent
    
    # Deploy to Azure
    ./scripts/deploy.sh
    
    # Invoke the deployed container
    ./scripts/invoke.sh "Check payments health"

Endpoints:
    POST /invoke - Invoke the agent with a prompt
    POST /score - Azure ML compatible scoring endpoint
    GET /health - Health check endpoint
"""

import os
import sys
import json
from flask import Flask, request, jsonify

# Add parent directory to path for imports
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

# For container deployment, _shared and agentsec are at /app level
APP_DIR = "/app"
if os.path.exists(APP_DIR) and APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

# Import the protected agent (agentsec.protect() is called on import)
from _shared import invoke_agent
from aidefense.runtime import agentsec

# Create Flask app
app = Flask(__name__)


@app.route("/health", methods=["GET"])
def health():
    """Health check endpoint for Azure."""
    return jsonify({
        "status": "healthy",
        "patched_clients": agentsec.get_patched_clients(),
    })


@app.route("/invoke", methods=["POST"])
def invoke():
    """
    Invoke the SRE agent with a prompt.
    
    Request body:
        {"prompt": "Check the health of the payments service"}
        
    Response:
        {"result": "The payments service is healthy..."}
    """
    try:
        # Parse request
        data = request.get_json(force=True)
        
        if not data:
            return jsonify({"error": "Request body is required"}), 400
        
        prompt = data.get("prompt", data.get("message", data.get("input")))
        
        if not prompt:
            return jsonify({"error": "prompt field is required"}), 400
        
        print(f"[app] Received prompt: {prompt}", flush=True)
        print(f"[agentsec] Patched clients: {agentsec.get_patched_clients()}", flush=True)
        
        # Invoke the agent (LLM + MCP calls are protected by agentsec!)
        result = invoke_agent(prompt)
        
        return jsonify({"result": result})
        
    except Exception as e:
        print(f"[app] Error: {e}", flush=True)
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@app.route("/score", methods=["POST"])
def score():
    """
    Azure ML compatible scoring endpoint.
    
    This endpoint follows Azure ML's expected interface for managed online endpoints.
    
    Request body:
        {"data": {"prompt": "Check the health of the payments service"}}
        
    Response:
        {"result": "The payments service is healthy..."}
    """
    try:
        data = request.get_json(force=True)
        
        if not data:
            return jsonify({"error": "Request body is required"}), 400
        
        # Azure ML wraps input in "data" key
        if "data" in data:
            data = data["data"]
        
        if not data:
            return jsonify({"error": "data field is required"}), 400
        
        prompt = data.get("prompt", data.get("message", data.get("input")))
        
        if not prompt:
            return jsonify({"error": "prompt field is required"}), 400
        
        result = invoke_agent(prompt)
        return jsonify({"result": result})
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    port = int(os.getenv("PORT", "8080"))
    print(f"Starting Foundry Container Agent on port {port}...")
    print(f"[agentsec] Patched clients: {agentsec.get_patched_clients()}")
    app.run(host="0.0.0.0", port=port, debug=False)
