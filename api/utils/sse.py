"""Server-Sent Events utilities for streaming agent responses."""
import json
import asyncio
import time
from typing import Dict, Any, AsyncGenerator, Optional
from enum import Enum


class SSEEvent(Enum):
    """SSE event types in order."""
    STATUS = "status"
    PLAN = "plan"
    CRITIC = "critic"
    EXEC = "exec"
    OBS = "obs"
    HYP = "hyp"
    BB = "bb"
    MET = "met"
    FINAL = "final"
    ERROR = "error"
    CANCEL = "cancel"
    # Add new event types
    THINKING = "thinking"
    REASONING = "reasoning"


class SSEManager:
    """Manages Server-Sent Events streaming with proper ordering."""
    
    def __init__(self, session_id: str):
        self.session_id = session_id
        self.step = 0
        self.cancelled = False
        self._event_queue = asyncio.Queue()
    
    def cancel(self):
        """Cancel the stream."""
        self.cancelled = True
        asyncio.create_task(self._event_queue.put({
            'event': SSEEvent.CANCEL.value,
            'data': {'cancelled': True, 'step': self.step}
        }))
    
    async def emit(self, event_type, data: Dict[str, Any], step: Optional[int] = None):
        """Emit an SSE event with proper formatting."""
        if self.cancelled and (isinstance(event_type, SSEEvent) and event_type != SSEEvent.CANCEL):
            return
        
        if step is not None:
            self.step = step
        
        # Handle both string and enum event types
        if isinstance(event_type, SSEEvent):
            event_name = event_type.value
        else:
            event_name = str(event_type)
        
        event_data = {
            'event': event_name,
            'data': {
                'session_id': self.session_id,
                'step': self.step,
                'timestamp': time.time(),
                **data
            }
        }
        
        await self._event_queue.put(event_data)
    
    async def stream(self) -> AsyncGenerator[str, None]:
        """Stream SSE events as formatted strings."""
        while True:
            try:
                # Wait for next event with timeout
                event_data = await asyncio.wait_for(
                    self._event_queue.get(), 
                    timeout=30.0
                )
                
                # Format as SSE
                sse_line = format_sse_event(
                    event_data['event'], 
                    event_data['data']
                )
                
                yield sse_line
                
                # End stream on final or cancel events
                if event_data['event'] in [SSEEvent.FINAL.value, SSEEvent.CANCEL.value, SSEEvent.ERROR.value]:
                    break
                    
            except asyncio.TimeoutError:
                # Send keepalive
                yield format_sse_event('keepalive', {'timestamp': time.time()})
            except Exception as e:
                # Send error and end stream
                yield format_sse_event(SSEEvent.ERROR.value, {'error': str(e)})
                break


def format_sse_event(event_type: str, data: Dict[str, Any]) -> str:
    """Format data as Server-Sent Event string."""
    json_data = json.dumps(data, ensure_ascii=False)
    return f"event: {event_type}\ndata: {json_data}\n\n"


async def emit_status(sse: SSEManager, status: str, details: Optional[Dict] = None):
    """Emit status event."""
    await sse.emit(SSEEvent.STATUS, {
        'status': status,
        **(details or {})
    })


async def emit_plan(sse: SSEManager, plan: Dict[str, Any]):
    """Emit plan event."""
    await sse.emit(SSEEvent.PLAN, {
        'subgoals': plan.get('subgoals', []),
        'success_criteria': plan.get('success_criteria', ''),
        'next_action': plan.get('next_action', ''),
        'args': plan.get('args', {}),
        'expected_observation': plan.get('expected_observation', ''),
        'rationale': plan.get('rationale', '')
    })


async def emit_critic(sse: SSEManager, critic_result: Dict[str, Any]):
    """Emit critic event."""
    await sse.emit(SSEEvent.CRITIC, {
        'approved': critic_result.get('approved', False),
        'changes': critic_result.get('changes', []),
        'reasoning': critic_result.get('reasoning', '')
    })


