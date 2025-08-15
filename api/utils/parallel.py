"""Parallel execution utilities for batch tool operations."""
import asyncio
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict, Any, Callable, Optional, Tuple
import logging
from dataclasses import dataclass


logger = logging.getLogger(__name__)


@dataclass
class BatchTask:
    """Represents a single task in a batch."""
    idx: int
    tool_name: str
    args: Dict[str, Any]
    args_key: str


@dataclass
class BatchResult:
    """Result of a batch task execution."""
    idx: int
    success: bool
    result: Any = None
    error: Optional[str] = None
    error_class: Optional[str] = None
    signature: str = ""
    duration: float = 0.0


class ParallelExecutor:
    """Executes tool operations in parallel with safety guards."""
    
    def __init__(self, max_workers: int = 4, timeout: float = 60.0):
        self.max_workers = max_workers
        self.timeout = timeout
        self.executor = ThreadPoolExecutor(max_workers=max_workers)
    
    def __del__(self):
        """Clean up thread pool."""
        try:
            self.executor.shutdown(wait=False)
        except:
            pass
    
    async def execute_batch(
        self,
        tasks: List[BatchTask],
        tool_registry: Dict[str, Callable],
        state_session
    ) -> List[BatchResult]:
        """
        Execute a batch of tasks in parallel.
        
        Args:
            tasks: List of batch tasks to execute
            tool_registry: Registry of available tool functions
            state_session: Session state for duplicate checking
            
        Returns:
            List of batch results in order of task indices
        """
        if not tasks:
            return []
        
        logger.info(f"Executing batch of {len(tasks)} tasks")
        
        # Pre-validate tasks
        validated_tasks = []
        results = [None] * len(tasks)  # Pre-allocate results list
        
        for task in tasks:
            # Check for duplicates
            if state_session.is_duplicate_attempt(task.tool_name, task.args):
                logger.warning(f"Task {task.idx} blocked: duplicate attempt")
                results[task.idx] = BatchResult(
                    idx=task.idx,
                    success=False,
                    error="Duplicate attempt blocked",
                    error_class="duplicate_blocked"
                )
            elif task.tool_name not in tool_registry:
                logger.error(f"Task {task.idx} blocked: unknown tool {task.tool_name}")
                results[task.idx] = BatchResult(
                    idx=task.idx,
                    success=False,
                    error=f"Unknown tool: {task.tool_name}",
                    error_class="unknown_tool"
                )
            else:
                validated_tasks.append(task)
        
        if not validated_tasks:
            logger.warning("No valid tasks to execute in batch")
            return [r for r in results if r is not None]
        
        # Execute validated tasks in parallel
        loop = asyncio.get_event_loop()
        
        # Create futures for each task
        futures = []
        for task in validated_tasks:
            future = loop.run_in_executor(
                self.executor,
                self._execute_single_task,
                task,
                tool_registry[task.tool_name],
                state_session
            )
            futures.append((task.idx, future))
        
        # Wait for completion with timeout
        try:
            completed_results = await asyncio.wait_for(
                asyncio.gather(*[future for _, future in futures], return_exceptions=True),
                timeout=self.timeout
            )
            
            # Map results back to original indices
            for (idx, _), result in zip(futures, completed_results):
                if isinstance(result, Exception):
                    logger.error(f"Task {idx} failed with exception: {result}")
                    results[idx] = BatchResult(
                        idx=idx,
                        success=False,
                        error=str(result),
                        error_class="execution_error"
                    )
                else:
                    results[idx] = result
        
        except asyncio.TimeoutError:
            logger.error(f"Batch execution timed out after {self.timeout}s")
            
            # Mark incomplete tasks as timed out
            for task in validated_tasks:
                if results[task.idx] is None:
                    results[task.idx] = BatchResult(
                        idx=task.idx,
                        success=False,
                        error="Batch execution timeout",
                        error_class="timeout"
                    )
        
        # Filter out None results and sort by index
        final_results = [r for r in results if r is not None]
        final_results.sort(key=lambda r: r.idx)
        
        logger.info(f"Batch completed: {sum(1 for r in final_results if r.success)}/{len(final_results)} successful")
        
        return final_results
    
    def _execute_single_task(
        self,
        task: BatchTask,
        tool_func: Callable,
        state_session
    ) -> BatchResult:
        """Execute a single task synchronously."""
        import time
        
        start_time = time.time()
        
        try:
            # Import here to avoid circular imports
            from .state import create_observation_signature
            
            logger.debug(f"Executing task {task.idx}: {task.tool_name}({task.args})")
            
            # Execute the tool
            result = tool_func(**task.args)
            duration = time.time() - start_time
            
            # Create signature
            signature = create_observation_signature(result)
            
            # Mark as successful attempt
            state_session.mark_attempt(task.tool_name, task.args, success=True)
            
            logger.debug(f"Task {task.idx} completed successfully in {duration:.2f}s")
            
            return BatchResult(
                idx=task.idx,
                success=True,
                result=result,
                signature=signature,
                duration=duration
            )
        
        except Exception as e:
            duration = time.time() - start_time
            error_class = self._classify_error(e)
            
            logger.warning(f"Task {task.idx} failed: {str(e)}")
            
            # Mark as failed attempt
            state_session.mark_attempt(task.tool_name, task.args, success=False)
            
            return BatchResult(
                idx=task.idx,
                success=False,
                error=str(e),
                error_class=error_class,
                duration=duration
            )
    
    def _classify_error(self, error: Exception) -> str:
        """Classify error type for metrics."""
        error_type = type(error).__name__
        error_msg = str(error).lower()
        
        if "permission" in error_msg or "access" in error_msg:
            return "access_denied"
        elif "timeout" in error_msg:
            return "timeout"
        elif "connection" in error_msg or "network" in error_msg:
            return "network_error"
        elif "file not found" in error_msg or "no such file" in error_msg:
            return "file_not_found"
        elif "json" in error_msg or "parse" in error_msg:
            return "parse_error"
        elif error_type in ["ValueError", "TypeError"]:
            return "validation_error"
        else:
            return "execution_error"


