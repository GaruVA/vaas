#!/usr/bin/env python
"""Debug script to inspect Flask app via HTTP."""
import socket
import sys

# Create the app like serve.py does
from src.config import HARDWARE_MODE
from webapp import create_app

app = create_app(
    hardware_mode=HARDWARE_MODE,
    start_overstay_monitor=True,
)

# Add debug endpoint
@app.route("/debug/blueprints")
def debug_blueprints():
    return {"blueprints": list(app.blueprints.keys())}

@app.route("/debug/routes")
def debug_routes():
    routes = []
    for rule in app.url_map.iter_rules():
        routes.append({
            "endpoint": rule.endpoint,
            "methods": list(rule.methods - {"HEAD", "OPTIONS"}),
            "path": str(rule),
        })
    return {"routes": routes}

if __name__ == "__main__":
    # Test locally
    with app.test_client() as client:
        print("Blueprints:", client.get("/debug/blueprints").json)
        
        # Get all routes
        resp = client.get("/debug/routes")
        routes = resp.json.get("routes", [])
        auth_routes = [r for r in routes if "auth" in r["endpoint"]]
        operator_routes = [r for r in routes if "operator" in r["endpoint"]]
        
        print(f"\nAuth routes ({len(auth_routes)}):")
        for r in auth_routes:
            print(f"  {r['path']} → {r['endpoint']}")
        
        print(f"\nOperator routes ({len(operator_routes)}):")
        for r in operator_routes:
            print(f"  {r['path']} → {r['endpoint']}")
