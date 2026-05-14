import asyncio

from kimi_agent_sdk import CallableTool2, ToolError, ToolOk, ToolReturnValue
from pydantic import BaseModel, Field
from typing import override
from kimi_cli.session import Session

from kimix.utils import close_session_async, _create_session_async
from kimix.base import get_skill_dirs
from kimix.tools.common import _maybe_export_output_async
from kimix.utils.system_prompt import SystemPromptType, SystemPromptCallback


class IndexerParams(BaseModel):
    """Parameters for the indexer tool."""
    prompt: str = Field(
        description="Search prompt."
    )
    dest_path: list[str] | None = Field(
        default=None,
        description="Destination path."
    )


class Retrieve(CallableTool2[IndexerParams]):
    """Indexer tool for semantic search over text files."""

    name: str = "Retrieve"
    description: str = "Search skills by keywords."
    params: type[IndexerParams] = IndexerParams

    def __init__(self, session: Session):
        super().__init__()
        self._session = session
        self._semaphore = asyncio.Semaphore(8)

    @override
    async def __call__(self, params: IndexerParams) -> ToolReturnValue:
        if self._session is not None and self._session.custom_config.get("is_sub_agent"):
            return ToolError(
                output='',
                message='Recursive sub-agent call detected',
                brief='sub-agent recursively'
            )
        async with self._semaphore:
            try:
                output_strs = []

                def output_function(fn: str, is_thinking: bool) -> None:
                    if fn and not is_thinking:
                        output_strs.append(fn)

                async def prompt_async(cancel_callable=None):
                    session = None
                    try:
                        import kimix.base as base
                        custom_config = self._session.custom_config
                        chat_provider = custom_config.get("chat_provider")
                        provider_dict = custom_config.get("provider_dict")
                        if provider_dict is None:
                            provider_dict = dict(base._default_provider) if base._default_provider is not None else {}
                        provider_dict["thinking_effort"] = 'off'
                        extra_system_prompt = SystemPromptCallback()
                        if params.dest_path is not None:
                            dest_path = params.dest_path
                        else:
                            skill_dirs = [str(d) for d in get_skill_dirs(use_kaos_path=False)]
                            dest_path = skill_dirs + ['.kimix_cache/'] if skill_dirs else ['.kimix_cache/']
                        dest_path_str = ', '.join(dest_path)

                        def role_callback(agent_role: SystemPromptType, items: list[str]):
                            items.append(f'Retrieve skills, docs from: {dest_path_str}.')

                        extra_system_prompt.role_callback = role_callback

                        session = await _create_session_async(
                            agent_file=base._default_agent_file_dir / 'agent_searcher.yaml',
                            agent_type=SystemPromptType.SkillSearcher,
                            provider_dict=provider_dict,
                            chat_provider=chat_provider,
                            extra_system_prompt=extra_system_prompt,
                        )
                        session.get_custom_config()['is_sub_agent'] = True
                        import kimix.utils as utils
                        await utils.prompt_async(prompt_str=params.prompt, session=session, output_function=output_function, info_print=False, cancel_callable=cancel_callable, merge_wire_messages=True)
                    except Exception as e:
                        return str(e)
                    finally:
                        if session:
                            await close_session_async(session)
                    return None

                err_msg = await prompt_async()
                output = await _maybe_export_output_async('\n'.join(output_strs))
                if err_msg:
                    return ToolError(output=output, message=err_msg, brief='')
                return ToolOk(output=output)
            except Exception as exc:
                return ToolError(
                    output="",
                    message=str(exc),
                    brief="Failed to create session",
                )
