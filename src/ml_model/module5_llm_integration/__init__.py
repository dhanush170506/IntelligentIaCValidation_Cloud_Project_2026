"""Module 5 - LLM Integration."""
from .prompt_engineering import (
    AssurancePromptEngineer,
    EngineeredPrompt,
    PromptContext,
    PromptEngineeringError,
)
from .bedrock_schema import (
    BedrockRequest,
    BedrockResponse,
    BedrockSchemaError,
)

from .bedrock_client import (
    BedrockClient,
    BedrockClientError,
    MockBedrockClient,
    AwsBedrockClient,
)

from .bedrock_adapter import (
    BedrockAdapter,
    BedrockAdapterError,
)

from .recommendation_schema import (
    Recommendation,
    RecommendationAction,
    RecommendationPriority,
    RecommendationReport,
    RecommendationSchemaError,
)

from .recommendation_engine import (
    RecommendationEngine,
    RecommendationEngineError,
)

from .confidence_scoring import (
    ConfidenceScorer,
    ConfidenceAssessment,
    ConfidenceScoringError,
)
__all__ = [
    "BedrockRequest",
    "BedrockResponse",
    "BedrockSchemaError",
    "BedrockClient",
    "BedrockClientError",
    "MockBedrockClient",
    "AwsBedrockClient",
    "BedrockAdapter",
    "BedrockAdapterError",
    "AssurancePromptEngineer",
    "EngineeredPrompt",
    "PromptContext",
    "PromptEngineeringError",
    "Recommendation",
    "RecommendationAction",
    "RecommendationPriority",
    "RecommendationReport",
    "RecommendationSchemaError",
    "RecommendationEngine",
    "RecommendationEngineError",
    "ConfidenceScorer",
    "ConfidenceAssessment",
    "ConfidenceScoringError",
]