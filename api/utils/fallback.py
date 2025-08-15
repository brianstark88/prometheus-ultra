"""Model fallback and health checking utilities."""
import asyncio
import httpx
import logging
from typing import List, Optional, Dict, Any
from dataclasses import dataclass


logger = logging.getLogger(__name__)


@dataclass
class ModelConfig:
    """Configuration for a single model."""
    name: str
    base_url: str
    timeout: int = 30
    max_tokens: int = 4096
    supports_json: bool = True
    priority: int = 0  # Lower = higher priority


class ModelFallbackManager:
    """Manages model availability and fallback chain."""
    
    def __init__(self, primary_model: str, fallback_models: List[str], ollama_host: str = "http://127.0.0.1:11434"):
        self.primary_model = primary_model
        self.fallback_models = fallback_models
        self.ollama_host = ollama_host
        
        # Model configurations
        self.models = self._initialize_models()
        
        # Health status cache
        self.health_cache: Dict[str, Dict[str, Any]] = {}
        self.cache_ttl = 60  # seconds
        self.last_check: Dict[str, float] = {}
    
    def _initialize_models(self) -> Dict[str, ModelConfig]:
        """Initialize model configurations."""
        models = {}
        
        # Primary model
        models[self.primary_model] = ModelConfig(
            name=self.primary_model,
            base_url=self.ollama_host,
            priority=0
        )
        
        # Fallback models
        for i, model_name in enumerate(self.fallback_models):
            models[model_name] = ModelConfig(
                name=model_name,
                base_url=self.ollama_host,
                priority=i + 1
            )
        
        return models
    
    async def health_check(self, model_name: str) -> Dict[str, Any]:
        """Check health of a specific model."""
        if model_name not in self.models:
            return {'healthy': False, 'error': 'Model not configured'}
        
        # Check cache
        now = asyncio.get_event_loop().time()
        if (model_name in self.health_cache and 
            model_name in self.last_check and
            now - self.last_check[model_name] < self.cache_ttl):
            return self.health_cache[model_name]
        
        model_config = self.models[model_name]
        
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                # Check Ollama health
                health_response = await client.get(f"{model_config.base_url}/api/tags")
                
                if health_response.status_code != 200:
                    result = {'healthy': False, 'error': f'Ollama not responding: {health_response.status_code}'}
                else:
                    # Check if specific model is available
                    models_data = health_response.json()
                    available_models = [m['name'] for m in models_data.get('models', [])]
                    
                    if model_name in available_models:
                        # Test model with a simple query
                        test_result = await self._test_model(model_name, model_config)
                        result = {
                            'healthy': test_result['success'],
                            'error': test_result.get('error'),
                            'response_time': test_result.get('response_time', 0),
                            'available': True
                        }
                    else:
                        result = {
                            'healthy': False,
                            'error': f'Model {model_name} not found in Ollama',
                            'available': False,
                            'available_models': available_models
                        }
        
        except Exception as e:
            result = {
                'healthy': False,
                'error': f'Health check failed: {str(e)}',
                'available': False
            }
        
        # Cache result
        self.health_cache[model_name] = result
        self.last_check[model_name] = now
        
        return result
    
    async def _test_model(self, model_name: str, model_config: ModelConfig) -> Dict[str, Any]:
        """Test model with a simple query."""
        start_time = asyncio.get_event_loop().time()
        
        try:
            async with httpx.AsyncClient(timeout=model_config.timeout) as client:
                test_payload = {
                    "model": model_name,
                    "prompt": "Respond with exactly: OK",
                    "stream": False,
                    "options": {
                        "temperature": 0.0,
                        "num_predict": 10
                    }
                }
                
                response = await client.post(
                    f"{model_config.base_url}/api/generate",
                    json=test_payload
                )
                
                response_time = asyncio.get_event_loop().time() - start_time
                
                if response.status_code == 200:
                    data = response.json()
                    response_text = data.get('response', '').strip()
                    
                    return {
                        'success': 'OK' in response_text,
                        'response_time': response_time,
                        'response': response_text
                    }
                else:
                    return {
                        'success': False,
                        'error': f'HTTP {response.status_code}',
                        'response_time': response_time
                    }
        
        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'response_time': asyncio.get_event_loop().time() - start_time
            }
    
    async def get_available_model(self) -> Optional[str]:
        """Get the best available model from the fallback chain."""
        models_to_try = [self.primary_model] + self.fallback_models
        
        for model_name in models_to_try:
            health = await self.health_check(model_name)
            if health['healthy']:
                logger.info(f"Using model: {model_name}")
                return model_name
            else:
                logger.warning(f"Model {model_name} unhealthy: {health.get('error')}")
        
        logger.error("No healthy models available")
        return None
    
    async def call_with_fallback(self, payload: Dict[str, Any], max_retries: int = 3) -> Dict[str, Any]:
        """Call LLM with automatic fallback on failure."""
        models_to_try = [self.primary_model] + self.fallback_models
        last_error = None
        
        for attempt, model_name in enumerate(models_to_try):
            if attempt >= max_retries:
                break
            
            # Check health first
            health = await self.health_check(model_name)
            if not health['healthy']:
                last_error = health.get('error', 'Model unhealthy')
                continue
            
            try:
                model_config = self.models[model_name]
                
                # Update payload with current model
                call_payload = payload.copy()
                call_payload['model'] = model_name
                
                async with httpx.AsyncClient(timeout=model_config.timeout) as client:
                    response = await client.post(
                        f"{model_config.base_url}/api/generate",
                        json=call_payload
                    )
                    
                    if response.status_code == 200:
                        data = response.json()
                        return {
                            'success': True,
                            'data': data,
                            'model_used': model_name,
                            'attempt': attempt + 1
                        }
                    else:
                        last_error = f"HTTP {response.status_code}: {response.text}"
            
            except Exception as e:
                last_error = str(e)
                logger.warning(f"Model {model_name} failed: {last_error}")
                
                # Mark model as unhealthy
                self.health_cache[model_name] = {
                    'healthy': False,
                    'error': last_error
                }
                self.last_check[model_name] = asyncio.get_event_loop().time()
        
        return {
            'success': False,
            'error': f'All models failed. Last error: {last_error}',
            'attempts': len(models_to_try)
        }
    
    async def get_system_status(self) -> Dict[str, Any]:
        """Get overall system health status."""
        all_models = [self.primary_model] + self.fallback_models
        model_status = {}
        
        for model_name in all_models:
            model_status[model_name] = await self.health_check(model_name)
        
        healthy_models = [name for name, status in model_status.items() if status['healthy']]
        
        return {
            'ollama_host': self.ollama_host,
            'primary_model': self.primary_model,
            'healthy_models': healthy_models,
            'total_models': len(all_models),
            'system_healthy': len(healthy_models) > 0,
            'model_details': model_status
        }


def create_fallback_manager(primary: str, fallbacks: List[str], host: str) -> ModelFallbackManager:
    """Factory function to create fallback manager."""
    return ModelFallbackManager(primary, fallbacks, host)