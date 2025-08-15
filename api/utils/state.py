"""State management for agent sessions with loop safety."""
import json
import hashlib
import time
from typing import Dict, List, Any, Optional, Set
from dataclasses import dataclass, asdict
from pathlib import Path


@dataclass
class LedgerEntry:
    """Single step in the execution ledger."""
    step: int
    action: str
    args: Dict[str, Any]
    args_key: str
    expected: str
    status: str  # ok, error, mismatch, no_progress, duplicate_blocked
    obs_signature: str
    error_class: Optional[str] = None
    notes: str = ""
    timestamp: float = None
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = time.time()


class SessionState:
    """Manages state for a single agent session."""
    
    def __init__(self, session_id: str, max_facts: int = 50, max_obs: int = 8):
        self.session_id = session_id
        self.max_facts = max_facts
        self.max_obs = max_obs
        
        # Core state
        self.blackboard: Dict[str, List[str]] = {'facts': []}
        self.last_obs: List[str] = []
        self.step_ledger: List[LedgerEntry] = []
        self.attempt_set: Set[str] = set()  # Failed (action, args_key) pairs
        self.result_cache: Dict[str, str] = {}  # Successful args_key -> obs_signature
        
        # Metrics
        self.confidence_trend: List[float] = []
        self.no_progress_count: int = 0
        self.strategy_switches: int = 0
        self.start_time: float = time.time()
        
        # Budget tracking
        self.retry_budgets: Dict[str, int] = {}  # action -> remaining retries
        self.total_steps: int = 0
    
    def canonicalize_args(self, action: str, args: Dict[str, Any]) -> str:
        """Create canonical hash key for args to detect duplicates."""
        # Expand paths and normalize
        canonical_args = {}
        
        for key, value in args.items():
            if key in ['dir', 'path', 'file'] and isinstance(value, str):
                # Expand and resolve paths
                try:
                    canonical_args[key] = str(Path(value).expanduser().resolve())
                except (OSError, ValueError):
                    canonical_args[key] = str(value)
            else:
                canonical_args[key] = value
        
        # Sort keys for consistent hashing
        sorted_json = json.dumps(canonical_args, sort_keys=True, ensure_ascii=True)
        args_key = hashlib.sha1(sorted_json.encode()).hexdigest()[:8]
        
        return f"{action}_{args_key}"
    
    def is_duplicate_attempt(self, action: str, args: Dict[str, Any]) -> bool:
        """Check if this (action, args) combo has already failed."""
        args_key = self.canonicalize_args(action, args)
        return args_key in self.attempt_set
    
    def mark_attempt(self, action: str, args: Dict[str, Any], success: bool):
        """Mark an attempt as tried."""
        args_key = self.canonicalize_args(action, args)
        if not success:
            self.attempt_set.add(args_key)
        else:
            # Successful attempts can be cached
            self.attempt_set.discard(args_key)
    
    def add_ledger_entry(self, entry: LedgerEntry):
        """Add entry to step ledger."""
        self.step_ledger.append(entry)
        self.total_steps += 1
        
        # Update no-progress counter
        if entry.status == 'no_progress':
            self.no_progress_count += 1
        elif entry.status == 'ok':
            self.no_progress_count = 0
    
    def add_observation(self, obs: str):
        """Add observation to recent history."""
        self.last_obs.append(obs)
        if len(self.last_obs) > self.max_obs:
            self.last_obs = self.last_obs[-self.max_obs:]
    
    def add_fact(self, fact: str):
        """Add fact to blackboard."""
        if fact and fact not in self.blackboard['facts']:
            self.blackboard['facts'].append(fact)
            if len(self.blackboard['facts']) > self.max_facts:
                self.blackboard['facts'] = self.blackboard['facts'][-self.max_facts:]
    
    def update_confidence(self, confidence: float):
        """Update confidence trend."""
        self.confidence_trend.append(confidence)
        if len(self.confidence_trend) > 10:
            self.confidence_trend = self.confidence_trend[-10:]
    
    def get_retry_budget(self, action: str) -> int:
        """Get remaining retry budget for action."""
        if action not in self.retry_budgets:
            self.retry_budgets[action] = 1  # Per spec: per-action retry budget = 1
        return self.retry_budgets[action]
    
    def decrement_retry_budget(self, action: str):
        """Decrement retry budget for action."""
        if action in self.retry_budgets:
            self.retry_budgets[action] = max(0, self.retry_budgets[action] - 1)
    
    def should_switch_strategy(self) -> bool:
        """Check if strategy switch is needed due to no progress."""
        return self.no_progress_count >= 3
    
    def reset_no_progress(self):
        """Reset no-progress counter after strategy switch."""
        self.no_progress_count = 0
        self.strategy_switches += 1
    
    def get_context_summary(self, max_chars: int = 4000) -> str:
        """Get compressed context for LLM consumption."""
        context_parts = []
        
        # Recent observations (most important)
        if self.last_obs:
            obs_text = "Recent observations:\n" + "\n".join(f"- {obs}" for obs in self.last_obs[-3:])
            context_parts.append(obs_text)
        
        # Key facts from blackboard
        if self.blackboard.get('facts'):
            facts_text = "Key facts:\n" + "\n".join(f"- {fact}" for fact in self.blackboard['facts'][-5:])
            context_parts.append(facts_text)
        
        # Recent failed attempts
        failed_attempts = [entry for entry in self.step_ledger[-5:] if entry.status in ['error', 'duplicate_blocked']]
        if failed_attempts:
            failures_text = "Recent failures:\n" + "\n".join(
                f"- {entry.action}({entry.args_key}): {entry.error_class or entry.status}"
                for entry in failed_attempts
            )
            context_parts.append(failures_text)
        
        # Join and clip
        full_context = "\n\n".join(context_parts)
        if len(full_context) > max_chars:
            return full_context[:max_chars] + "... [context clipped]"
        
        return full_context
    
    def to_dict(self) -> Dict[str, Any]:
        """Export state as dictionary."""
        return {
            'session_id': self.session_id,
            'blackboard': self.blackboard,
            'last_obs': self.last_obs,
            'step_ledger': [asdict(entry) for entry in self.step_ledger],
            'confidence_trend': self.confidence_trend,
            'no_progress_count': self.no_progress_count,
            'strategy_switches': self.strategy_switches,
            'total_steps': self.total_steps,
            'retry_budgets': self.retry_budgets,
            'start_time': self.start_time,
            'duration': time.time() - self.start_time
        }


