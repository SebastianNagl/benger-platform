#!/usr/bin/env python3
"""
Production Schema Drift Monitor

This script monitors production database schema for drift and inconsistencies.
It can be run as a scheduled job (cron/kubernetes cronjob) to detect issues early.
"""

import json
import logging
import os
import smtplib
import sys
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import Dict, List, Optional

# Add parent directory to path for imports
sys.path.append(str(Path(__file__).parent.parent))

from app.core.schema_validator import create_validator_from_env

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class SchemaDriftMonitor:
    """Monitor database schema for drift and issues"""

    def __init__(self):
        """Initialize the schema drift monitor"""
        self.validator = create_validator_from_env(mode="lenient")
        self.report_data = {
            "timestamp": datetime.utcnow().isoformat(),
            "environment": os.getenv("ENVIRONMENT", "production"),
            "issues": [],
            "warnings": [],
            "metrics": {},
        }

    def run_monitoring(self) -> Dict:
        """
        Run complete schema monitoring suite

        Returns:
            Dictionary containing monitoring results
        """
        logger.info("Starting schema drift monitoring...")

        # 1. Basic schema validation
        logger.info("Running schema validation...")
        validation_result = self.validator.validate()

        self.report_data["schema_valid"] = validation_result.is_valid
        self.report_data["issues"].extend([str(e) for e in validation_result.errors])
        self.report_data["warnings"].extend([str(w) for w in validation_result.warnings])

        # 2. Type consistency check
        logger.info("Checking type consistency...")
        type_result = self.validator.check_type_consistency()

        if not type_result.is_valid:
            self.report_data["issues"].extend([f"Type mismatch: {e}" for e in type_result.errors])

        # 3. Migration history check
        logger.info("Checking migration history...")
        migration_result = self.validator.check_migration_history()

        if not migration_result.is_valid:
            self.report_data["issues"].extend(
                [f"Migration issue: {e}" for e in migration_result.errors]
            )

        # 4. Collect metrics
        self.report_data["metrics"] = self._collect_metrics()

        # 5. Determine severity
        self.report_data["severity"] = self._determine_severity()

        logger.info(f"Monitoring complete. Severity: {self.report_data['severity']}")

        return self.report_data

    def _collect_metrics(self) -> Dict:
        """Collect schema-related metrics"""
        metrics = {
            "total_issues": len(self.report_data["issues"]),
            "total_warnings": len(self.report_data["warnings"]),
            "tables_checked": 0,
            "columns_checked": 0,
        }

        if self.validator.inspector:
            try:
                tables = self.validator.inspector.get_table_names()
                metrics["tables_checked"] = len(tables)

                total_columns = 0
                for table in tables:
                    columns = self.validator.inspector.get_columns(table)
                    total_columns += len(columns)
                metrics["columns_checked"] = total_columns
            except Exception as e:
                logger.error(f"Error collecting metrics: {e}")

        return metrics

    def _determine_severity(self) -> str:
        """
        Determine the severity of detected issues

        Returns:
            Severity level: CRITICAL, HIGH, MEDIUM, LOW, or OK
        """
        if not self.report_data["issues"] and not self.report_data["warnings"]:
            return "OK"

        # Check for critical issues
        critical_keywords = ["missing_table", "type_mismatch", "migration_history"]
        for issue in self.report_data["issues"]:
            if any(keyword in str(issue).lower() for keyword in critical_keywords):
                return "CRITICAL"

        # Determine based on count
        issue_count = len(self.report_data["issues"])
        warning_count = len(self.report_data["warnings"])

        if issue_count > 5:
            return "CRITICAL"
        elif issue_count > 2:
            return "HIGH"
        elif issue_count > 0:
            return "MEDIUM"
        elif warning_count > 5:
            return "MEDIUM"
        elif warning_count > 0:
            return "LOW"
        else:
            return "OK"

    def send_alert(self, recipient_emails: List[str], smtp_config: Optional[Dict] = None):
        """
        Send email alert if issues are detected

        Args:
            recipient_emails: List of email addresses to notify
            smtp_config: SMTP configuration (host, port, user, password)
        """
        if self.report_data["severity"] == "OK":
            logger.info("No issues detected, skipping alert")
            return

        if not smtp_config:
            smtp_config = {
                "host": os.getenv("SMTP_HOST", "localhost"),
                "port": int(os.getenv("SMTP_PORT", "587")),
                "user": os.getenv("SMTP_USER"),
                "password": os.getenv("SMTP_PASSWORD"),
                "from_email": os.getenv("SMTP_FROM", "schema-monitor@benger.com"),
            }

        subject = f"[{self.report_data['severity']}] Schema Drift Detected in {self.report_data['environment']}"

        # Create email body
        body = self._format_email_body()

        # Send email
        try:
            msg = MIMEMultipart()
            msg["From"] = smtp_config["from_email"]
            msg["To"] = ", ".join(recipient_emails)
            msg["Subject"] = subject

            msg.attach(MIMEText(body, "html"))

            with smtplib.SMTP(smtp_config["host"], smtp_config["port"]) as server:
                if smtp_config.get("user") and smtp_config.get("password"):
                    server.starttls()
                    server.login(smtp_config["user"], smtp_config["password"])

                server.send_message(msg)
                logger.info(f"Alert sent to {recipient_emails}")

        except Exception as e:
            logger.error(f"Failed to send alert: {e}")

    def _format_email_body(self) -> str:
        """Format the email body as HTML"""
        severity_colors = {
            "CRITICAL": "#FF0000",
            "HIGH": "#FF8800",
            "MEDIUM": "#FFAA00",
            "LOW": "#888888",
            "OK": "#00AA00",
        }

        color = severity_colors.get(self.report_data["severity"], "#000000")

        html = f"""
        <html>
        <body>
        <h2 style="color: {color};">Schema Drift Detection Report</h2>
        
        <p><strong>Environment:</strong> {self.report_data['environment']}</p>
        <p><strong>Timestamp:</strong> {self.report_data['timestamp']}</p>
        <p><strong>Severity:</strong> <span style="color: {color}; font-weight: bold;">{self.report_data['severity']}</span></p>
        
        <h3>Metrics</h3>
        <ul>
            <li>Tables Checked: {self.report_data['metrics']['tables_checked']}</li>
            <li>Columns Checked: {self.report_data['metrics']['columns_checked']}</li>
            <li>Total Issues: {self.report_data['metrics']['total_issues']}</li>
            <li>Total Warnings: {self.report_data['metrics']['total_warnings']}</li>
        </ul>
        """

        if self.report_data["issues"]:
            html += "<h3>Issues Detected</h3><ul>"
            for issue in self.report_data["issues"]:
                html += f"<li style='color: red;'>{issue}</li>"
            html += "</ul>"

        if self.report_data["warnings"]:
            html += "<h3>Warnings</h3><ul>"
            for warning in self.report_data["warnings"]:
                html += f"<li style='color: orange;'>{warning}</li>"
            html += "</ul>"

        html += """
        <p><strong>Action Required:</strong> Please review and fix the detected issues.</p>
        </body>
        </html>
        """

        return html

    def create_github_issue(self, repo: str, token: str):
        """
        Create a GitHub issue for detected schema drift

        Args:
            repo: Repository name (owner/repo)
            token: GitHub personal access token
        """
        if self.report_data["severity"] in ["OK", "LOW"]:
            logger.info("Severity too low for GitHub issue")
            return

        try:
            import requests

            url = f"https://api.github.com/repos/{repo}/issues"

            title = f"[Schema Drift] {self.report_data['severity']} issues detected in {self.report_data['environment']}"

            body = f"""## Schema Drift Detection Report

**Environment:** {self.report_data['environment']}
**Timestamp:** {self.report_data['timestamp']}
**Severity:** {self.report_data['severity']}

### Metrics
- Tables Checked: {self.report_data['metrics']['tables_checked']}
- Columns Checked: {self.report_data['metrics']['columns_checked']}
- Total Issues: {self.report_data['metrics']['total_issues']}
- Total Warnings: {self.report_data['metrics']['total_warnings']}

### Issues Detected
"""

            if self.report_data["issues"]:
                for issue in self.report_data["issues"]:
                    body += f"- ❌ {issue}\n"

            if self.report_data["warnings"]:
                body += "\n### Warnings\n"
                for warning in self.report_data["warnings"]:
                    body += f"- ⚠️ {warning}\n"

            body += "\n**This issue was automatically created by the schema drift monitor.**"

            headers = {
                "Authorization": f"token {token}",
                "Accept": "application/vnd.github.v3+json",
            }

            data = {
                "title": title,
                "body": body,
                "labels": ["bug", "database", "automated"],
            }

            response = requests.post(url, json=data, headers=headers)

            if response.status_code == 201:
                issue_url = response.json()["html_url"]
                logger.info(f"GitHub issue created: {issue_url}")
            else:
                logger.error(f"Failed to create GitHub issue: {response.text}")

        except Exception as e:
            logger.error(f"Error creating GitHub issue: {e}")

    def save_report(self, output_path: str):
        """
        Save the monitoring report to a file

        Args:
            output_path: Path to save the report
        """
        try:
            with open(output_path, "w") as f:
                json.dump(self.report_data, f, indent=2, default=str)
            logger.info(f"Report saved to {output_path}")
        except Exception as e:
            logger.error(f"Failed to save report: {e}")


