"""Base abstractions for Agno-backed agents."""

from abc import ABC, abstractmethod
from typing import Any, TypeVar

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


class BaseAgent(ABC):
    """Abstract base class for all Agno-backed agents."""

    def __init__(
        self,
        model_id: str,
        instructions: list[str],
        agent: Any | None = None,
    ) -> None:
        """Create an Agno-backed agent wrapper.

        Args:
            model_id: OpenAI model id used by Agno.
            instructions: System-level instructions for the agent.
            agent: Optional prebuilt agent, useful for tests.
        """
        self._agent = agent or self._create_agent(model_id, instructions)

    @property
    @abstractmethod
    def agent_name(self) -> str:
        """Return the human-readable agent name.

        Returns:
            Agent name used in logs and debugging.
        """

    async def _run_structured(self, prompt: str, schema: type[T]) -> T:
        """Run the underlying Agno agent with structured output.

        Args:
            prompt: Prompt sent to the agent.
            schema: Pydantic schema expected from the response.

        Returns:
            Validated structured response.
        """
        response = await self._agent.arun(prompt, output_schema=schema)
        if isinstance(response.content, schema):
            return response.content
        return schema.model_validate(response.content)

    def _create_agent(self, model_id: str, instructions: list[str]) -> Any:
        """Create the concrete Agno agent lazily.

        Args:
            model_id: OpenAI model id used by Agno.
            instructions: System-level instructions for the agent.

        Returns:
            Configured Agno agent.
        """
        from agno.agent import Agent
        from agno.models.openai import OpenAIResponses

        return Agent(model=OpenAIResponses(id=model_id), instructions=instructions)