def create_observation_signature(observation: Any) -> str:
    """Create signature for observation to detect mismatches."""
    if observation is None:
        return "null"
    
    obs_type = type(observation).__name__
    
    if isinstance(observation, list):
        return f"list[len={len(observation)},keys={get_list_keys(observation)}]"
    elif isinstance(observation, dict):
        keys = sorted(observation.keys()) if observation else []
        return f"dict[keys={','.join(keys[:5])}]"
    elif isinstance(observation, str):
        if "error" in observation.lower() or "failed" in observation.lower():
            return f"str[len={len(observation)},error=true]"
        return f"str[len={len(observation)}]"
    elif isinstance(observation, (int, float)):
        return f"{obs_type}[value={observation}]"
    else:
        return f"{obs_type}[{str(observation)[:50]}]"


def get_list_keys(lst: List[Any]) -> str:
    """Get common keys from list of dictionaries."""
    if not lst or not isinstance(lst[0], dict):
        return "mixed"
    
    if len(lst) == 0:
        return "empty"
    
    # Get keys from first item
    first_keys = set(lst[0].keys()) if isinstance(lst[0], dict) else set()
    
    # Find common keys across all items
    common_keys = first_keys
    for item in lst[1:5]:  # Check first 5 items
        if isinstance(item, dict):
            common_keys &= set(item.keys())
        else:
            common_keys = set()
            break
    
    return '|'.join(sorted(common_keys)) if common_keys else 'mixed'


def hash_args_key(action: str, args: Dict[str, Any]) -> str:
    """Generate consistent hash key for action+args combo."""
    sorted_json = json.dumps({'action': action, 'args': args}, sort_keys=True)
    return hashlib.sha1(sorted_json.encode()).hexdigest()[:12]


class StateManager:
    """Manages multiple agent sessions."""
    
    def __init__(self):
        self.sessions: Dict[str, SessionState] = {}
    
    def get_session(self, session_id: str) -> SessionState:
        """Get or create session state."""
        if session_id not in self.sessions:
            self.sessions[session_id] = SessionState(session_id)
        return self.sessions[session_id]
    
    def cleanup_session(self, session_id: str):
        """Clean up session resources."""
        if session_id in self.sessions:
            del self.sessions[session_id]
    
    def export_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Export session data."""
        if session_id in self.sessions:
            return self.sessions[session_id].to_dict()
        return None


# Global state manager instance
state_manager = StateManager()