class BatchCoordinator:
    """Coordinates batch execution with SSE streaming."""
    
    def __init__(self, parallel_executor: ParallelExecutor):
        self.executor = parallel_executor
    
    async def execute_with_streaming(
        self,
        tasks: List[BatchTask],
        tool_registry: Dict[str, Callable],
        state_session,
        sse_manager
    ) -> Tuple[List[BatchResult], Dict[str, Any]]:
        """
        Execute batch with live SSE streaming updates.
        
        Returns:
            Tuple of (batch_results, summary_stats)
        """
        # Import here to avoid circular imports
        from .sse import emit_exec
        
        # Emit execution events for each task
        for task in tasks:
            await emit_exec(
                sse_manager,
                task.tool_name,
                task.args,
                batch_idx=task.idx
            )
        
        # Execute batch
        results = await self.executor.execute_batch(tasks, tool_registry, state_session)
        
        # Calculate summary stats
        successful = [r for r in results if r.success]
        failed = [r for r in results if not r.success]
        
        total_duration = sum(r.duration for r in results)
        avg_duration = total_duration / len(results) if results else 0
        
        summary = {
            'total_tasks': len(tasks),
            'successful': len(successful),
            'failed': len(failed),
            'success_rate': len(successful) / len(results) if results else 0,
            'total_duration': total_duration,
            'average_duration': avg_duration,
            'error_classes': self._count_error_classes(failed)
        }
        
        logger.info(f"Batch summary: {summary['successful']}/{summary['total_tasks']} successful")
        
        return results, summary
    
    def _count_error_classes(self, failed_results: List[BatchResult]) -> Dict[str, int]:
        """Count error classes in failed results."""
        error_counts = {}
        for result in failed_results:
            if result.error_class:
                error_counts[result.error_class] = error_counts.get(result.error_class, 0) + 1
        return error_counts


def create_batch_tasks(plan_actions: List[Dict[str, Any]], state_session) -> List[BatchTask]:
    """
    Create batch tasks from planner actions.
    
    Args:
        plan_actions: List of action dictionaries from planner
        state_session: Session state for generating args keys
        
    Returns:
        List of batch tasks
    """
    tasks = []
    
    for idx, action_data in enumerate(plan_actions):
        tool_name = action_data.get('action', action_data.get('tool'))
        args = action_data.get('args', {})
        
        # Generate args key for duplicate detection
        args_key = state_session.canonicalize_args(tool_name, args)
        
        task = BatchTask(
            idx=idx,
            tool_name=tool_name,
            args=args,
            args_key=args_key
        )
        
        tasks.append(task)
    
    return tasks


def merge_batch_observations(results: List[BatchResult], max_chars: int = 4000) -> str:
    """
    Merge batch results into a single observation string.
    
    Args:
        results: List of batch results
        max_chars: Maximum characters in merged observation
        
    Returns:
        Merged observation string
    """
    if not results:
        return "No results from batch execution"
    
    obs_parts = []
    successful_count = sum(1 for r in results if r.success)
    failed_count = len(results) - successful_count
    
    # Summary header
    obs_parts.append(f"Batch execution: {successful_count}/{len(results)} successful")
    
    # Individual results (truncated if needed)
    char_budget = max_chars - len(obs_parts[0]) - 100  # Reserve space
    char_per_result = char_budget // len(results) if results else 0
    char_per_result = max(50, min(char_per_result, 500))  # Reasonable bounds
    
    for result in results:
        if result.success:
            result_str = str(result.result)
            if len(result_str) > char_per_result:
                result_str = result_str[:char_per_result] + "..."
            obs_parts.append(f"[{result.idx}] {result_str}")
        else:
            obs_parts.append(f"[{result.idx}] ERROR: {result.error}")
    
    merged = "\n".join(obs_parts)
    
    # Final truncation if still too long
    if len(merged) > max_chars:
        merged = merged[:max_chars] + "... [batch obs clipped]"
    
    return merged


def validate_batch_safety(tasks: List[BatchTask], max_batch_size: int = 10) -> List[str]:
    """
    Validate batch safety constraints.
    
    Args:
        tasks: List of batch tasks
        max_batch_size: Maximum allowed batch size
        
    Returns:
        List of validation errors (empty if valid)
    """
    errors = []
    
    # Check batch size
    if len(tasks) > max_batch_size:
        errors.append(f"Batch size {len(tasks)} exceeds maximum {max_batch_size}")
    
    # Check for conflicting operations
    write_operations = ['delete_files', 'write_file', 'move_file']
    write_tasks = [t for t in tasks if t.tool_name in write_operations]
    
    if len(write_tasks) > 1:
        errors.append("Multiple write operations in batch not allowed")
    
    # Check for duplicate args_keys
    args_keys = [t.args_key for t in tasks]
    if len(set(args_keys)) != len(args_keys):
        errors.append("Duplicate operations detected in batch")
    
    # Check for resource conflicts (same paths)
    path_tasks = {}
    for task in tasks:
        for arg_name in ['path', 'dir', 'file']:
            if arg_name in task.args:
                path = str(task.args[arg_name])
                if path in path_tasks:
                    errors.append(f"Path conflict: {path} used by multiple tasks")
                path_tasks[path] = task
    
    return errors


# Default parallel executor instance
default_executor = ParallelExecutor(max_workers=4, timeout=60.0)