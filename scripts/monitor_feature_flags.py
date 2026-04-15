#!/usr/bin/env python3
"""
Feature Flag Monitoring Script

Monitors feature flag usage, performance, and lifecycle for TBD compliance.
Generates alerts for flags requiring cleanup and provides usage metrics.
"""

import os
import sys
import json
import logging
import argparse
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
import redis
import asyncio
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

# Add the API directory to the path for imports
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'services', 'api'))

from models import FeatureFlag, UserFeatureFlag, OrganizationFeatureFlag
from feature_flag_service import FeatureFlagService

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class FeatureFlagMonitor:
    """Monitor feature flag usage and lifecycle for TBD compliance"""
    
    def __init__(self, database_url: str, redis_url: str = None):
        self.engine = create_engine(database_url)
        self.Session = sessionmaker(bind=self.engine)
        self.redis_client = redis.from_url(redis_url) if redis_url else None
        
    def get_all_flags(self) -> List[Dict[str, Any]]:
        """Get all feature flags with their metadata"""
        with self.Session() as session:
            flags = session.query(FeatureFlag).all()
            return [
                {
                    'id': flag.id,
                    'name': flag.name,
                    'description': flag.description,
                    'is_enabled': flag.is_enabled,
                    'created_at': flag.created_at,
                    'updated_at': flag.updated_at,
                    'created_by': flag.created_by,
                    'target_criteria': flag.target_criteria,
                    'rollout_percentage': flag.rollout_percentage
                }
                for flag in flags
            ]
    
    def get_flag_usage_stats(self) -> Dict[str, Any]:
        """Get feature flag usage statistics"""
        with self.Session() as session:
            # Total flags
            total_flags = session.query(FeatureFlag).count()
            
            # Enabled flags
            enabled_flags = session.query(FeatureFlag).filter(
                FeatureFlag.is_enabled == True
            ).count()
            
            # Flags with overrides
            flags_with_user_overrides = session.query(UserFeatureFlag).distinct(
                UserFeatureFlag.feature_flag_id
            ).count()
            
            flags_with_org_overrides = session.query(OrganizationFeatureFlag).distinct(
                OrganizationFeatureFlag.feature_flag_id
            ).count()
            
            # Age analysis
            now = datetime.utcnow()
            old_flags = session.query(FeatureFlag).filter(
                FeatureFlag.created_at < now - timedelta(days=30)
            ).count()
            
            very_old_flags = session.query(FeatureFlag).filter(
                FeatureFlag.created_at < now - timedelta(days=60)
            ).count()
            
            return {
                'total_flags': total_flags,
                'enabled_flags': enabled_flags,
                'disabled_flags': total_flags - enabled_flags,
                'flags_with_user_overrides': flags_with_user_overrides,
                'flags_with_org_overrides': flags_with_org_overrides,
                'old_flags_30_days': old_flags,
                'very_old_flags_60_days': very_old_flags,
                'timestamp': now.isoformat()
            }
    
    def get_cache_performance(self) -> Optional[Dict[str, Any]]:
        """Get feature flag cache performance metrics"""
        if not self.redis_client:
            return None
            
        try:
            info = self.redis_client.info()
            
            # Get all feature flag cache keys
            ff_keys = self.redis_client.keys('feature_flag:*')
            
            # Calculate hit rate (approximate)
            keyspace_hits = info.get('keyspace_hits', 0)
            keyspace_misses = info.get('keyspace_misses', 0)
            total_operations = keyspace_hits + keyspace_misses
            hit_rate = (keyspace_hits / total_operations * 100) if total_operations > 0 else 0
            
            return {
                'total_ff_keys': len(ff_keys),
                'hit_rate_percent': round(hit_rate, 2),
                'keyspace_hits': keyspace_hits,
                'keyspace_misses': keyspace_misses,
                'memory_usage_mb': round(info.get('used_memory', 0) / 1024 / 1024, 2),
                'connected_clients': info.get('connected_clients', 0)
            }
        except Exception as e:
            logger.warning(f"Failed to get cache performance: {e}")
            return None
    
    def check_naming_compliance(self, flags: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Check feature flag naming convention compliance"""
        valid_areas = {
            'ANNOTATION', 'ANALYTICS', 'TASKS', 'USERS', 
            'API', 'UI', 'ADMIN'
        }
        
        compliant_flags = 0
        non_compliant_flags = []
        
        for flag in flags:
            name = flag['name']
            
            # Check format: FEATURE_AREA_DESCRIPTION
            if name.startswith('FEATURE_'):
                parts = name.split('_')
                if len(parts) >= 3:
                    area = parts[1]
                    if area in valid_areas:
                        compliant_flags += 1
                    else:
                        non_compliant_flags.append({
                            'name': name,
                            'issue': f'Invalid area "{area}"',
                            'valid_areas': list(valid_areas)
                        })
                else:
                    non_compliant_flags.append({
                        'name': name,
                        'issue': 'Insufficient name parts',
                        'expected_format': 'FEATURE_AREA_DESCRIPTION'
                    })
            else:
                non_compliant_flags.append({
                    'name': name,
                    'issue': 'Does not start with FEATURE_',
                    'expected_format': 'FEATURE_AREA_DESCRIPTION'
                })
        
        total_flags = len(flags)
        compliance_rate = (compliant_flags / total_flags * 100) if total_flags > 0 else 100
        
        return {
            'total_flags': total_flags,
            'compliant_flags': compliant_flags,
            'non_compliant_flags': len(non_compliant_flags),
            'compliance_rate_percent': round(compliance_rate, 2),
            'violations': non_compliant_flags
        }
    
    def get_cleanup_candidates(self, flags: List[Dict[str, Any]], days_threshold: int = 30) -> List[Dict[str, Any]]:
        """Get flags that are candidates for cleanup"""
        now = datetime.utcnow()
        cleanup_candidates = []
        
        for flag in flags:
            created_at = flag['created_at']
            if isinstance(created_at, str):
                created_at = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
            
            age_days = (now - created_at).days
            
            if age_days >= days_threshold:
                # Additional context for cleanup decision
                is_enabled = flag['is_enabled']
                has_rollout = flag.get('rollout_percentage', 0) > 0
                
                cleanup_candidates.append({
                    'name': flag['name'],
                    'age_days': age_days,
                    'is_enabled': is_enabled,
                    'rollout_percentage': flag.get('rollout_percentage', 0),
                    'created_by': flag.get('created_by', 'unknown'),
                    'description': flag['description'],
                    'urgency': 'high' if age_days > 60 else 'medium' if age_days > 45 else 'low'
                })
        
        # Sort by age (oldest first)
        cleanup_candidates.sort(key=lambda x: x['age_days'], reverse=True)
        
        return cleanup_candidates
    
    def generate_alerts(self, stats: Dict[str, Any], cleanup_candidates: List[Dict[str, Any]], 
                       naming_compliance: Dict[str, Any]) -> List[Dict[str, str]]:
        """Generate alerts for feature flag management"""
        alerts = []
        
        # Cleanup alerts
        urgent_cleanup = [c for c in cleanup_candidates if c['urgency'] == 'high']
        if urgent_cleanup:
            alerts.append({
                'level': 'error',
                'type': 'cleanup_overdue',
                'message': f'{len(urgent_cleanup)} flags are > 60 days old and require immediate cleanup',
                'details': [f"{c['name']} ({c['age_days']} days)" for c in urgent_cleanup[:5]]
            })
        
        medium_cleanup = [c for c in cleanup_candidates if c['urgency'] == 'medium']
        if medium_cleanup:
            alerts.append({
                'level': 'warning',
                'type': 'cleanup_due',
                'message': f'{len(medium_cleanup)} flags are approaching cleanup deadline (30-60 days)',
                'details': [f"{c['name']} ({c['age_days']} days)" for c in medium_cleanup[:5]]
            })
        
        # Naming compliance alerts
        if naming_compliance['compliance_rate_percent'] < 80:
            alerts.append({
                'level': 'warning',
                'type': 'naming_compliance',
                'message': f"Low naming compliance: {naming_compliance['compliance_rate_percent']:.1f}%",
                'details': [v['name'] for v in naming_compliance['violations'][:5]]
            })
        
        # Usage pattern alerts
        if stats['enabled_flags'] == 0 and stats['total_flags'] > 0:
            alerts.append({
                'level': 'warning',
                'type': 'no_enabled_flags',
                'message': 'No feature flags are currently enabled',
                'details': ['Consider enabling flags for gradual feature rollout']
            })
        
        if stats['total_flags'] > 50:
            alerts.append({
                'level': 'info',
                'type': 'high_flag_count',
                'message': f'High number of feature flags ({stats["total_flags"]})',
                'details': ['Regular cleanup recommended for better performance']
            })
        
        return alerts
    
    def calculate_tbd_metrics(self, stats: Dict[str, Any], cleanup_candidates: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Calculate TBD-specific metrics"""
        # Feature flag lifecycle health
        total_flags = stats['total_flags']
        old_flags = len(cleanup_candidates)
        lifecycle_health = max(0, 100 - (old_flags / total_flags * 100)) if total_flags > 0 else 100
        
        # Rollout maturity (enabled flags vs total)
        rollout_maturity = (stats['enabled_flags'] / total_flags * 100) if total_flags > 0 else 0
        
        # Override usage (indicates fine-grained control)
        override_usage = ((stats['flags_with_user_overrides'] + stats['flags_with_org_overrides']) / 
                         total_flags * 100) if total_flags > 0 else 0
        
        return {
            'lifecycle_health_percent': round(lifecycle_health, 2),
            'rollout_maturity_percent': round(rollout_maturity, 2),
            'override_usage_percent': round(override_usage, 2),
            'cleanup_backlog': old_flags,
            'tbd_readiness_score': round((lifecycle_health + rollout_maturity) / 2, 2)
        }
    
    def generate_report(self, format: str = 'json') -> str:
        """Generate comprehensive feature flag monitoring report"""
        logger.info("Generating feature flag monitoring report...")
        
        # Gather all data
        flags = self.get_all_flags()
        stats = self.get_flag_usage_stats()
        cache_perf = self.get_cache_performance()
        naming_compliance = self.check_naming_compliance(flags)
        cleanup_candidates = self.get_cleanup_candidates(flags)
        alerts = self.generate_alerts(stats, cleanup_candidates, naming_compliance)
        tbd_metrics = self.calculate_tbd_metrics(stats, cleanup_candidates)
        
        report = {
            'timestamp': datetime.utcnow().isoformat(),
            'summary': {
                'total_flags': stats['total_flags'],
                'enabled_flags': stats['enabled_flags'],
                'cleanup_candidates': len(cleanup_candidates),
                'alerts_count': len(alerts),
                'tbd_readiness_score': tbd_metrics['tbd_readiness_score']
            },
            'usage_statistics': stats,
            'cache_performance': cache_perf,
            'naming_compliance': naming_compliance,
            'cleanup_candidates': cleanup_candidates,
            'tbd_metrics': tbd_metrics,
            'alerts': alerts
        }
        
        if format == 'json':
            return json.dumps(report, indent=2, default=str)
        elif format == 'markdown':
            return self._format_markdown_report(report)
        else:
            raise ValueError(f"Unsupported format: {format}")
    
    def _format_markdown_report(self, report: Dict[str, Any]) -> str:
        """Format report as markdown"""
        md = f"""# Feature Flag Monitoring Report

**Generated**: {report['timestamp']}
**TBD Readiness Score**: {report['tbd_metrics']['tbd_readiness_score']}%

## 📊 Summary

- **Total Flags**: {report['summary']['total_flags']}
- **Enabled Flags**: {report['summary']['enabled_flags']}
- **Cleanup Candidates**: {report['summary']['cleanup_candidates']}
- **Active Alerts**: {report['summary']['alerts_count']}

## 🚩 Usage Statistics

| Metric | Value |
|--------|-------|
| Total Flags | {report['usage_statistics']['total_flags']} |
| Enabled Flags | {report['usage_statistics']['enabled_flags']} |
| Disabled Flags | {report['usage_statistics']['disabled_flags']} |
| User Overrides | {report['usage_statistics']['flags_with_user_overrides']} |
| Org Overrides | {report['usage_statistics']['flags_with_org_overrides']} |
| Old Flags (30d+) | {report['usage_statistics']['old_flags_30_days']} |
| Very Old Flags (60d+) | {report['usage_statistics']['very_old_flags_60_days']} |

"""

        # Cache performance
        if report['cache_performance']:
            perf = report['cache_performance']
            md += f"""## ⚡ Cache Performance

| Metric | Value |
|--------|-------|
| Cache Keys | {perf['total_ff_keys']} |
| Hit Rate | {perf['hit_rate_percent']}% |
| Memory Usage | {perf['memory_usage_mb']} MB |
| Connected Clients | {perf['connected_clients']} |

"""

        # Naming compliance
        compliance = report['naming_compliance']
        md += f"""## 📝 Naming Compliance

- **Compliance Rate**: {compliance['compliance_rate_percent']}%
- **Compliant Flags**: {compliance['compliant_flags']}
- **Non-compliant Flags**: {compliance['non_compliant_flags']}

"""

        # Alerts
        if report['alerts']:
            md += "## 🚨 Alerts\n\n"
            for alert in report['alerts']:
                level_emoji = {'error': '🔴', 'warning': '⚠️', 'info': 'ℹ️'}.get(alert['level'], '•')
                md += f"### {level_emoji} {alert['message']}\n"
                if alert.get('details'):
                    for detail in alert['details']:
                        md += f"- {detail}\n"
                md += "\n"

        # Cleanup candidates
        if report['cleanup_candidates']:
            md += "## 🧹 Cleanup Candidates\n\n"
            md += "| Flag Name | Age (days) | Status | Urgency |\n"
            md += "|-----------|------------|--------|----------|\n"
            for candidate in report['cleanup_candidates'][:10]:  # Show top 10
                status = "Enabled" if candidate['is_enabled'] else "Disabled"
                md += f"| {candidate['name']} | {candidate['age_days']} | {status} | {candidate['urgency'].title()} |\n"

        # TBD metrics
        tbd = report['tbd_metrics']
        md += f"""

## 🎯 TBD Metrics

- **Lifecycle Health**: {tbd['lifecycle_health_percent']}%
- **Rollout Maturity**: {tbd['rollout_maturity_percent']}%
- **Override Usage**: {tbd['override_usage_percent']}%
- **Cleanup Backlog**: {tbd['cleanup_backlog']} flags

---

*Generated by Feature Flag Monitor for Trunk-Based Development*
"""

        return md

def main():
    parser = argparse.ArgumentParser(description='Monitor feature flags for TBD compliance')
    parser.add_argument('--database-url', default=os.getenv('DATABASE_URL', 
                       'postgresql://postgres:postgres@localhost:5432/benger'))
    parser.add_argument('--redis-url', default=os.getenv('REDIS_URL', 
                       'redis://localhost:6379'))
    parser.add_argument('--format', choices=['json', 'markdown'], default='json',
                       help='Output format')
    parser.add_argument('--output', help='Output file (default: stdout)')
    parser.add_argument('--cleanup-threshold', type=int, default=30,
                       help='Days after which flags are cleanup candidates')
    parser.add_argument('--alerts-only', action='store_true',
                       help='Only show alerts')
    
    args = parser.parse_args()
    
    try:
        monitor = FeatureFlagMonitor(args.database_url, args.redis_url)
        
        if args.alerts_only:
            # Quick alerts check
            flags = monitor.get_all_flags()
            stats = monitor.get_flag_usage_stats()
            naming_compliance = monitor.check_naming_compliance(flags)
            cleanup_candidates = monitor.get_cleanup_candidates(flags, args.cleanup_threshold)
            alerts = monitor.generate_alerts(stats, cleanup_candidates, naming_compliance)
            
            if alerts:
                print(f"🚨 {len(alerts)} alerts found:")
                for alert in alerts:
                    level_emoji = {'error': '🔴', 'warning': '⚠️', 'info': 'ℹ️'}.get(alert['level'], '•')
                    print(f"{level_emoji} {alert['message']}")
                sys.exit(1)
            else:
                print("✅ No alerts")
                sys.exit(0)
        else:
            # Full report
            report = monitor.generate_report(args.format)
            
            if args.output:
                with open(args.output, 'w') as f:
                    f.write(report)
                print(f"Report saved to {args.output}")
            else:
                print(report)
                
    except Exception as e:
        logger.error(f"Failed to generate report: {e}")
        sys.exit(1)

if __name__ == '__main__':
    main()