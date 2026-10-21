import json
import os
import subprocess
import sys

import pytest


@pytest.mark.parametrize('marker,value', [
    ('RAILWAY_ENVIRONMENT', 'production'),
    ('RAILWAY_ENVIRONMENT_NAME', 'production'),
    ('ENVIRONMENT', 'production'),
    ('ENVIRONMENT', 'prod'),
    ('ENVIRONMENT', 'development'),
])
def test_production_cannot_disable_login_or_secure_cookies(marker, value):
    env = os.environ.copy()
    for name in ('RAILWAY_ENVIRONMENT', 'RAILWAY_ENVIRONMENT_NAME', 'ENVIRONMENT'):
        env.pop(name, None)
    env.update({marker: value, 'AUTH_REQUIRED': 'false', 'COOKIE_SECURE': 'false'})
    result = subprocess.run([
        sys.executable, '-c',
        'import json; from app.auth import AUTH_REQUIRED, COOKIE_SECURE; '
        'print(json.dumps([AUTH_REQUIRED, COOKIE_SECURE]))',
    ], env=env, capture_output=True, text=True, check=True)
    expected = value != 'development'
    assert json.loads(result.stdout) == [expected, expected]