async def emit_exec(sse: SSEManager, tool_name: str, args: Dict[str, Any], batch_idx: Optional[int] = None):
    """Emit execution event."""
    event_data = {
        'tool': tool_name,
        'args': args,
        'started_at': time.time()
    }
    
    if batch_idx is not None:
        event_data['batch_idx'] = batch_idx
    
    await sse.emit(SSEEvent.EXEC, event_data)


async def emit_obs(sse: SSEManager, observation: Any, signature: str, error_class: Optional[str] = None):
    """Emit observation event."""
    # Clip large observations
    obs_str = str(observation)
    if len(obs_str) > 4000:
        obs_str = obs_str[:4000] + "... [clipped]"
    
    await sse.emit(SSEEvent.OBS, {
        'observation': obs_str,
        'signature': signature,
        'error_class': error_class,
        'clipped': len(str(observation)) > 4000
    })


async def emit_obs_batch(sse: SSEManager, observations: list, signatures: list, error_classes: list):
    """Emit batch observation event."""
    batch_data = []
    for i, (obs, sig, err_cls) in enumerate(zip(observations, signatures, error_classes)):
        obs_str = str(obs)
        if len(obs_str) > 1000:  # Smaller clip for batch
            obs_str = obs_str[:1000] + "... [clipped]"
        
        batch_data.append({
            'idx': i,
            'observation': obs_str,
            'signature': sig,
            'error_class': err_cls,
            'clipped': len(str(obs)) > 1000
        })
    
    await sse.emit(SSEEvent.OBS, {
        'batch': True,
        'observations': batch_data
    })


async def emit_hyp(sse: SSEManager, hypothesis: Dict[str, Any]):
    """Emit hypothesis event."""
    await sse.emit(SSEEvent.HYP, {
        'expected_match': hypothesis.get('expected_match', False),
        'actual_signature': hypothesis.get('actual_signature', ''),
        'expected_signature': hypothesis.get('expected_signature', ''),
        'notes': hypothesis.get('notes', '')
    })


async def emit_blackboard(sse: SSEManager, blackboard: Dict[str, Any]):
    """Emit blackboard state event."""
    await sse.emit(SSEEvent.BB, {
        'facts_count': len(blackboard.get('facts', [])),
        'recent_facts': blackboard.get('facts', [])[-5:],  # Last 5 facts
        'last_obs_count': len(blackboard.get('last_obs', [])),
        'step_count': len(blackboard.get('step_ledger', []))
    })


async def emit_metrics(sse: SSEManager, metrics: Dict[str, Any]):
    """Emit metrics event."""
    await sse.emit(SSEEvent.MET, {
        'cpu_percent': metrics.get('cpu_percent', 0),
        'memory_percent': metrics.get('memory_percent', 0),
        'confidence_trend': metrics.get('confidence_trend', []),
        'no_progress_count': metrics.get('no_progress_count', 0),
        'latency_ms': metrics.get('latency_ms', 0),
        'tokens_used': metrics.get('tokens_used', 0)
    })


async def emit_final(sse: SSEManager, result: str, success: bool, confidence: float, next_steps: Optional[list] = None):
    """Emit final result event."""
    await sse.emit(SSEEvent.FINAL, {
        'result': result,
        'success': success,
        'confidence': confidence,
        'next_steps': next_steps or [],
        'completed_at': time.time()
    })


# Enhanced SSE functions for thinking
async def emit_thinking(sse_manager: SSEManager, thought: str, step_type: str = "general"):
    """Emit a thinking step with human-readable content."""
    data = {
        "thought": thought,
        "step_type": step_type,
        "timestamp": time.time()
    }
    await sse_manager.emit(SSEEvent.THINKING, data)


async def emit_reasoning(sse_manager: SSEManager, step: str, reasoning: str, details: Dict = None):
    """Emit human-readable reasoning step."""
    data = {
        "step": step,
        "reasoning": reasoning,
        "timestamp": time.time()
    }
    if details:
        data["details"] = details
    
    await sse_manager.emit(SSEEvent.REASONING, data)