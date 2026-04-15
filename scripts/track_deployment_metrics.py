#!/usr/bin/env python3
"""
Deployment Metrics Tracking for Trunk-Based Development

Tracks and analyzes deployment frequency, lead time, and other TBD KPIs.
"""

import os
import json
import logging
import argparse
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
import subprocess
from pathlib import Path

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class TBDMetricsTracker:
    """Track and analyze TBD metrics"""
    
    def __init__(self, repo_path: str = '.'):
        self.repo_path = Path(repo_path)
        self.metrics_file = self.repo_path / 'deployment_metrics.json'
        
    def record_deployment(self, services: List[str], commit_hash: str = None) -> Dict[str, Any]:
        """Record a deployment event"""
        if commit_hash is None:
            commit_hash = self._get_current_commit()
        
        deployment_event = {
            'timestamp': datetime.utcnow().isoformat(),
            'commit_hash': commit_hash,
            'services_deployed': services,
            'deployment_id': f"deploy-{datetime.utcnow().strftime('%Y%m%d-%H%M%S')}"
        }
        
        # Load existing metrics
        metrics = self._load_metrics()
        if 'deployments' not in metrics:
            metrics['deployments'] = []
        
        metrics['deployments'].append(deployment_event)
        
        # Save updated metrics
        self._save_metrics(metrics)
        
        logger.info(f"Recorded deployment: {services} at {deployment_event['timestamp']}")
        return deployment_event
    
    def calculate_deployment_frequency(self, days: int = 7) -> Dict[str, Any]:
        """Calculate deployment frequency over specified period"""
        metrics = self._load_metrics()
        deployments = metrics.get('deployments', [])
        
        # Filter deployments to the specified period
        cutoff_date = datetime.utcnow() - timedelta(days=days)
        recent_deployments = [
            d for d in deployments
            if datetime.fromisoformat(d['timestamp']) > cutoff_date
        ]
        
        # Group by day
        daily_deployments = {}
        for deployment in recent_deployments:
            date = datetime.fromisoformat(deployment['timestamp']).date()
            if date not in daily_deployments:
                daily_deployments[date] = 0
            daily_deployments[date] += 1
        
        # Calculate metrics
        total_deployments = len(recent_deployments)
        days_with_deployments = len(daily_deployments)
        avg_deployments_per_day = total_deployments / days if days > 0 else 0
        
        # TBD target: >5 deployments per week
        weekly_target = 5
        meets_target = total_deployments >= weekly_target if days >= 7 else None
        
        return {
            'period_days': days,
            'total_deployments': total_deployments,
            'days_with_deployments': days_with_deployments,
            'avg_deployments_per_day': round(avg_deployments_per_day, 2),
            'meets_weekly_target': meets_target,
            'target_weekly_deployments': weekly_target,
            'daily_breakdown': {str(k): v for k, v in daily_deployments.items()}
        }
    
    def calculate_lead_time(self, limit: int = 10) -> Dict[str, Any]:
        """Calculate lead time for changes (commit to deployment)"""
        metrics = self._load_metrics()
        deployments = metrics.get('deployments', [])
        
        # Get recent deployments
        recent_deployments = sorted(
            deployments, 
            key=lambda x: x['timestamp'], 
            reverse=True
        )[:limit]
        
        lead_times = []
        for deployment in recent_deployments:
            commit_hash = deployment['commit_hash']
            deploy_time = datetime.fromisoformat(deployment['timestamp'])
            
            # Get commit time
            commit_time = self._get_commit_time(commit_hash)
            if commit_time:
                lead_time_hours = (deploy_time - commit_time).total_seconds() / 3600
                lead_times.append({
                    'commit_hash': commit_hash[:8],
                    'commit_time': commit_time.isoformat(),
                    'deploy_time': deploy_time.isoformat(),
                    'lead_time_hours': round(lead_time_hours, 2)
                })
        
        if not lead_times:
            return {'error': 'No lead time data available'}
        
        # Calculate statistics
        hours = [lt['lead_time_hours'] for lt in lead_times]
        avg_lead_time = sum(hours) / len(hours)
        min_lead_time = min(hours)
        max_lead_time = max(hours)
        
        # TBD target: <24 hours
        target_hours = 24
        fast_deployments = sum(1 for h in hours if h < target_hours)
        meets_target = avg_lead_time < target_hours
        
        return {
            'sample_size': len(lead_times),
            'avg_lead_time_hours': round(avg_lead_time, 2),
            'min_lead_time_hours': round(min_lead_time, 2),
            'max_lead_time_hours': round(max_lead_time, 2),
            'fast_deployments': fast_deployments,
            'fast_deployment_rate': round(fast_deployments / len(hours) * 100, 1),
            'meets_target': meets_target,
            'target_hours': target_hours,
            'lead_times': lead_times
        }
    
    def analyze_pr_metrics(self, days: int = 30) -> Dict[str, Any]:
        """Analyze PR metrics for TBD compliance"""
        try:
            # Get recent PRs
            cutoff_date = (datetime.utcnow() - timedelta(days=days)).strftime('%Y-%m-%d')
            
            # Use GitHub CLI to get PR data
            cmd = [
                'gh', 'pr', 'list',
                '--state', 'all',
                '--limit', '100',
                '--json', 'number,title,state,createdAt,closedAt,additions,deletions'
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True, cwd=self.repo_path)
            if result.returncode != 0:
                logger.warning("GitHub CLI not available, skipping PR metrics")
                return {'error': 'GitHub CLI not available'}
            
            prs = json.loads(result.stdout)
            
            # Filter to recent PRs
            recent_prs = []
            for pr in prs:
                created_at = datetime.fromisoformat(pr['createdAt'].replace('Z', '+00:00'))
                if created_at.date() >= datetime.fromisoformat(cutoff_date).date():
                    recent_prs.append(pr)
            
            if not recent_prs:
                return {'error': 'No recent PRs found'}
            
            # Analyze PR sizes
            pr_sizes = []
            large_prs = 0
            closed_prs = [pr for pr in recent_prs if pr['state'] == 'MERGED']
            
            for pr in recent_prs:
                size = pr.get('additions', 0) + pr.get('deletions', 0)
                pr_sizes.append(size)
                
                if size > 400:  # TBD size limit
                    large_prs += 1
            
            # Calculate PR age for closed PRs
            pr_ages = []
            for pr in closed_prs:
                if pr.get('closedAt'):
                    created = datetime.fromisoformat(pr['createdAt'].replace('Z', '+00:00'))
                    closed = datetime.fromisoformat(pr['closedAt'].replace('Z', '+00:00'))
                    age_hours = (closed - created).total_seconds() / 3600
                    pr_ages.append(age_hours)
            
            # Calculate metrics
            avg_pr_size = sum(pr_sizes) / len(pr_sizes) if pr_sizes else 0
            large_pr_rate = (large_prs / len(recent_prs) * 100) if recent_prs else 0
            avg_pr_age = sum(pr_ages) / len(pr_ages) if pr_ages else 0
            
            # TBD compliance
            size_compliant = avg_pr_size <= 400
            age_compliant = avg_pr_age <= 24  # Target: <24 hours
            
            return {
                'period_days': days,
                'total_prs': len(recent_prs),
                'merged_prs': len(closed_prs),
                'avg_pr_size_lines': round(avg_pr_size, 0),
                'large_prs': large_prs,
                'large_pr_rate_percent': round(large_pr_rate, 1),
                'avg_pr_age_hours': round(avg_pr_age, 2),
                'size_compliant': size_compliant,
                'age_compliant': age_compliant,
                'tbd_compliant': size_compliant and age_compliant
            }
            
        except Exception as e:
            logger.error(f"Failed to analyze PR metrics: {e}")
            return {'error': str(e)}
    
    def generate_tbd_scorecard(self) -> Dict[str, Any]:
        """Generate overall TBD compliance scorecard"""
        deployment_freq = self.calculate_deployment_frequency(7)
        lead_time = self.calculate_lead_time(10)
        pr_metrics = self.analyze_pr_metrics(30)
        
        # Calculate overall score
        scores = []
        
        # Deployment frequency (40% weight)
        if deployment_freq.get('meets_weekly_target'):
            scores.append(100 * 0.4)
        else:
            freq_score = min(100, deployment_freq.get('total_deployments', 0) / 5 * 100)
            scores.append(freq_score * 0.4)
        
        # Lead time (30% weight)
        if not lead_time.get('error'):
            if lead_time.get('meets_target'):
                scores.append(100 * 0.3)
            else:
                # Partial score based on fast deployment rate
                fast_rate = lead_time.get('fast_deployment_rate', 0)
                scores.append(fast_rate * 0.3)
        
        # PR compliance (30% weight)
        if not pr_metrics.get('error'):
            if pr_metrics.get('tbd_compliant'):
                scores.append(100 * 0.3)
            else:
                # Partial score
                size_score = 50 if pr_metrics.get('size_compliant') else 0
                age_score = 50 if pr_metrics.get('age_compliant') else 0
                scores.append((size_score + age_score) * 0.3 / 100)
        
        overall_score = sum(scores) if scores else 0
        
        # Determine grade
        if overall_score >= 90:
            grade = 'A'
        elif overall_score >= 80:
            grade = 'B'
        elif overall_score >= 70:
            grade = 'C'
        elif overall_score >= 60:
            grade = 'D'
        else:
            grade = 'F'
        
        return {
            'timestamp': datetime.utcnow().isoformat(),
            'overall_score': round(overall_score, 1),
            'grade': grade,
            'deployment_frequency': deployment_freq,
            'lead_time': lead_time,
            'pr_metrics': pr_metrics,
            'recommendations': self._generate_recommendations(deployment_freq, lead_time, pr_metrics)
        }
    
    def _generate_recommendations(self, deploy_freq: Dict, lead_time: Dict, pr_metrics: Dict) -> List[str]:
        """Generate improvement recommendations"""
        recommendations = []
        
        # Deployment frequency
        if not deploy_freq.get('meets_weekly_target', True):
            recommendations.append("Increase deployment frequency to >5 per week")
        
        # Lead time
        if not lead_time.get('error') and not lead_time.get('meets_target', True):
            recommendations.append("Reduce lead time to <24 hours through smaller PRs and faster reviews")
        
        # PR size
        if not pr_metrics.get('error'):
            if not pr_metrics.get('size_compliant', True):
                recommendations.append("Keep PRs under 400 lines for faster reviews")
            
            if not pr_metrics.get('age_compliant', True):
                recommendations.append("Merge PRs within 24 hours of creation")
            
            if pr_metrics.get('large_pr_rate_percent', 0) > 20:
                recommendations.append("Reduce large PR rate to <20% through better planning")
        
        if not recommendations:
            recommendations.append("TBD practices are working well! Continue current workflow")
        
        return recommendations
    
    def _get_current_commit(self) -> str:
        """Get current commit hash"""
        try:
            result = subprocess.run(
                ['git', 'rev-parse', 'HEAD'],
                capture_output=True,
                text=True,
                cwd=self.repo_path
            )
            return result.stdout.strip()
        except Exception:
            return 'unknown'
    
    def _get_commit_time(self, commit_hash: str) -> Optional[datetime]:
        """Get commit timestamp"""
        try:
            result = subprocess.run(
                ['git', 'show', '-s', '--format=%ci', commit_hash],
                capture_output=True,
                text=True,
                cwd=self.repo_path
            )
            if result.returncode == 0:
                return datetime.fromisoformat(result.stdout.strip().replace(' ', 'T'))
        except Exception:
            pass
        return None
    
    def _load_metrics(self) -> Dict[str, Any]:
        """Load metrics from file"""
        if self.metrics_file.exists():
            try:
                with open(self.metrics_file, 'r') as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(f"Failed to load metrics: {e}")
        return {}
    
    def _save_metrics(self, metrics: Dict[str, Any]) -> None:
        """Save metrics to file"""
        try:
            with open(self.metrics_file, 'w') as f:
                json.dump(metrics, f, indent=2, default=str)
        except Exception as e:
            logger.error(f"Failed to save metrics: {e}")

