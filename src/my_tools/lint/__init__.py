"""Unified syntax lint tool that dispatches based on file extension."""

import asyncio
from pathlib import Path

from kimi_agent_sdk import CallableTool2, ToolError, ToolOk, ToolReturnValue
from pydantic import BaseModel, Field

from my_tools.common import _maybe_export_output_async
from my_tools.lint.cpp_lint import Cpplint
# from .js_lint import func
from .py_lint import MypyCheck


class Params(BaseModel):
    """Parameters for unified syntax lint."""

    file_path: str = Field(description="Path to the file to validate.")
    project_root: str = Field(
        default=".",
        description="Root directory of the project (default: current directory).",
    )
    clangd_path: str = Field(
        default="clangd",
        description="Path to the clangd executable for C++ files (default: 'clangd').",
    )
    verbose: bool = Field(
        default=False,
        description="Include verbose output.",
    )


_EXTENSION_MAP = {
    # Python
    ".py": MypyCheck,
    # JavaScript / TypeScript
    # ".js": JsTsSyntaxCheck,
    # ".jsx": JsTsSyntaxCheck,
    # ".mjs": JsTsSyntaxCheck,
    # ".cjs": JsTsSyntaxCheck,
    # ".ts": JsTsSyntaxCheck,
    # ".tsx": JsTsSyntaxCheck,
    # C++
    ".cpp": Cpplint,
    ".cc": Cpplint,
    ".cxx": Cpplint,
    ".h": Cpplint,
    ".hpp": Cpplint,
    ".hxx": Cpplint,
    ".hh": Cpplint,
    ".c++": Cpplint,
}


class SyntaxLint(CallableTool2):  # type: ignore[type-arg]
    """Check file syntax using the appropriate linter based on file extension."""

    name: str = "SyntaxLint"
    description: str = (
        "Validate file syntax using language-specific tools. "
        "Supports Python (.py), JavaScript/TypeScript (.js, .jsx, .ts, .tsx, .mjs, .cjs), "
        "and C++ (.cpp, .cc, .cxx, .h, .hpp, .hxx, .hh, .c++)."
    )
    params: type[Params] = Params

    async def __call__(self, params: Params) -> ToolReturnValue:
        file_path = Path(params.file_path)

        if not await asyncio.to_thread(file_path.exists):
            return ToolError(
                output="",
                message=f"File not found: {file_path}",
                brief="File not found",
            )

        ext = file_path.suffix.lower()
        tool_class = _EXTENSION_MAP.get(ext)

        if tool_class is None:
            supported = ", ".join(sorted(set(_EXTENSION_MAP.keys())))
            msg = f"Unsupported file extension: {ext}. Supported: {supported}"
            return ToolError(
                output=msg,
                message=msg,
                brief="Unsupported file type",
            )

        # Build sub-tool params based on what each tool expects
        tool_instance = tool_class()
        # if tool_class is JsTsSyntaxCheck:
        #     sub_params = tool_class.params(
        #         file_path=params.file_path,
        #         verbose=params.verbose,
        #     )
        if tool_class is MypyCheck:
            sub_params = tool_class.params(
                file_path=params.file_path,
                project_root=params.project_root,
                verbose=params.verbose,
            )
        elif tool_class is Cpplint:
            sub_params = tool_class.params(
                file_path=params.file_path,
                project_root=params.project_root,
                clangd_path=params.clangd_path,
                verbose=params.verbose,
            )
        else:
            # Fallback — should never happen
            return ToolError(
                output="",
                message=f"Unknown linter class: {tool_class.__name__}",
                brief="Internal linter dispatch error",
            )

        try:
            result: ToolReturnValue = await tool_instance(sub_params)
            return result
        except Exception as e:
            return ToolError(
                output="",
                message=f"Lint tool failed: {e}",
                brief="Lint failed",
            )
