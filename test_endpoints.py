#!/usr/bin/env python
"""Test dashboard route with auth."""
import sys
import traceback

try:
    from webapp import create_app
    app = create_app(hardware_mode='LIVE')
    
    # Test 1: Dashboard without auth (should redirect to login)
    print("Test 1: Dashboard without auth...")
    with app.test_client() as client:
        resp = client.get('/operator/dashboard')
        print(f"  Status: {resp.status_code}")
        if resp.status_code == 302:
            print(f"  ✓ Redirects to: {resp.location}")
        else:
            print(f"  Error: {resp.get_data(as_text=True)[:500]}")
    
    # Test 2: Login page
    print("\nTest 2: Login page...")
    with app.test_client() as client:
        resp = client.get('/auth/login')
        print(f"  Status: {resp.status_code}")
        if resp.status_code == 200:
            print(f"  ✓ Login page loads")
        else:
            print(f"  Error: {resp.get_data(as_text=True)[:500]}")
    
    # Test 3: Check blueprints registered
    print("\nTest 3: Registered blueprints...")
    print(f"  Blueprints: {list(app.blueprints.keys())}")
    
except Exception as e:
    print(f'Error: {e}')
    traceback.print_exc()
    sys.exit(1)
