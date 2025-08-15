"""Dynamic tool registry and configuration-driven loader."""
import importlib
import yaml
import logging
from typing import Dict, Callable, Any, List
from pathlib import Path


logger = logging.getLogger(__name__)


class ToolRegistry:
    """Dynamic registry for tool functions with policy enforcement."""
    
    def __init__(self):
        self.tools: Dict[str, Callable] = {}
        self.policies: Dict[str, Dict[str, Any]] = {}
        self.loaded_modules: Dict[str, Any] = {}
    
    def register(self, name: str, func: Callable, policy: Dict[str, Any] = None):
        """Register a tool function."""
        self.tools[name] = func
        if policy:
            self.policies[name] = policy
        logger.debug(f"Registered tool: {name}")
    
    def load_from_config(self, config_path: str):
        """Load tools from YAML configuration."""
        try:
            with open(config_path, 'r') as f:
                config = yaml.safe_load(f)
            
            tools_config = config.get('tools', {})
            
            for tool_name, tool_config in tools_config.items():
                if not tool_config.get('enabled', True):
                    logger.info(f"Tool {tool_name} disabled in config")
                    continue
                
                # Load tool function
                try:
                    if 'module' in tool_config and 'fn' in tool_config:
                        # Dynamic import for plugins
                        module_path = tool_config['module']
                        function_name = tool_config['fn']
                        
                        if module_path not in self.loaded_modules:
                            self.loaded_modules[module_path] = importlib.import_module(module_path)
                        
                        module = self.loaded_modules[module_path]
                        tool_func = getattr(module, function_name)
                        
                    else:
                        # Built-in tools
                        tool_func = self._get_builtin_tool(tool_name)
                    
                    if tool_func:
                        self.register(tool_name, tool_func, tool_config)
                        logger.info(f"Loaded tool: {tool_name}")
                    else:
                        logger.warning(f"Tool function not found: {tool_name}")
                
                except Exception as e:
                    logger.error(f"Failed to load tool {tool_name}: {e}")
        
        except Exception as e:
            logger.error(f"Failed to load tool config: {e}")
            # Load default tools as fallback
            self._load_default_tools()
    
    def _get_builtin_tool(self, tool_name: str) -> Callable:
        """Get built-in tool function."""
        builtin_mapping = {
            'list_files': 'api.tools.core_fs.list_files',
            'read_file': 'api.tools.core_fs.read_file',
            'count_files': 'api.tools.core_fs.count_files',
            'count_dirs': 'api.tools.core_fs.count_dirs',
            'delete_files': 'api.tools.core_fs.delete_files',
            'web_get': 'api.tools.core_web.web_get',
            'analyze': 'api.tools.core_llm.analyze',
            'summarize': 'api.tools.core_llm.summarize'
        }
        
        if tool_name in builtin_mapping:
            module_path, func_name = builtin_mapping[tool_name].rsplit('.', 1)
            try:
                if module_path not in self.loaded_modules:
                    self.loaded_modules[module_path] = importlib.import_module(module_path)
                
                module = self.loaded_modules[module_path]
                return getattr(module, func_name)
            except Exception as e:
                logger.error(f"Failed to load builtin tool {tool_name}: {e}")
        
        return None
    
    def _load_default_tools(self):
        """Load default core tools."""
        default_tools = [
            'list_files', 'read_file', 'count_files', 'count_dirs',
            'web_get', 'analyze'
        ]
        
        for tool_name in default_tools:
            tool_func = self._get_builtin_tool(tool_name)
            if tool_func:
                self.register(tool_name, tool_func, {'enabled': True})
    
    def get_tool(self, name: str) -> Callable:
        """Get tool function by name."""
        return self.tools.get(name)
    
    def get_policy(self, name: str) -> Dict[str, Any]:
        """Get tool policy configuration."""
        return self.policies.get(name, {})
    
    def list_tools(self) -> List[str]:
        """List all registered tool names."""
        return list(self.tools.keys())
    
    def is_enabled(self, name: str) -> bool:
        """Check if tool is enabled."""
        policy = self.get_policy(name)
        return policy.get('enabled', True)
    
    def validate_args(self, tool_name: str, args: Dict[str, Any]) -> Dict[str, Any]:
        """Validate tool arguments against policy."""
        from ..utils.sandbox import validate_tool_args
        
        policy = self.get_policy(tool_name)
        return validate_tool_args(tool_name, args, {'tools': {tool_name: policy}})
    
    def get_tool_info(self) -> Dict[str, Any]:
        """Get information about all registered tools."""
        info = {}
        for name in self.tools:
            policy = self.get_policy(name)
            info[name] = {
                'enabled': policy.get('enabled', True),
                'requires_confirm': policy.get('require_confirm', False),
                'destructive': name in ['delete_files'],
                'policy': policy
            }
        return info


# Global tool registry instance
tool_registry = ToolRegistry()


def get_tool_registry() -> ToolRegistry:
    """Get the global tool registry."""
    return tool_registry


def initialize_tools(config_path: str = None):
    """Initialize tools from configuration."""
    if config_path and Path(config_path).exists():
        tool_registry.load_from_config(config_path)
    else:
        logger.warning("No tool config found, loading defaults")
        tool_registry._load_default_tools()