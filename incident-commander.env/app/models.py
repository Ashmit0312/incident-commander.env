"""
Typed Pydantic models for the Incident Commander OpenEnv.

These models form the strict contract between agent and environment:
  - Observation: what the agent sees (alerts, system status, timeline)
  - Action: what the agent does (restart, rollback, page, communicate, investigate)
  - Reward: per-step score with breakdown
  - EnvironmentState: full internal state for debugging/inspection
"""

from __future__ import annotations
from typing import List, Dict, Any
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


# ── Enums ──────────────────────────────────────────────────────────────────────

class ActionType(str, Enum):
    """What kind of action the agent takes."""
    INVESTIGATE = "investigate"        # Check logs, metrics, traces
    RESTART_SERVICE = "restart_service" # Restart a specific service
    ROLLBACK_DEPLOY = "rollback_deploy" # Undo a recent deployment
    SCALE_UP = "scale_up"              # Add more instances of a service
    PAGE_TEAM = "page_team"            # Call in a specific team
    STATUS_UPDATE = "status_update"    # Communicate to stakeholders
    MITIGATE = "mitigate"              # Apply a specific fix/workaround
    SKIP = "skip"                      # Do nothing this step


class Severity(str, Enum):
    """Incident severity level."""
    SEV1 = "sev1"  # Critical: full outage, data loss, security breach
    SEV2 = "sev2"  # Major: partial outage, degraded service
    SEV3 = "sev3"  # Minor: limited impact, workaround available
    SEV4 = "sev4"  # Low: cosmetic, non-urgent


class ServiceName(str, Enum):
    """Services in the infrastructure."""
    WEB_SERVER = "web-server"
    API_GATEWAY = "api-gateway"
    AUTH_SERVICE = "auth-service"
    DATABASE = "database"
    CACHE = "cache"
    QUEUE = "message-queue"
    PAYMENT = "payment-service"
    SEARCH = "search-service"
    CDN = "cdn"
    LOAD_BALANCER = "load-balancer"


class TeamName(str, Enum):
    """Teams that can be paged."""
    BACKEND = "backend"
    FRONTEND = "frontend"
    DATABASE = "database-team"
    SECURITY = "security"
    DEVOPS = "devops"
    MANAGEMENT = "management"
    ON_CALL = "on-call"


# ── Observation ────────────────────────────────────────────────────────────────

class Alert(BaseModel):
    """A single monitoring alert."""
    source: str = Field(description="Monitoring system that triggered the alert")
    service: str = Field(description="Affected service name")
    message: str = Field(description="Alert description")
    severity: Severity = Field(description="Alert severity")
    timestamp: str = Field(description="When the alert fired (ISO 8601)")


class SystemMetrics(BaseModel):
    """Current system health metrics."""
    error_rate_pct: float = Field(description="Percentage of requests returning errors")
    latency_p99_ms: float = Field(description="99th percentile latency in ms")
    cpu_usage_pct: float = Field(description="Average CPU usage across fleet")
    memory_usage_pct: float = Field(description="Average memory usage across fleet")
    active_connections: int = Field(description="Number of active connections")
    requests_per_second: float = Field(description="Current request throughput")


class IncidentContext(BaseModel):
    """Background information about the incident."""
    incident_id: str = Field(description="Unique incident identifier")
    started_at: str = Field(description="When the incident began")
    affected_users: int = Field(description="Estimated number of affected users")
    revenue_impact_per_minute: float = Field(description="Estimated revenue loss per minute ($)")
    recent_deploys: list[str] = Field(default_factory=list, description="Recent deployments in last 24h")
    on_call_engineer: str = Field(description="Name of the on-call engineer")


class Observation(BaseModel):
    """What the agent sees at each step."""
    alerts: list[Alert] = Field(description="Current active alerts")
    metrics: SystemMetrics = Field(description="Current system metrics")
    context: IncidentContext = Field(description="Incident background info")
    log_snippets: list[str] = Field(default_factory=list, description="Recent log lines (if investigated)")
    actions_taken: list[str] = Field(default_factory=list, description="Summary of actions taken so far")
    minutes_elapsed: int = Field(description="Minutes since incident started")
    task_description: str = Field(description="What the agent should accomplish")


# ── Action ─────────────────────────────────────────────────────────────────────

class Action(BaseModel):
    """Agent's incident response decision."""
    action_type: ActionType = Field(description="Type of action to take")
    target: Optional[str] = Field(None, description="Target service or team name")
    message: Optional[str] = Field(None, description="Status update text or investigation query")
    reasoning: Optional[str] = Field(None, description="Why the agent chose this action")


# ── Reward ─────────────────────────────────────────────────────────────────────

class Reward(BaseModel):
    """Reward signal returned after each action."""
    total: float = Field(description="Total reward for this step")
    diagnosis_score: float = Field(default=0.0, description="Did the agent identify the right problem?")
    action_score: float = Field(default=0.0, description="Was the action appropriate?")
    communication_score: float = Field(default=0.0, description="Was the status update good?")
    speed_bonus: float = Field(default=0.0, description="Bonus for acting quickly")
    penalty: float = Field(default=0.0, description="Penalty for bad actions")
    details: str = Field(default="", description="Human-readable explanation")


# ── State ──────────────────────────────────────────────────────────────────────

class EnvironmentState(BaseModel):
    """Full internal state of the environment."""
    task_id: str
    incidents: list[dict]
    ground_truth: List[Dict[str, Any]]
    current_phase: int
    total_reward: float
    step_count: int
    done: bool
    action_history: list[dict]
    resolved: bool