def main():
    parser = argparse.ArgumentParser(description='Track TBD deployment metrics')
    parser.add_argument('--repo-path', default='.', help='Path to git repository')
    
    subparsers = parser.add_subparsers(dest='command', help='Available commands')
    
    # Record deployment
    record_parser = subparsers.add_parser('record', help='Record a deployment')
    record_parser.add_argument('--services', nargs='+', required=True,
                             help='Services deployed (e.g., api frontend workers)')
    record_parser.add_argument('--commit', help='Commit hash (default: current)')
    
    # Show deployment frequency
    freq_parser = subparsers.add_parser('frequency', help='Show deployment frequency')
    freq_parser.add_argument('--days', type=int, default=7, help='Period in days')
    
    # Show lead time
    lead_parser = subparsers.add_parser('lead-time', help='Show lead time metrics')
    lead_parser.add_argument('--limit', type=int, default=10, help='Number of recent deployments')
    
    # Show PR metrics
    pr_parser = subparsers.add_parser('pr-metrics', help='Show PR metrics')
    pr_parser.add_argument('--days', type=int, default=30, help='Period in days')
    
    # Generate scorecard
    scorecard_parser = subparsers.add_parser('scorecard', help='Generate TBD scorecard')
    scorecard_parser.add_argument('--output', help='Output file (default: stdout)')
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return
    
    tracker = TBDMetricsTracker(args.repo_path)
    
    if args.command == 'record':
        result = tracker.record_deployment(args.services, args.commit)
        print(f"✅ Recorded deployment: {result['deployment_id']}")
        
    elif args.command == 'frequency':
        result = tracker.calculate_deployment_frequency(args.days)
        print(f"📊 Deployment Frequency ({args.days} days):")
        print(f"  Total: {result['total_deployments']} deployments")
        print(f"  Days with deployments: {result['days_with_deployments']}")
        print(f"  Average per day: {result['avg_deployments_per_day']}")
        if result['meets_weekly_target'] is not None:
            status = "✅" if result['meets_weekly_target'] else "❌"
            print(f"  Weekly target (5+): {status}")
        
    elif args.command == 'lead-time':
        result = tracker.calculate_lead_time(args.limit)
        if 'error' in result:
            print(f"❌ {result['error']}")
        else:
            print(f"⏱️ Lead Time (last {result['sample_size']} deployments):")
            print(f"  Average: {result['avg_lead_time_hours']} hours")
            print(f"  Range: {result['min_lead_time_hours']} - {result['max_lead_time_hours']} hours")
            print(f"  Fast deployments (<24h): {result['fast_deployments']}/{result['sample_size']} ({result['fast_deployment_rate']}%)")
            status = "✅" if result['meets_target'] else "❌"
            print(f"  Target (<24h): {status}")
        
    elif args.command == 'pr-metrics':
        result = tracker.analyze_pr_metrics(args.days)
        if 'error' in result:
            print(f"❌ {result['error']}")
        else:
            print(f"📋 PR Metrics ({args.days} days):")
            print(f"  Total PRs: {result['total_prs']}")
            print(f"  Average size: {result['avg_pr_size_lines']} lines")
            print(f"  Large PRs (>400): {result['large_prs']} ({result['large_pr_rate_percent']}%)")
            print(f"  Average age: {result['avg_pr_age_hours']} hours")
            size_status = "✅" if result['size_compliant'] else "❌"
            age_status = "✅" if result['age_compliant'] else "❌"
            print(f"  Size compliant: {size_status}")
            print(f"  Age compliant: {age_status}")
        
    elif args.command == 'scorecard':
        result = tracker.generate_tbd_scorecard()
        
        scorecard = f"""
# TBD Scorecard

**Overall Score**: {result['overall_score']}/100 (Grade: {result['grade']})
**Generated**: {result['timestamp']}

## 📊 Metrics Summary

### Deployment Frequency
- Total (7 days): {result['deployment_frequency'].get('total_deployments', 'N/A')}
- Target: 5+ per week
- Status: {'✅' if result['deployment_frequency'].get('meets_weekly_target') else '❌'}

### Lead Time
- Average: {result['lead_time'].get('avg_lead_time_hours', 'N/A')} hours
- Target: <24 hours
- Status: {'✅' if result['lead_time'].get('meets_target') else '❌'}

### PR Compliance
- Average size: {result['pr_metrics'].get('avg_pr_size_lines', 'N/A')} lines
- Average age: {result['pr_metrics'].get('avg_pr_age_hours', 'N/A')} hours
- Status: {'✅' if result['pr_metrics'].get('tbd_compliant') else '❌'}

## 💡 Recommendations
"""
        for rec in result['recommendations']:
            scorecard += f"- {rec}\n"
        
        if args.output:
            with open(args.output, 'w') as f:
                f.write(scorecard)
            print(f"📊 Scorecard saved to {args.output}")
        else:
            print(scorecard)

if __name__ == '__main__':
    main()