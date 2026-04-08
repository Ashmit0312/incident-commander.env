"""
IncidentCommanderEnv — OpenEnv-compliant incident response environment.

Implements the full OpenEnv interface:
  - reset(task_id) → Observation
  - step(action)   → (Observation, Reward, done, info)
  - state()        → EnvironmentState
  - close()        → cleanup (required by OpenEnv SDK)
"""

from __future__ import annotations

from typing import Any

from app.grader import grade_action, grade_episode
from app.incidents import generate_easy, generate_hard, generate_medium
from app.models import Action, EnvironmentState, Observation, Reward

TASK_GENERATORS = {
    "easy": generate_easy,
    "medium": generate_medium,
    "hard": generate_hard,
}

TASK_DESCRIPTIONS = {
    "easy": "Single service crash with clear root cause — investigate, fix, communicate.",
    "medium": "Cascading failure across multiple services — trace the chain, fix root cause, coordinate teams.",
    "hard": "Database corruption + data breach — fix technical issues AND handle security/compliance.",
}


class IncidentCommanderEnv:
    """OpenEnv-compliant incident response environment."""

    def __init__(self):
        self._state: EnvironmentState | None = None

    def reset(self, task_id: str = "easy") -> Observation:
        """Reset environment to a fresh episode for the given task."""
        if task_id not in TASK_GENERATORS:
            raise ValueError(
                f"Unknown task_id: {task_id}. Must be one of: {list(TASK_GENERATORS.keys())}"
            )

        phases, ground_truth = TASK_GENERATORS[task_id]()

        self._state = EnvironmentState(
            task_id=task_id,
            incidents=phases,
            ground_truth=ground_truth,
            current_phase=0,
            total_reward=0.0,
            step_count=0,
            done=False,
            action_history=[],
            resolved=False,
        )

        return self._make_observation()

    def step(self, action: Action) -> tuple[Observation, Reward, bool, dict[str, Any]]:
        """Process an agent action and advance to the next phase."""
        if self._state is None:
            raise RuntimeError("Environment not initialized. Call reset() first.")
        if self._state.done:
            raise RuntimeError("Episode is done. Call reset() to start a new one.")

        s = self._state
        gt = s.ground_truth[s.current_phase]
        minutes = s.incidents[s.current_phase].get("minutes_elapsed", s.step_count * 5)

        # Grade the action
        reward = grade_action(action, gt, minutes)

        # Record action with metadata
        action_record = action.model_dump()
        action_record["minutes_elapsed"] = minutes
        s.action_history.append(action_record)

        s.total_reward += reward.total
        s.step_count += 1
        s.current_phase += 1

        # Check if done
        if s.current_phase >= len(s.incidents):
            s.done = True
            s.resolved = True

        # Build info
        info = {
            "phase": s.current_phase,
            "step": s.step_count,
            "cumulative_reward": round(s.total_reward, 4),
            "phase_description": gt.get("phase_description", ""),
        }

        if s.done:
            info["episode_score"] = grade_episode(s.action_history, s.ground_truth)

        return self._make_observation(), reward, s.done, info

    def state(self) -> EnvironmentState:
        """Return the full internal state."""
        if self._state is None:
            raise RuntimeError("Environment not initialized. Call reset() first.")
        return self._state.model_copy(deep=True)

    def get_task_ids(self) -> list[str]:
        """List available task IDs."""
        return list(TASK_GENERATORS.keys())

    def grade(self, task_id: str | None = None) -> float:
        """Run the task grader on the current episode. Returns 0.0–1.0."""
        if self._state is None:
            raise RuntimeError("Environment not initialized.")
        return grade_episode(self._state.action_history, self._state.ground_truth)

    def close(self) -> None:
        """Cleanup. Required by OpenEnv SDK pattern."""
        self._state = None

    def _make_observation(self) -> Observation:
        """Build an Observation from current state."""
        s = self._state

        if s.done or s.current_phase >= len(s.incidents):
            # Return final observation with empty alerts
            last = s.incidents[-1]
            return Observation(
                alerts=[],
                metrics=last["metrics"],
                context=last["context"],
                log_snippets=[],
                actions_taken=last.get("actions_taken", []),
                minutes_elapsed=last.get("minutes_elapsed", 0),
                task_description="Incident resolved. Episode complete.",
            )

        phase_data = s.incidents[s.current_phase]
        return Observation(**phase_data)
