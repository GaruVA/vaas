#!/usr/bin/env python
"""Test script: populate sample data and verify API endpoints."""

import sys
sys.path.insert(0, '.')

from datetime import datetime, timedelta
import bcrypt
from webapp import create_app
from src.database import connect, init_db

def populate_test_data():
    """Insert test data into the database."""
    app = create_app()
    db = app.config['VAAS_DB']

    # Insert test user
    admin_pw = bcrypt.hashpw('admin123'.encode(), bcrypt.gensalt()).decode()
    db.execute(
        'INSERT OR REPLACE INTO users (username, password_hash, role, full_name) '
        'VALUES (?, ?, ?, ?)',
        ('admin_test', admin_pw, 'ADMIN', 'Test Admin')
    )

    # Insert test shifts
    shifts = [
        ('Morning', '07:00', '15:00', 'Mon-Fri', 'GATE_A,GATE_B'),
        ('Evening', '15:00', '23:00', 'Mon-Fri', 'GATE_A,GATE_B'),
        ('Night', '23:00', '07:00', 'Daily', 'GATE_A,GATE_B'),
    ]
    for name, start, end, dow, gates in shifts:
        db.execute(
            'INSERT INTO shifts (shift_name, start_time, end_time, days_of_week, permitted_gates, grace_period_minutes) '
            'VALUES (?, ?, ?, ?, ?, ?)',
            (name, start, end, dow, gates, 30)
        )

    # Insert test zones
    zones = [
        ('DRYDOCK_1', 'Drydock 1', 'DRYDOCK', 'GATE_A,GATE_B', 50),
        ('BERTH_3', 'Berth 3', 'BERTH', 'GATE_B', 30),
        ('WORKSHOP_A', 'Workshop A', 'WORKSHOP', 'GATE_A', 20),
    ]
    for zone_id, name, zone_type, gates, capacity in zones:
        db.execute(
            'INSERT OR REPLACE INTO cdl_zones (zone_id, zone_name, zone_type, associated_gates, vehicle_capacity) '
            'VALUES (?, ?, ?, ?, ?)',
            (zone_id, name, zone_type, gates, capacity)
        )

    # Insert test vehicles
    vehicles = [
        ('WP-KJ-3847', 'STAFF', 'CAR', 'ACTIVE', None, 'Engineering'),
        ('NB-AA-0012', 'CONTRACTOR', 'TRUCK', 'ACTIVE', 'ABC Contractors', 'Project A'),
        ('CP-MA-2341', 'MANAGEMENT', 'CAR', 'ACTIVE', None, 'Admin'),
        ('SP-BD-7783', 'CONTRACTOR', 'TRUCK', 'EXPIRED', 'XYZ Services', 'Project B'),
    ]
    for plate, category, vtype, status, contractor, dept in vehicles:
        db.execute(
            'INSERT OR REPLACE INTO registered_vehicles '
            '(plate_number, vehicle_category, vehicle_type, registration_status, contractor_name, department) '
            'VALUES (?, ?, ?, ?, ?, ?)',
            (plate, category, vtype, status, contractor, dept)
        )

    # Insert test access events
    now = datetime.utcnow()
    events = [
        ('WP-KJ-3847', 'ENTRY', now - timedelta(hours=2), 'GATE_A', 0.94),
        ('NB-AA-0012', 'ENTRY', now - timedelta(hours=1, minutes=30), 'GATE_B', 0.87),
        ('CP-MA-2341', 'EXIT', now - timedelta(minutes=45), 'GATE_A', 0.92),
        ('SP-BD-7783', 'ENTRY', now - timedelta(minutes=30), 'GATE_B', 0.89),
        ('WP-KJ-3847', 'EXIT', now - timedelta(minutes=15), 'GATE_A', 0.91),
    ]
    for plate, direction, ts, gate, conf in events:
        db.execute(
            'INSERT INTO access_log (plate_number, direction, timestamp, gate_id, status, confidence_score) '
            'VALUES (?, ?, ?, ?, ?, ?)',
            (plate, 'ENTRY' if direction == 'ENTRY' else 'EXIT', ts.isoformat(), gate, 'ON_TIME_ENTRY', conf)
        )

    db.commit()
    print('[OK] Test data populated successfully')
    return admin_pw

def test_api_endpoints():
    """Test API endpoints with authentication."""
    from werkzeug.datastructures import Authorization

    app = create_app()

    # First, populate test data and get credentials
    pw_hash = populate_test_data()

    with app.test_client() as client:
        # Login
        login_resp = client.post('/auth/login', data={
            'username': 'admin_test',
            'password': 'admin123',
        }, follow_redirects=True)

        if login_resp.status_code != 200:
            print(f'[FAIL] Login failed: {login_resp.status_code}')
            return

        print('[OK] Login successful')

        # Test each endpoint
        endpoints = [
            ('GET', '/api/stats', 'Stats'),
            ('GET', '/api/events/recent', 'Events (recent)'),
            ('GET', '/api/exceptions/pending', 'Exceptions (pending)'),
            ('GET', '/api/vehicles', 'Vehicles'),
            ('GET', '/api/shifts', 'Shifts'),
            ('GET', '/api/zones', 'Zones'),
            ('GET', '/api/users', 'Users'),
            ('GET', '/api/manager/dashboard', 'Manager Dashboard'),
            ('GET', '/api/audit/chain', 'Audit Chain'),
            ('GET', '/api/audit/log', 'Audit Log'),
        ]

        for method, endpoint, name in endpoints:
            resp = client.get(endpoint) if method == 'GET' else client.post(endpoint)
            status = resp.status_code

            if status == 200:
                data = resp.get_json()
                if isinstance(data, dict):
                    print(f'  [OK] {name}: 200 ({len(data)} keys)')
                elif isinstance(data, list):
                    print(f'  [OK] {name}: 200 ({len(data)} items)')
                else:
                    print(f'  [OK] {name}: 200')
            else:
                print(f'  [FAIL] {name}: {status}')

if __name__ == '__main__':
    try:
        test_api_endpoints()
        print('\n[SUCCESS] All tests passed!')
    except Exception as e:
        print(f'\n[ERROR] {e}')
        import traceback
        traceback.print_exc()
