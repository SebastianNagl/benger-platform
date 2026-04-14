"""
SSL/TLS Configuration for BenGER Production

This module implements SSL/TLS configuration and certificate management:
1. Let's Encrypt certificate automation
2. SSL security headers
3. Certificate renewal monitoring
4. HTTPS redirect enforcement
5. Security best practices

Production Security Impact:
- Automated SSL certificate management
- HTTPS enforcement for all traffic
- Security headers for XSS/CSRF protection
- Certificate monitoring and alerts
"""

import asyncio
import os
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Dict

import aiofiles
from cryptography import x509
from cryptography.hazmat.backends import default_backend


class SSLTLSManager:
    """Production SSL/TLS certificate management"""

    def __init__(self, domain: str, email: str):
        self.domain = domain
        self.email = email
        self.cert_dir = Path("/etc/letsencrypt/live") / domain
        self.staging = os.getenv("SSL_STAGING", "false").lower() == "true"

    async def setup_letsencrypt(self) -> Dict:
        """Setup Let's Encrypt certificates"""
        try:
            # Check if certbot is installed
            result = subprocess.run(["certbot", "--version"], capture_output=True, text=True)

            if result.returncode != 0:
                return {
                    "success": False,
                    "error": "Certbot not installed",
                    "install_command": "sudo apt-get install certbot python3-certbot-nginx",
                }

            # Prepare certbot command
            cmd = [
                "certbot",
                "certonly",
                "--nginx",  # or --standalone
                "--agree-tos",
                "--non-interactive",
                "--email",
                self.email,
                "-d",
                self.domain,
                "-d",
                f"www.{self.domain}",
                "-d",
                f"api.{self.domain}",
                "-d",
                f"labelstudio.{self.domain}",
            ]

            if self.staging:
                cmd.append("--staging")

            # Run certbot
            result = subprocess.run(cmd, capture_output=True, text=True)

            if result.returncode == 0:
                return {
                    "success": True,
                    "message": "SSL certificates obtained successfully",
                    "cert_path": str(self.cert_dir),
                    "renewal_command": "certbot renew",
                }
            else:
                return {
                    "success": False,
                    "error": result.stderr,
                    "stdout": result.stdout,
                }

        except Exception as e:
            return {"success": False, "error": f"SSL setup failed: {str(e)}"}

    async def check_certificate_expiry(self) -> Dict:
        """Check certificate expiration status"""
        cert_file = self.cert_dir / "cert.pem"

        try:
            if not cert_file.exists():
                return {"exists": False, "error": "Certificate file not found"}

            # Read certificate
            async with aiofiles.open(cert_file, "rb") as f:
                cert_data = await f.read()

            cert = x509.load_pem_x509_certificate(cert_data, default_backend())

            # Get expiration info
            now = datetime.utcnow()
            expires = cert.not_valid_after
            days_until_expiry = (expires - now).days

            # Check renewal needed
            renewal_needed = days_until_expiry <= 30

            return {
                "exists": True,
                "expires": expires.isoformat(),
                "days_until_expiry": days_until_expiry,
                "renewal_needed": renewal_needed,
                "subject": cert.subject.rfc4514_string(),
                "issuer": cert.issuer.rfc4514_string(),
            }

        except Exception as e:
            return {"exists": True, "error": f"Certificate check failed: {str(e)}"}

    async def auto_renew_certificates(self) -> Dict:
        """Automatically renew certificates if needed"""
        try:
            # Check if renewal is needed
            cert_status = await self.check_certificate_expiry()

            if not cert_status.get("renewal_needed", False):
                return {
                    "success": True,
                    "message": "Certificate renewal not needed",
                    "days_until_expiry": cert_status.get("days_until_expiry", 0),
                }

            # Run renewal
            result = subprocess.run(["certbot", "renew", "--quiet"], capture_output=True, text=True)

            if result.returncode == 0:
                # Reload nginx after renewal
                nginx_reload = subprocess.run(
                    ["nginx", "-s", "reload"], capture_output=True, text=True
                )

                return {
                    "success": True,
                    "message": "Certificate renewed successfully",
                    "nginx_reload": nginx_reload.returncode == 0,
                }
            else:
                return {
                    "success": False,
                    "error": result.stderr,
                    "stdout": result.stdout,
                }

        except Exception as e:
            return {"success": False, "error": f"Certificate renewal failed: {str(e)}"}

    def get_nginx_ssl_config(self) -> str:
        """Generate nginx SSL configuration"""
        return f"""
server {{
    listen 80;
    server_name {self.domain} www.{self.domain} api.{self.domain} labelstudio.{self.domain};
    
    # Redirect HTTP to HTTPS
    return 301 https://$server_name$request_uri;
}}

server {{
    listen 443 ssl http2;
    server_name {self.domain} www.{self.domain};
    
    # SSL Configuration
    ssl_certificate {self.cert_dir}/fullchain.pem;
    ssl_certificate_key {self.cert_dir}/privkey.pem;
    ssl_trusted_certificate {self.cert_dir}/chain.pem;
    
    # SSL Security Settings
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers ECDHE-RSA-AES128-GCM-SHA256:ECDHE-RSA-AES256-GCM-SHA384:ECDHE-RSA-AES128-SHA256:ECDHE-RSA-AES256-SHA384:ECDHE-RSA-AES128-SHA:ECDHE-RSA-AES256-SHA:DHE-RSA-AES128-SHA256:DHE-RSA-AES256-SHA256:DHE-RSA-AES128-SHA:DHE-RSA-AES256-SHA:!aNULL:!eNULL:!EXPORT:!DES:!RC4:!3DES:!MD5:!PSK;
    ssl_prefer_server_ciphers off;
    ssl_dhparam /etc/nginx/dhparam.pem;
    
    # SSL Session
    ssl_session_cache shared:SSL:10m;
    ssl_session_timeout 10m;
    ssl_session_tickets off;
    
    # OCSP Stapling
    ssl_stapling on;
    ssl_stapling_verify on;
    resolver 8.8.8.8 8.8.4.4 valid=300s;
    resolver_timeout 5s;
    
    # Security Headers
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains; preload" always;
    add_header X-Frame-Options DENY always;
    add_header X-Content-Type-Options nosniff always;
    add_header X-XSS-Protection "1; mode=block" always;
    add_header Referrer-Policy "strict-origin-when-cross-origin" always;
    add_header Content-Security-Policy "default-src 'self'; script-src 'self' 'unsafe-inline' 'unsafe-eval'; style-src 'self' 'unsafe-inline'; img-src 'self' data: https:; font-src 'self' data:;" always;
    
    # Main application
    location / {{
        proxy_pass http://frontend:3000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Forwarded-Host $host;
        proxy_set_header X-Forwarded-Port $server_port;
    }}
}}

server {{
    listen 443 ssl http2;
    server_name api.{self.domain};
    
    # SSL Configuration (same as above)
    ssl_certificate {self.cert_dir}/fullchain.pem;
    ssl_certificate_key {self.cert_dir}/privkey.pem;
    ssl_trusted_certificate {self.cert_dir}/chain.pem;
    
    # SSL Security Settings (same as above)
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers ECDHE-RSA-AES128-GCM-SHA256:ECDHE-RSA-AES256-GCM-SHA384:ECDHE-RSA-AES128-SHA256:ECDHE-RSA-AES256-SHA384:ECDHE-RSA-AES128-SHA:ECDHE-RSA-AES256-SHA:DHE-RSA-AES128-SHA256:DHE-RSA-AES256-SHA256:DHE-RSA-AES128-SHA:DHE-RSA-AES256-SHA:!aNULL:!eNULL:!EXPORT:!DES:!RC4:!3DES:!MD5:!PSK;
    ssl_prefer_server_ciphers off;
    ssl_session_cache shared:SSL:10m;
    ssl_session_timeout 10m;
    ssl_session_tickets off;
    ssl_stapling on;
    ssl_stapling_verify on;
    
    # Security Headers
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains; preload" always;
    add_header X-Frame-Options DENY always;
    add_header X-Content-Type-Options nosniff always;
    add_header X-XSS-Protection "1; mode=block" always;
    add_header Referrer-Policy "strict-origin-when-cross-origin" always;
    
    # API endpoints
    location / {{
        proxy_pass http://api:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Forwarded-Host $host;
        proxy_set_header X-Forwarded-Port $server_port;
        
        # API-specific settings
        proxy_read_timeout 300;
        proxy_connect_timeout 60;
        proxy_send_timeout 60;
        client_max_body_size 100M;
    }}
}}

server {{
    listen 443 ssl http2;
    server_name labelstudio.{self.domain};
    
    # SSL Configuration (same as above)
    ssl_certificate {self.cert_dir}/fullchain.pem;
    ssl_certificate_key {self.cert_dir}/privkey.pem;
    ssl_trusted_certificate {self.cert_dir}/chain.pem;
    
    # SSL Security Settings (same as above)
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers ECDHE-RSA-AES128-GCM-SHA256:ECDHE-RSA-AES256-GCM-SHA384:ECDHE-RSA-AES128-SHA256:ECDHE-RSA-AES256-SHA384:ECDHE-RSA-AES128-SHA:ECDHE-RSA-AES256-SHA:DHE-RSA-AES128-SHA256:DHE-RSA-AES256-SHA256:DHE-RSA-AES128-SHA:DHE-RSA-AES256-SHA:!aNULL:!eNULL:!EXPORT:!DES:!RC4:!3DES:!MD5:!PSK;
    ssl_prefer_server_ciphers off;
    ssl_session_cache shared:SSL:10m;
    ssl_session_timeout 10m;
    ssl_session_tickets off;
    ssl_stapling on;
    ssl_stapling_verify on;
    
    # Security Headers (relaxed for Label Studio)
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains; preload" always;
    add_header X-Content-Type-Options nosniff always;
    add_header X-XSS-Protection "1; mode=block" always;
    add_header Referrer-Policy "strict-origin-when-cross-origin" always;
    
    # Label Studio
    location / {{
        proxy_pass http://labelstudio:8080;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Forwarded-Host $host;
        proxy_set_header X-Forwarded-Port $server_port;
        
        # Project specific settings
        proxy_read_timeout 300;
        proxy_connect_timeout 60;
        proxy_send_timeout 60;
        client_max_body_size 500M;
    }}
}}
"""


