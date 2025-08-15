"""System metrics and resource monitoring."""
import psutil
import time
from typing import Dict, Any, List
from dataclasses import dataclass


@dataclass
class SystemMetrics:
    """System resource metrics snapshot."""
    cpu_percent: float
    memory_percent: float
    gpu_temp: float
    available_memory_gb: float
    timestamp: float


class MetricsCollector:
    """Collects and tracks system metrics."""
    
    def __init__(self, history_size: int = 50):
        self.history_size = history_size
        self.history: List[SystemMetrics] = []
        self.start_time = time.time()
        self._last_cpu_times = None
        
        # Initialize CPU measurement
        psutil.cpu_percent(interval=None)
    
    def collect(self) -> SystemMetrics:
        """Collect current system metrics."""
        # CPU percentage (non-blocking)
        cpu_percent = psutil.cpu_percent(interval=None)
        
        # Memory usage
        memory = psutil.virtual_memory()
        memory_percent = memory.percent
        available_gb = memory.available / (1024 ** 3)
        
        # GPU temperature (Apple Silicon M-series)
        gpu_temp = self._get_gpu_temperature()
        
        metrics = SystemMetrics(
            cpu_percent=cpu_percent,
            memory_percent=memory_percent,
            gpu_temp=gpu_temp,
            available_memory_gb=available_gb,
            timestamp=time.time()
        )
        
        # Add to history
        self.history.append(metrics)
        if len(self.history) > self.history_size:
            self.history = self.history[-self.history_size:]
        
        return metrics
    
    def _get_gpu_temperature(self) -> float:
        """Get GPU temperature for Apple Silicon."""
        try:
            # Try to read thermal state (macOS specific)
            import subprocess
            result = subprocess.run(
                ['system_profiler', 'SPPowerDataType'],
                capture_output=True,
                text=True,
                timeout=2
            )
            # This is a simplified approach - actual implementation
            # would parse the output for thermal data
            return 45.0  # Placeholder
        except:
            return 0.0
    
    def get_trend(self, metric_name: str, window: int = 10) -> List[float]:
        """Get trend for specific metric."""
        if len(self.history) < 2:
            return []
        
        recent = self.history[-window:]
        return [getattr(m, metric_name) for m in recent]
    
    def is_under_load(self) -> bool:
        """Check if system is under high load."""
        if not self.history:
            return False
        
        latest = self.history[-1]
        return (latest.cpu_percent > 80 or 
                latest.memory_percent > 85 or 
                latest.gpu_temp > 80)
    
    def should_enable_eco_mode(self) -> bool:
        """Recommend eco mode based on resource usage."""
        if len(self.history) < 3:
            return False
        
        recent_cpu = [m.cpu_percent for m in self.history[-3:]]
        recent_memory = [m.memory_percent for m in self.history[-3:]]
        
        avg_cpu = sum(recent_cpu) / len(recent_cpu)
        avg_memory = sum(recent_memory) / len(recent_memory)
        
        return avg_cpu > 70 or avg_memory > 80
    
    def get_performance_score(self) -> float:
        """Get overall performance score (0.0 to 1.0)."""
        if not self.history:
            return 1.0
        
        latest = self.history[-1]
        
        # Invert resource usage for score (lower usage = higher score)
        cpu_score = max(0, 1.0 - latest.cpu_percent / 100)
        memory_score = max(0, 1.0 - latest.memory_percent / 100)
        
        # Temperature factor (Apple Silicon throttles at high temps)
        temp_score = 1.0
        if latest.gpu_temp > 0:
            temp_score = max(0, 1.0 - max(0, latest.gpu_temp - 50) / 50)
        
        return (cpu_score + memory_score + temp_score) / 3


class SessionMetrics:
    """Tracks metrics for a specific agent session."""
    
    def __init__(self, session_id: str):
        self.session_id = session_id
        self.start_time = time.time()
        self.step_timings: List[float] = []
        self.tool_usage: Dict[str, int] = {}
        self.error_counts: Dict[str, int] = {}
        self.token_usage = 0
        self.llm_calls = 0
        self.confidence_history: List[float] = []
    
    def record_step_timing(self, duration: float):
        """Record timing for a step."""
        self.step_timings.append(duration)
    
    def record_tool_usage(self, tool_name: str):
        """Record tool usage."""
        self.tool_usage[tool_name] = self.tool_usage.get(tool_name, 0) + 1
    
    def record_error(self, error_class: str):
        """Record error occurrence."""
        self.error_counts[error_class] = self.error_counts.get(error_class, 0) + 1
    
    def record_llm_call(self, tokens_used: int = 0):
        """Record LLM call."""
        self.llm_calls += 1
        self.token_usage += tokens_used
    
    def record_confidence(self, confidence: float):
        """Record confidence score."""
        self.confidence_history.append(confidence)
    
    def get_average_step_time(self) -> float:
        """Get average step execution time."""
        if not self.step_timings:
            return 0.0
        return sum(self.step_timings) / len(self.step_timings)
    
    def get_session_duration(self) -> float:
        """Get total session duration."""
        return time.time() - self.start_time
    
    def get_confidence_trend(self) -> List[float]:
        """Get recent confidence trend."""
        return self.confidence_history[-10:] if self.confidence_history else []
    
    def to_dict(self) -> Dict[str, Any]:
        """Export metrics as dictionary."""
        return {
            'session_id': self.session_id,
            'duration': self.get_session_duration(),
            'steps_completed': len(self.step_timings),
            'average_step_time': self.get_average_step_time(),
            'tool_usage': self.tool_usage,
            'error_counts': self.error_counts,
            'llm_calls': self.llm_calls,
            'token_usage': self.token_usage,
            'confidence_trend': self.get_confidence_trend()
        }


class MetricsManager:
    """Manages metrics collection for all sessions."""
    
    def __init__(self):
        self.system_collector = MetricsCollector()
        self.session_metrics: Dict[str, SessionMetrics] = {}
    
    def get_session_metrics(self, session_id: str) -> SessionMetrics:
        """Get or create session metrics."""
        if session_id not in self.session_metrics:
            self.session_metrics[session_id] = SessionMetrics(session_id)
        return self.session_metrics[session_id]
    
    def collect_all_metrics(self, session_id: str) -> Dict[str, Any]:
        """Collect both system and session metrics."""
        system_metrics = self.system_collector.collect()
        session_metrics = self.get_session_metrics(session_id)
        
        return {
            'system': {
                'cpu_percent': system_metrics.cpu_percent,
                'memory_percent': system_metrics.memory_percent,
                'gpu_temp': system_metrics.gpu_temp,
                'available_memory_gb': system_metrics.available_memory_gb,
                'performance_score': self.system_collector.get_performance_score(),
                'under_load': self.system_collector.is_under_load(),
                'eco_mode_recommended': self.system_collector.should_enable_eco_mode()
            },
            'session': session_metrics.to_dict()
        }
    
    def cleanup_session(self, session_id: str):
        """Clean up session metrics."""
        if session_id in self.session_metrics:
            del self.session_metrics[session_id]


# Global metrics manager
metrics_manager = MetricsManager()