#!/usr/bin/env python
"""Fix thread-safety issues by replacing current_app.config VAAS_DB with g.db."""
import re

files = [
    'webapp/routes/admin.py',
    'webapp/routes/manager.py',
]

for fpath in files:
    with open(fpath, encoding='utf-8') as f:
        content = f.read()
    
    original = content
    # Replace VAAS_DB references
    content = content.replace('current_app.config["VAAS_DB"]', 'g.db')
    
    if content != original:
        with open(fpath, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f'✓ Fixed {fpath}')
    else:
        print(f'No changes needed for {fpath}')
