"""
Code Monitors

Sourcegraph-inspired code monitors that watch for code changes
matching specific patterns and trigger alerts.
"""

from typing import List, Dict, Optional, Any, Callable, Set
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
import re
import hashlib
import threading
import structlog

logger = structlog.get_logger()


class AlertSeverity(Enum):
    """Alert severity levels"""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class TriggerType(Enum):
    """Types of triggers"""
    NEW_MATCH = "new_match"        # Pattern appears where it didn't before
    REMOVED = "removed"             # Pattern was removed
    MODIFIED = "modified"           # Existing match was changed
    THRESHOLD = "threshold"         # Count exceeds threshold


@dataclass
class MonitorRule:
    """A code monitoring rule"""
    id: str
    name: str
    description: str
    pattern: str
    language: Optional[str] = None
    file_pattern: Optional[str] = None
    repo_pattern: Optional[str] = None
    trigger: TriggerType = TriggerType.NEW_MATCH
    severity: AlertSeverity = AlertSeverity.WARNING
    threshold: int = 0
    enabled: bool = True
    created_at: datetime = field(default_factory=datetime.now)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "pattern": self.pattern,
            "language": self.language,
            "trigger": self.trigger.value,
            "severity": self.severity.value,
            "threshold": self.threshold,
            "enabled": self.enabled
        }


@dataclass
class Alert:
    """An alert triggered by a monitor"""
    id: str
    monitor_id: str
    monitor_name: str
    message: str
    file_path: str
    line: int
    matched_text: str
    severity: AlertSeverity
    timestamp: datetime = field(default_factory=datetime.now)
    acknowledged: bool = False
    resolved: bool = False
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "monitor_id": self.monitor_id,
            "monitor_name": self.monitor_name,
            "message": self.message,
            "file": self.file_path,
            "line": self.line,
            "matched_text": self.matched_text,
            "severity": self.severity.value,
            "timestamp": self.timestamp.isoformat(),
            "acknowledged": self.acknowledged,
            "resolved": self.resolved
        }


