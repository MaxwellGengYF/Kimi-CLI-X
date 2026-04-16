"""Fetch web page content as Markdown."""
import asyncio
from pathlib import Path

from kimi_agent_sdk import CallableTool2, ToolError, ToolOk, ToolReturnValue
from pydantic import BaseModel, Field

from my_tools.web.web_fetcher import fetch_to_markdown


class Params(BaseModel):
    """Parameters for FetchURL tool."""
    url: str = Field(
        description="URL to fetch content from."
    )
    output_path: str | None = Field(
        default=None,
        description="Optional file path to save the fetched markdown content."
    )


class FetchURL(CallableTool2):
    """Fetch a web page and return its content as Markdown."""
    name: str = "FetchURL"
    description: str = "Fetch content from a URL using a headless browser and return it as Markdown."
    params: type[Params] = Params

    async def __call__(self, params: Params) -> ToolReturnValue:
        """Fetch URL content asynchronously and return markdown."""
        try:
            markdown = await fetch_to_markdown(params.url)
        except Exception as exc:
            return ToolError(
                message=str(exc),
                output="",
                brief="Failed to fetch URL"
            )

        if params.output_path:
            try:
                output_file = Path(params.output_path)
                output_file.parent.mkdir(parents=True, exist_ok=True)
                await asyncio.to_thread(output_file.write_text, markdown, encoding="utf-8")
                return ToolOk(
                    output=f"Content saved to {params.output_path} ({len(markdown)} characters)."
                )
            except Exception as exc:
                return ToolError(
                    message=str(exc),
                    output=markdown,
                    brief="Failed to write output file"
                )

        # Truncate very long content for direct output
        max_length = 10000
        if len(markdown) > max_length:
            truncated = markdown[:max_length] + "\n\n... [content truncated]"
            return ToolOk(
                output=truncated,
                message=f"Content was truncated (total: {len(markdown)} characters). Use output_path parameter to save full content to file."
            )

        return ToolOk(output=markdown)
