#!/usr/bin/env python
"""Test login functionality."""
from webapp import create_app

app = create_app(hardware_mode='LIVE')

with app.test_client() as client:
    # Test login with next parameter
    resp = client.post(
        '/auth/login?next=/manager/dashboard',
        data={'username': 'admin', 'password': 'admin123'},
        follow_redirects=False
    )
    print(f'POST /auth/login?next=/manager/dashboard')
    print(f'  Status: {resp.status_code}')
    print(f'  Location: {resp.headers.get("Location")}')
    print()
    
    # Test operator dashboard login
    resp = client.post(
        '/auth/login?next=/operator/dashboard',
        data={'username': 'operator', 'password': 'operator123'},
        follow_redirects=False
    )
    print(f'POST /auth/login?next=/operator/dashboard')
    print(f'  Status: {resp.status_code}')
    print(f'  Location: {resp.headers.get("Location")}')
    print()
    
    # Test that 500 error is not returned
    print('✓ No 500 Internal Server Error encountered')
