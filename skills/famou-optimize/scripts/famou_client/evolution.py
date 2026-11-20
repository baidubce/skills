"""Evolution facts observed in tool receipts, independent of conversational turn state."""
import json


ACTIVE = {"created", "initializing", "running"}


class Evolution:
    """Track deep-evolution experiment lifecycles solely from verified tool receipts."""

    def __init__(self):
        """Initialize an empty per-session evolution tracker."""
        self.experiments = {}
        self.latest_id = None
        self.updated_this_turn = False

    def begin_turn(self):
        """Reset the per-turn observation flag when a new conversational turn starts."""
        self.updated_this_turn = False

    def observe(self, tool, text, observed_at=None):
        """Parse one successful evolution tool result into the normalized state table."""
        # Natural-language claims and IDs in prompts are not evidence of a launch.
        if tool not in ("evolve_create", "evolve_status", "evolve_continue", "evolve_cancel"):
            return
        try:
            result = json.loads(text)
        except (ValueError, TypeError):
            return
        if not isinstance(result, dict) or result.get("ok") is not True:
            return
        data = result.get("data")
        data = data if isinstance(data, dict) else {}
        experiment_id = result.get("experiment_id") or data.get("experiment_id")
        if not isinstance(experiment_id, str) or not experiment_id:
            return
        stage = result.get("evolve_stage")
        if not isinstance(stage, dict):
            stages = data.get("progress")
            stage = (
                next((item for item in stages if isinstance(item, dict) and item.get("stage") == "EVOLVE"), {})
                if isinstance(stages, list)
                else {}
            )
        overall = str(result.get("experiment_status") or data.get("status") or "").upper()
        stage_status = str(stage.get("status") or "").upper()
        initialization = result.get("initialization")
        if tool == "evolve_cancel" and result.get("executed") is True and result.get("state") == "changed":
            state = "cancelled"
        elif overall in ("COMPLETED", "SUCCESS", "SUCCEEDED"):
            state = "completed"
        elif overall in ("CANCELLED", "CANCELED", "STOPPED"):
            state = "cancelled"
        elif overall in ("FAILED", "INVALID") or initialization == "failed" or stage_status in ("FAILED", "INVALID"):
            state = "failed"
        elif stage_status in ("RUNNING", "COMPLETED") or initialization == "passed":
            # A COMPLETED EVOLVE stage alone is not the whole experiment's terminal state.
            state = "running"
        elif stage_status in ("INITIALING", "INITIALIZING", "CREATED") or initialization == "pending":
            state = "initializing"
        elif tool in ("evolve_create", "evolve_continue"):
            state = "created"
        else:
            # RUNNING at the top level alone also occurs during initialization.
            state = "unknown"
        item = {"experiment_id": experiment_id, "state": state,
                "experiment_status": overall or None, "stage_status": stage_status or None,
                "initialization": initialization, "observed_at": observed_at,
                "source": "tool_result"}
        progress = stage.get("progress")
        if type(progress) in (int, float):
            item["progress"] = progress
        self.experiments[experiment_id] = item
        self.latest_id = experiment_id
        self.updated_this_turn = True

    def snapshot(self):
        """Return the latest tracked experiment snapshot and active experiment IDs."""
        item = self.experiments.get(self.latest_id)
        if not item:
            return None
        return {**item, "observed_in_current_turn": self.updated_this_turn,
                "active_experiment_ids": [key for key, value in self.experiments.items()
                                          if value["state"] in ACTIVE]}