class CodeMonitor:
    """
    Monitors code for specific patterns and triggers alerts.
    
    Features:
    - Watch for security vulnerabilities
    - Track deprecated API usage
    - Monitor for code quality issues
    - Alert on specific pattern appearances
    """
    
    def __init__(self):
        self.rules: Dict[str, MonitorRule] = {}
        self.alerts: List[Alert] = []
        self.alert_handlers: List[Callable[[Alert], None]] = []
        self.match_history: Dict[str, Set[str]] = {}  # rule_id -> set of match hashes
        self._lock = threading.Lock()
        
        # Add default security monitors
        self._add_default_monitors()
    
    def _add_default_monitors(self):
        """Add default security monitoring rules"""
        defaults = [
            MonitorRule(
                id="sec-001",
                name="Hardcoded Secrets",
                description="Detects hardcoded passwords and API keys",
                pattern=r"(?:password|api_key|secret|token)\s*=\s*['\"][^'\"]+['\"]",
                severity=AlertSeverity.CRITICAL
            ),
            MonitorRule(
                id="sec-002",
                name="Eval Usage",
                description="Detects use of eval() which can lead to code injection",
                pattern=r"\beval\s*\(",
                severity=AlertSeverity.ERROR
            ),
            MonitorRule(
                id="sec-003",
                name="SQL Injection Risk",
                description="Detects potential SQL injection patterns",
                pattern=r"execute\([^)]*%s|execute\([^)]*\+|cursor\.execute\([^)]*f['\"]",
                severity=AlertSeverity.ERROR
            ),
            MonitorRule(
                id="dep-001",
                name="Deprecated APIs",
                description="Tracks deprecated function usage",
                pattern=r"@deprecated|# deprecated|DEPRECATED",
                severity=AlertSeverity.WARNING
            ),
            MonitorRule(
                id="qual-001",
                name="TODO/FIXME",
                description="Tracks TODO and FIXME comments",
                pattern=r"(?:TODO|FIXME|HACK|XXX):",
                severity=AlertSeverity.INFO
            ),
        ]
        
        for rule in defaults:
            self.rules[rule.id] = rule
    
    def add_rule(self, rule: MonitorRule):
        """Add a monitoring rule"""
        self.rules[rule.id] = rule
        logger.info("Added monitor rule", rule_id=rule.id, name=rule.name)
    
    def remove_rule(self, rule_id: str) -> bool:
        """Remove a monitoring rule"""
        if rule_id in self.rules:
            del self.rules[rule_id]
            return True
        return False
    
    def add_alert_handler(self, handler: Callable[[Alert], None]):
        """Add a handler for alerts"""
        self.alert_handlers.append(handler)
    
    def scan(
        self,
        file_path: str,
        content: str,
        language: Optional[str] = None
    ) -> List[Alert]:
        """
        Scan a file for matching patterns.
        """
        new_alerts = []
        
        for rule in self.rules.values():
            if not rule.enabled:
                continue
            
            # Check language filter
            if rule.language and language != rule.language:
                continue
            
            # Check file pattern
            if rule.file_pattern:
                if not re.match(rule.file_pattern, file_path):
                    continue
            
            # Find matches
            matches = list(re.finditer(rule.pattern, content, re.IGNORECASE))
            
            for match in matches:
                match_hash = self._hash_match(file_path, match.start(), match.group())
                
                # Check if this is a new match
                with self._lock:
                    rule_matches = self.match_history.setdefault(rule.id, set())
                    is_new = match_hash not in rule_matches
                    
                    if is_new and rule.trigger == TriggerType.NEW_MATCH:
                        rule_matches.add(match_hash)
                        
                        # Calculate line number
                        line = content[:match.start()].count('\n') + 1
                        
                        alert = Alert(
                            id=f"{rule.id}-{len(self.alerts)}",
                            monitor_id=rule.id,
                            monitor_name=rule.name,
                            message=f"{rule.name}: {rule.description}",
                            file_path=file_path,
                            line=line,
                            matched_text=match.group()[:100],  # Truncate
                            severity=rule.severity
                        )
                        
                        self.alerts.append(alert)
                        new_alerts.append(alert)
                        
                        # Notify handlers
                        for handler in self.alert_handlers:
                            try:
                                handler(alert)
                            except Exception as e:
                                logger.error("Alert handler error", error=str(e))
            
            # Check threshold trigger
            if rule.trigger == TriggerType.THRESHOLD:
                if len(matches) > rule.threshold:
                    alert = Alert(
                        id=f"{rule.id}-threshold-{len(self.alerts)}",
                        monitor_id=rule.id,
                        monitor_name=rule.name,
                        message=f"Threshold exceeded: {len(matches)} matches (threshold: {rule.threshold})",
                        file_path=file_path,
                        line=0,
                        matched_text=f"{len(matches)} matches found",
                        severity=rule.severity
                    )
                    self.alerts.append(alert)
                    new_alerts.append(alert)
        
        return new_alerts
    
    def _hash_match(self, file_path: str, position: int, text: str) -> str:
        """Create hash for a match to track uniqueness"""
        data = f"{file_path}:{position}:{text}"
        return hashlib.md5(data.encode()).hexdigest()
    
    def get_alerts(
        self,
        severity: Optional[AlertSeverity] = None,
        unacknowledged_only: bool = False,
        limit: int = 100
    ) -> List[Alert]:
        """Get alerts with optional filters"""
        filtered = self.alerts
        
        if severity:
            filtered = [a for a in filtered if a.severity == severity]
        
        if unacknowledged_only:
            filtered = [a for a in filtered if not a.acknowledged]
        
        return filtered[-limit:]
    
    def acknowledge_alert(self, alert_id: str) -> bool:
        """Acknowledge an alert"""
        for alert in self.alerts:
            if alert.id == alert_id:
                alert.acknowledged = True
                return True
        return False
    
    def resolve_alert(self, alert_id: str) -> bool:
        """Mark alert as resolved"""
        for alert in self.alerts:
            if alert.id == alert_id:
                alert.resolved = True
                return True
        return False
    
    def get_stats(self) -> Dict[str, Any]:
        """Get monitor statistics"""
        by_severity = {}
        for severity in AlertSeverity:
            count = len([a for a in self.alerts if a.severity == severity])
            by_severity[severity.value] = count
        
        return {
            "total_rules": len(self.rules),
            "active_rules": len([r for r in self.rules.values() if r.enabled]),
            "total_alerts": len(self.alerts),
            "unacknowledged": len([a for a in self.alerts if not a.acknowledged]),
            "by_severity": by_severity
        }


class WebhookNotifier:
    """Sends alerts via webhook"""
    
    def __init__(self, webhook_url: str):
        self.webhook_url = webhook_url
    
    def notify(self, alert: Alert):
        """Send alert via webhook"""
        import json
        # Would use requests in real implementation
        payload = {
            "text": f"[{alert.severity.value.upper()}] {alert.message}",
            "attachments": [{
                "title": alert.monitor_name,
                "text": f"File: {alert.file_path}:{alert.line}",
                "color": self._severity_color(alert.severity)
            }]
        }
        logger.info("Would send webhook", url=self.webhook_url, payload=payload)
    
    def _severity_color(self, severity: AlertSeverity) -> str:
        colors = {
            AlertSeverity.INFO: "#36a64f",
            AlertSeverity.WARNING: "#ffcc00",
            AlertSeverity.ERROR: "#ff6600",
            AlertSeverity.CRITICAL: "#ff0000"
        }
        return colors.get(severity, "#808080")