def main():
    """Main entry point for the schema drift monitor"""
    import argparse

    parser = argparse.ArgumentParser(description="Monitor database schema for drift")
    parser.add_argument("--email", nargs="+", help="Email addresses to send alerts to")
    parser.add_argument("--github-repo", help="GitHub repository (owner/repo) to create issues in")
    parser.add_argument("--github-token", help="GitHub personal access token")
    parser.add_argument(
        "--output",
        default="/tmp/schema_drift_report.json",
        help="Path to save the report (default: /tmp/schema_drift_report.json)",
    )
    parser.add_argument(
        "--exit-on-error",
        action="store_true",
        help="Exit with non-zero code if issues are detected",
    )

    args = parser.parse_args()

    # Run monitoring
    monitor = SchemaDriftMonitor()
    report = monitor.run_monitoring()

    # Save report
    monitor.save_report(args.output)

    # Send alerts
    if args.email:
        monitor.send_alert(args.email)

    # Create GitHub issue
    if args.github_repo and args.github_token:
        monitor.create_github_issue(args.github_repo, args.github_token)
    elif args.github_repo:
        # Try to use GITHUB_TOKEN environment variable
        token = os.getenv("GITHUB_TOKEN")
        if token:
            monitor.create_github_issue(args.github_repo, token)

    # Print summary
    print(f"Schema Drift Monitoring Complete")
    print(f"Severity: {report['severity']}")
    print(f"Issues: {report['metrics']['total_issues']}")
    print(f"Warnings: {report['metrics']['total_warnings']}")

    # Exit with appropriate code
    if args.exit_on_error and report["severity"] not in ["OK", "LOW"]:
        sys.exit(1)
    else:
        sys.exit(0)


if __name__ == "__main__":
    main()