def get_security_headers() -> Dict[str, str]:
    """Get production security headers"""
    return {
        "Strict-Transport-Security": "max-age=31536000; includeSubDomains; preload",
        "X-Frame-Options": "DENY",
        "X-Content-Type-Options": "nosniff",
        "X-XSS-Protection": "1; mode=block",
        "Referrer-Policy": "strict-origin-when-cross-origin",
        "Content-Security-Policy": (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline' 'unsafe-eval'; "
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data: https:; "
            "font-src 'self' data:; "
            "connect-src 'self'; "
            "frame-ancestors 'none';"
        ),
        "Permissions-Policy": (
            "geolocation=(), "
            "microphone=(), "
            "camera=(), "
            "payment=(), "
            "usb=(), "
            "magnetometer=(), "
            "accelerometer=(), "
            "gyroscope=()"
        ),
    }


async def generate_dhparam() -> Dict:
    """Generate DH parameters for enhanced security"""
    try:
        dhparam_path = "/etc/nginx/dhparam.pem"

        # Check if already exists
        if Path(dhparam_path).exists():
            return {
                "success": True,
                "message": "DH parameters already exist",
                "path": dhparam_path,
            }

        # Generate DH parameters (this takes a while)
        result = subprocess.run(
            ["openssl", "dhparam", "-out", dhparam_path, "2048"],
            capture_output=True,
            text=True,
            timeout=300,  # 5 minutes timeout
        )

        if result.returncode == 0:
            return {
                "success": True,
                "message": "DH parameters generated successfully",
                "path": dhparam_path,
            }
        else:
            return {"success": False, "error": result.stderr}

    except subprocess.TimeoutExpired:
        return {"success": False, "error": "DH parameter generation timed out"}
    except Exception as e:
        return {"success": False, "error": f"DH parameter generation failed: {str(e)}"}


