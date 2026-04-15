"""
Base AI Service class with common functionality for all AI service integrations.
"""

import logging
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class BaseAIService(ABC):
    """
    Abstract base class for AI service integrations.
    Provides common functionality and interface for all AI services.
    """

    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize the AI service with an API key.
        
        Args:
            api_key: API key for the service (optional, can be set via environment)
        """
        self.api_key = api_key
        self.client = None
        self._initialize_client()

    @abstractmethod
    def _initialize_client(self):
        """Initialize the service client."""
        pass

    @abstractmethod
    def generate(
        self,
        prompt: str,
        system_prompt: str = "",
        model_name: str = None,
        max_tokens: int = 1500,
        temperature: float = 0.0,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Generate a response from the AI service.

        Args:
            prompt: User prompt
            system_prompt: System instructions
            model_name: Model to use
            max_tokens: Maximum response tokens
            temperature: Response creativity (0.0-1.0)
            **kwargs: Additional service-specific parameters

        Returns:
            Dict with response data including content, metadata, and usage stats
        """
        pass

    def generate_structured(
        self,
        prompt: str,
        system_prompt: str,
        json_schema: Dict[str, Any],
        model_name: str = None,
        max_tokens: int = 1500,
        temperature: float = 0.0,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Generate a structured JSON response from the AI service.

        Uses native structured output APIs when available (OpenAI JSON mode,
        Anthropic tool_use, Google JSON mode), falling back to prompt-based
        instructions for providers without native support.

        Args:
            prompt: User prompt
            system_prompt: System instructions
            json_schema: JSON Schema defining the expected response structure
            model_name: Model to use
            max_tokens: Maximum response tokens
            temperature: Response creativity (0.0-1.0)
            **kwargs: Additional service-specific parameters

        Returns:
            Dict with response data. The 'content' field will be a JSON string
            matching the provided schema (when generation is successful).
        """
        raise NotImplementedError(
            f"{self.__class__.__name__} does not implement generate_structured()"
        )

    def _create_response_dict(
        self,
        content: str,
        model: str,
        usage: Dict[str, int],
        success: bool = True,
        error: str = None,
        **additional_data
    ) -> Dict[str, Any]:
        """
        Create a standardized response dictionary.
        
        Args:
            content: Generated content
            model: Model used
            usage: Token usage statistics
            success: Whether generation was successful
            error: Error message if failed
            **additional_data: Additional data to include
            
        Returns:
            Standardized response dictionary
        """
        response = {
            "content": content,
            "model": model,
            "usage": usage,
            "metadata": {
                "service": self.__class__.__name__.replace("Service", ""),
                "timestamp": datetime.now().isoformat(),
                "created_at": datetime.now().isoformat(),
            },
            "success": success,
        }
        
        if error:
            response["error"] = error
            
        # Add any additional data
        response.update(additional_data)
        
        return response

    def _create_error_response(
        self,
        error: Exception,
        model: str,
        service_name: str = None
    ) -> Dict[str, Any]:
        """
        Create a standardized error response.
        
        Args:
            error: Exception that occurred
            model: Model that was attempted
            service_name: Name of the service (optional)
            
        Returns:
            Error response dictionary
        """
        service_name = service_name or self.__class__.__name__.replace("Service", "")
        error_str = str(error)
        
        logger.error(f"❌ {service_name} API Error: {error_str}")
        
        return self._create_response_dict(
            content="",
            model=model,
            usage={"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
            success=False,
            error=error_str
        )