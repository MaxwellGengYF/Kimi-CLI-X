import asyncio
from pathlib import Path
from kimi_agent_sdk import CallableTool2, ToolError, ToolOk, ToolReturnValue
from pydantic import BaseModel, Field
from typing import override
from my_tools.skill.searching.file_builder import FileBuilder, formatted_print


class IndexerParams(BaseModel):
    """Parameters for the indexer tool."""
    query: str = Field(
        description="Search keywords/query."
    )
    top_k: int = Field(
        default=5,
        ge=1,
        le=20,
        description="Number of top results to return."
    )



class SkillRag(CallableTool2[IndexerParams]):
    """Indexer tool for semantic search over text files."""

    name: str = "SkillRag"
    description: str = "Search keywords in skills."
    params: type[IndexerParams] = IndexerParams
    file_builder_inited: bool = False
    file_builder: FileBuilder | None = None

    @override
    async def __call__(self, params: IndexerParams) -> ToolReturnValue:
        import kimix.base as base
        if not self.file_builder_inited:
            skill_dirs = base.get_skill_dirs(False)
            self.file_builder = FileBuilder(skill_dirs, '.kimix_cache/skill_config.json')
            self.file_builder_inited = True
        if self.file_builder is None:
            return ToolOk(output='')
        try:
            self.file_builder.update()
            results = self.file_builder.search(
                params.query, top_k=params.top_k)
            return ToolOk(output=formatted_print(results))
        except Exception as e:
            return ToolError(
                message=str(e),
                output="",
                brief="Search failed"
            )
