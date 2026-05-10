#!/usr/bin/env python
"""Test all manager report endpoints."""
from webapp import create_app
from datetime import date, timedelta

app = create_app(hardware_mode='LIVE')

with app.test_client() as client:
    # Login as admin first
    client.post('/auth/login', data={'username': 'admin', 'password': 'admin123'})
    
    # Test all manager report endpoints
    endpoints = [
        ('/manager/', 'Manager Home'),
        ('/manager/reports/ohs', 'OHS Compliance'),
        ('/manager/reports/personal-allowance', 'Personal Allowance'),
        ('/manager/reports/gate-rejection-audit', 'Gate Rejection Audit'),
        ('/manager/reports/admin-audit', 'Admin Audit'),
        ('/manager/reports/zone-occupancy', 'Zone Occupancy'),
        ('/manager/reports/subcontractor', 'Subcontractor Billing'),
        ('/manager/daily', 'Daily Report'),
        ('/manager/weekly', 'Weekly Report'),
        ('/manager/monthly', 'Monthly Report'),
        ('/manager/rejections', 'Rejections'),
        ('/manager/fuel', 'Fuel'),
        ('/manager/audit', 'Audit'),
        ('/manager/payroll', 'Payroll'),
    ]
    
    for endpoint, name in endpoints:
        resp = client.get(endpoint)
        status_symbol = '[OK]' if resp.status_code == 200 else '[ERR]'
        print(f'{status_symbol} {name:30} [{endpoint:35}] {resp.status_code}')