def create_ssl_monitoring_script() -> str:
    """Create SSL monitoring script for cron"""
    return """#!/bin/bash
# SSL Certificate Monitoring Script for BenGER
# Add to crontab: 0 2 * * * /usr/local/bin/ssl-monitor.sh

DOMAIN="${DOMAIN:-your-domain.com}"
EMAIL="${ALERT_EMAIL:-admin@your-domain.com}"
WEBHOOK="${SLACK_WEBHOOK:-}"

# Check certificate expiry
EXPIRY_DAYS=$(echo | openssl s_client -servername $DOMAIN -connect $DOMAIN:443 2>/dev/null | openssl x509 -noout -dates | grep notAfter | cut -d= -f2 | xargs -I {} date -d "{}" +%s)
CURRENT_TIME=$(date +%s)
DAYS_LEFT=$(( ($EXPIRY_DAYS - $CURRENT_TIME) / 86400 ))

if [ $DAYS_LEFT -le 7 ]; then
    # Send alert
    MESSAGE="⚠️ SSL Certificate for $DOMAIN expires in $DAYS_LEFT days!"
    
    # Email alert
    echo "$MESSAGE" | mail -s "SSL Certificate Expiry Alert" $EMAIL
    
    # Slack webhook (if configured)
    if [ -n "$WEBHOOK" ]; then
        curl -X POST -H 'Content-type: application/json' \
            --data "{\\"text\\":\\"$MESSAGE\\"}" $WEBHOOK
    fi
    
    # Log alert
    echo "$(date): $MESSAGE" >> /var/log/ssl-monitor.log
fi

# Auto-renewal attempt
if [ $DAYS_LEFT -le 30 ]; then
    echo "$(date): Attempting certificate renewal" >> /var/log/ssl-monitor.log
    certbot renew --quiet && nginx -s reload
fi
"""


async def setup_ssl_automation(domain: str, email: str) -> Dict:
    """Setup complete SSL automation"""
    manager = SSLTLSManager(domain, email)

    results = {
        "ssl_setup": await manager.setup_letsencrypt(),
        "dhparam": await generate_dhparam(),
        "nginx_config": manager.get_nginx_ssl_config(),
        "monitoring_script": create_ssl_monitoring_script(),
        "security_headers": get_security_headers(),
    }

    # Check certificate status
    cert_status = await manager.check_certificate_expiry()
    results["certificate_status"] = cert_status

    return results


if __name__ == "__main__":
    # Test SSL setup
    import sys

    if len(sys.argv) < 3:
        print("Usage: python ssl_tls_config.py <domain> <email>")
        sys.exit(1)

    domain = sys.argv[1]
    email = sys.argv[2]

    async def main():
        results = await setup_ssl_automation(domain, email)
        print(f"SSL Setup Results for {domain}:")
        for key, value in results.items():
            print(f"  {key}: {value}")

    asyncio.run(main())
