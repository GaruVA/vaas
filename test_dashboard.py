#!/usr/bin/env python
"""Test dashboard route to see actual error."""
import sys
import traceback

try:
    from webapp import create_app
    app = create_app(hardware_mode='LIVE')
    
    with app.test_client() as client:
        resp = client.get('/operator/dashboard')
        print(f'Status: {resp.status_code}')
        print(f'Content-Type: {resp.content_type}')
        print('\n--- Response ---')
        print(resp.get_data(as_text=True)[:3000])
except Exception as e:
    print(f'Error: {e}')
    traceback.print_exc()
    sys.exit(1)
