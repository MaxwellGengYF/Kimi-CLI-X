"""JavaScript/TypeScript syntax check tool using Tree-sitter."""

import asyncio
from pathlib import Path

from kimi_agent_sdk import CallableTool2, ToolError, ToolOk, ToolReturnValue
from pydantic import BaseModel, Field

from my_tools.common import _maybe_export_output_async

# Eagerly import tree-sitter languages once at module load to avoid repeated
# import overhead on every tool invocation.
from tree_sitter import Language, Parser
import tree_sitter_javascript as _js_lang
import tree_sitter_typescript as _ts_lang

_LANGUAGES = {
    ".js": Language(_js_lang.language()),
    ".jsx": Language(_js_lang.language()),
    ".mjs": Language(_js_lang.language()),
    ".cjs": Language(_js_lang.language()),
    ".ts": Language(_ts_lang.language_typescript()),
    ".tsx": Language(_ts_lang.language_tsx()),
}

# Cache parsers per language so we don't recreate them every call.
_PARSER_CACHE: dict[int, Parser] = {}


def _get_language(ext: str) -> Language | None:
    """Get Tree-sitter language for a file extension."""
    return _LANGUAGES.get(ext.lower())


def _collect_errors(root, source_bytes: bytes):
    """Iteratively collect ERROR and missing nodes."""
    stack = [root]
    while stack:
        node = stack.pop()
        if node.type == "ERROR":
            start_line = node.start_point[0] + 1
            start_col = node.start_point[1] + 1
            end_line = node.end_point[0] + 1
            end_col = node.end_point[1] + 1
            snippet = source_bytes[node.start_byte : node.end_byte]
            try:
                snippet_str = snippet.decode("utf-8", errors="replace")
            except Exception:
                snippet_str = repr(snippet)
            yield {
                "kind": "error",
                "message": "Unexpected token",
                "start_line": start_line,
                "start_col": start_col,
                "end_line": end_line,
                "end_col": end_col,
                "snippet": snippet_str,
            }
        if node.is_missing:
            start_line = node.start_point[0] + 1
            start_col = node.start_point[1] + 1
            yield {
                "kind": "missing",
                "message": f"Missing '{node.type}'",
                "start_line": start_line,
                "start_col": start_col,
                "end_line": start_line,
                "end_col": start_col,
                "snippet": "",
            }
        # Push children in reverse so they are processed left-to-right.
        stack.extend(reversed(node.children))


def _format_errors(errors: list[dict], verbose: bool) -> str:
    """Format collected errors into a human-readable string."""
    if not errors:
        return "No syntax issues found."

    lines = []
    for err in errors:
        loc = f"line {err['start_line']}, col {err['start_col']}"
        if err["start_line"] != err["end_line"] or err["start_col"] != err["end_col"]:
            loc += f" - line {err['end_line']}, col {err['end_col']}"
        kind_label = "Error" if err["kind"] == "error" else "Missing"
        msg = f"{kind_label}: {err['message']} at {loc}"
        if err["snippet"]:
            snippet = err["snippet"].replace("\n", "\\n")
            msg += f' (near "{snippet}")'
        lines.append(msg)

    result = "\n".join(lines)
    if verbose:
        result = f"Total syntax issues: {len(errors)}\n{result}"

    return result


class Params(BaseModel):
    """Parameters for JS/TS syntax check."""

    file_path: str = Field(description="Path to the JavaScript or TypeScript file to validate.")
    verbose: bool = Field(
        default=False, description="Include detailed parse information in output."
    )


class JsTsSyntaxCheck(CallableTool2):
    """Check JavaScript/TypeScript syntax using Tree-sitter."""

    name: str = "JsTsSyntaxCheck"
    description: str = (
        "Validate JavaScript/TypeScript file syntax using Tree-sitter. "
        "Supports .js, .jsx, .ts, .tsx, .mjs, .cjs files."
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

        ext = file_path.suffix
        language = _get_language(ext)
        if language is None:
            msg = f"Unsupported file extension: {ext}. Supported: .js, .jsx, .ts, .tsx, .mjs, .cjs"
            return ToolError(
                output=msg,
                message=msg,
                brief="Unsupported file type",
            )

        try:
            source_bytes = await asyncio.to_thread(file_path.read_bytes)
        except Exception as e:
            return ToolError(
                output="",
                message=f"Failed to read file: {e}",
                brief="Failed to read file",
            )

        try:
            parser = _PARSER_CACHE.get(id(language))
            if parser is None:
                parser = Parser(language)
                _PARSER_CACHE[id(language)] = parser
            tree = parser.parse(source_bytes)
        except Exception as e:
            return ToolError(
                output="",
                message=f"Failed to parse file: {e}",
                brief="Parse failed",
            )

        root = tree.root_node
        errors = list(_collect_errors(root, source_bytes))

        if not errors and not root.has_error:
            output = f"No syntax issues found in {file_path.name}."
            if params.verbose:
                output += f"\nFile type: {ext}\nParse tree root: {root.type}"
            output = await _maybe_export_output_async(output)
            return ToolOk(output=output)

        formatted = _format_errors(errors, params.verbose)
        summary = f"\n{'-' * 60}\nTotal syntax issues: {len(errors)}"
        output = formatted + summary

        if params.verbose:
            output += f"\nFile type: {ext}\nParse tree root: {root.type}"

        output = await _maybe_export_output_async(output)
        return ToolError(
            output=output,
            message=f"Found {len(errors)} syntax issue(s) in {file_path.name}",
            brief=f"Syntax errors: {len(errors)} issue(s)",
        )
