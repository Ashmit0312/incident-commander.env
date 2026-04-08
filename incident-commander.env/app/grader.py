"""
Grading functions for the Incident Commander OpenEnv.

Scores agent actions against ground truth with partial credit:
  - Action type: did the agent do the right thing? (investigate vs restart vs rollback)
  - Target: did it target the right service/team?
  - Communication: for status updates, did it mention the right things?
  - Speed: bonus for acting quickly, penalty for delays

All scores are deterministic and reproducible.
"""

from __future__ import annotations

from typing import Any

from app.models import Action, ActionType, Reward


def _score_action_type(actual: str, ideal: str, acceptable: list[tuple[str, str | None]]) -> float:
    """Score whether the agent took the right type of action."""
    if actual == ideal:
        return 1.0

    # Check acceptable alternatives
    for acc_type, _ in acceptable:
        if actual == acc_type:
            return 0.6  # Acceptable but not ideal

    # Some actions are always somewhat reasonable
    partial_credit = {
        ("investigate", "restart_service"): 0.2,  # investigating when should restart is cautious
        ("investigate", "rollback_deploy"): 0.2,
        ("investigate", "mitigate"): 0.2,
        ("status_update", "page_team"): 0.3,  # communicating is close to paging
        ("page_team", "status_update"): 0.3,
        ("restart_service", "rollback_deploy"): 0.3,  # both are remediation
        ("rollback_deploy", "restart_service"): 0.3,
        ("mitigate", "rollback_deploy"): 0.4,
        ("rollback_deploy", "mitigate"): 0.4,
        ("mitigate", "restart_service"): 0.3,
        ("restart_service", "mitigate"): 0.3,
    }
    return partial_credit.get((actual, ideal), 0.0)


def _score_target(actual: str | None, ideal: str | None, acceptable: list[tuple[str, str | None]]) -> float:
    """Score whether the agent targeted the right service/team."""
    if ideal is None:
        return 1.0  # No specific target required

    if actual is None:
        return 0.3  # Didn't specify target but should have

    actual_lower = actual.lower().strip()
    ideal_lower = ideal.lower().strip()

    if actual_lower == ideal_lower:
        return 1.0

    # Check if target matches any acceptable action's target
    for _, acc_target in acceptable:
        if acc_target and actual_lower == acc_target.lower().strip():
            return 0.7

    # Partial credit for related targets
    related_targets = {
        ("backend", "devops"): 0.4,
        ("devops", "backend"): 0.4,
        ("security", "management"): 0.3,
        ("management", "security"): 0.3,
        ("on-call", "backend"): 0.4,
        ("on-call", "devops"): 0.4,
        ("on-call", "security"): 0.3,
        ("web-server", "api-gateway"): 0.2,
        ("api-gateway", "web-server"): 0.2,
        ("database", "backend"): 0.2,
    }
    return related_targets.get((actual_lower, ideal_lower), 0.1)


def _score_communication(message: str | None, criteria: list[str]) -> float:
    """Score status update quality based on keyword criteria."""
    if not criteria:
        return 1.0  # No communication needed for this phase

    if not message or len(message.strip()) < 10:
        return 0.0

    message_lower = message.lower()
    met = sum(1 for keyword in criteria if keyword.lower() in message_lower)

    # Need at least some criteria met
    return min(1.0, met / max(1, len(criteria) * 0.5))  # 50% of keywords = full score


def grade_action(action: Action, ground_truth: dict[str, Any], minutes_elapsed: int) -> Reward:
    """Grade a single incident response action against ground truth."""

    # Skip action
    if action.action_type == ActionType.SKIP:
        return Reward(
            total=-0.15,
            penalty=-0.15,
            details="Skipped during active incident — time is critical",
        )

    action_type_str = action.action_type.value
    ideal_action = ground_truth["ideal_action"]
    ideal_target = ground_truth.get("ideal_target")
    acceptable = ground_truth.get("acceptable_actions", [])
    comm_criteria = ground_truth.get("communication_criteria", [])

    # Score components
    action_score = _score_action_type(action_type_str, ideal_action, acceptable)
    target_score = _score_target(action.target, ideal_target, acceptable)
    comm_score = 1.0
    penalty = 0.0

    # Communication scoring for status updates
    if action_type_str == "status_update" and comm_criteria:
        comm_score = _score_communication(action.message, comm_criteria)
    elif ideal_action == "status_update" and action_type_str != "status_update":
        # Should have communicated but didn't
        comm_score = 0.0

    # Speed bonus (acting faster is better in incidents)
    speed_bonus = 0.0
    if action_score > 0.5:
        if minutes_elapsed <= 5:
            speed_bonus = 0.05
        elif minutes_elapsed <= 10:
            speed_bonus = 0.02

    # Penalty: dangerous actions
    # Restarting database without investigating first = bad (lose forensic evidence)
    if action_type_str == "restart_service" and ideal_action == "investigate":
        penalty = -0.2
    # Restarting database during potential breach = very bad
    if action_type_str == "restart_service" and "database" in (action.target or ""):
        if any("breach" in str(a) or "security" in str(a) for a in comm_criteria):
            penalty = -0.3

    # Weighted total
    diagnosis_score = action_score * 0.4
    action_total = target_score * 0.3
    comm_total = comm_score * 0.3

    total = diagnosis_score + action_total + comm_total + speed_bonus + penalty
    total = max(-1.0, min(1.0, total))

    details_parts = []
    if action_score >= 0.8:
        details_parts.append("Correct action")
    elif action_score >= 0.5:
        details_parts.append(f"Acceptable action ({action_score:.1f})")
    else:
        details_parts.append(f"Wrong action: {action_type_str} (wanted {ideal_action})")

    if ideal_target:
        if target_score >= 0.8:
            details_parts.append("correct target")
        else:
            details_parts.append(f"target: {action.target} (wanted {ideal_target})")

    if comm_criteria and action_type_str == "status_update":
        details_parts.append(f"comms: {comm_score:.0%}")

    if speed_bonus > 0:
        details_parts.append(f"speed bonus +{speed_bonus:.2f}")
    if penalty < 0:
        details_parts.append(f"penalty {penalty:.2f}")

    return Reward(
        total=round(total, 4),
        diagnosis_score=round(diagnosis_score, 4),
        action_score=round(action_total, 4),
        communication_score=round(comm_total, 4),
        speed_bonus=round(speed_bonus, 4),
        penalty=round(penalty, 4),
        details=" | ".join(details_parts),
    )


def grade_episode(action_history: list[dict], ground_truths: list[dict]) -> float:
    """
    Compute final episode score (0.0–1.0) from all actions taken.
    This is the task grader used for evaluation.
    """
    if not action_history:
        return 0.0

    total_score = 0.0
    n = min(len(action_history), len(ground_truths))

    for i in range(n):
        action_data = action_history[i]
        gt = ground_truths[i]

        action = Action(**action_data)
        minutes = action_data.get("minutes_elapsed", i * 5)
        reward = grade_action(action, gt, minutes)

        # Normalize from [-1, 1] to [0, 1]
        normalized = (reward.total + 1.0) / 2.0
        total_score += normalized

    # Unprocessed phases count as 0
    return round(total_score / len(ground_truths), 4)
