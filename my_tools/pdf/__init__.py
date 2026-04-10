from kimi_agent_sdk import CallableTool2, ToolError, ToolOk, ToolReturnValue
from pydantic import BaseModel, Field


class Params(BaseModel):
    pdf_path: str = Field(
        description="Path to the PDF file to convert."
    )
    output_path: str = Field(
        default="",
        description="Optional path to save the output markdown file."
    )
    extract_images: bool = Field(
        default=False,
        description="Whether to extract images from the PDF."
    )
    ocr: bool = Field(
        default=False,
        description="Whether to run OCR on extracted images."
    )
    extract_tables: bool = Field(
        default=True,
        description="Whether to extract tables from the PDF."
    )
    page_range: str = Field(
        default="",
        description="Page range to convert (e.g., '0-5' for pages 1-6, '3' for single page). Empty means all pages."
    )


class PdfToMarkdown(CallableTool2):
    name: str = "PdfToMarkdown"
    description: str = "Convert a PDF document to Markdown format, with optional image extraction, OCR, and table extraction."
    params: type[Params] = Params

    async def __call__(self, params: Params) -> ToolReturnValue:
        import os
        import sys
        from pathlib import Path

        # Add parent directory to path to import pdf_to_md
        sys.path.insert(0, str(Path(__file__).parent.parent.parent))
        
        try:
            from .pdf_to_md import pdf_to_markdown
        except ImportError as e:
            return ToolError(
                output="",
                message=f"Failed to import pdf_to_md: {str(e)}",
                brief="PDF conversion module not available",
            )

        # Validate PDF path
        if not os.path.exists(params.pdf_path):
            return ToolError(
                output="",
                message=f"PDF file not found: {params.pdf_path}",
                brief="File not found",
            )

        # Parse page range
        page_range = None
        if params.page_range:
            try:
                if '-' in params.page_range:
                    start, end = params.page_range.split('-', 1)
                    page_range = (int(start), int(end))
                else:
                    page_num = int(params.page_range)
                    page_range = (page_num, page_num)
            except ValueError:
                return ToolError(
                    output="",
                    message=f"Invalid page range format: {params.page_range}",
                    brief="Invalid page range",
                )

        # Determine output path
        output_path = params.output_path if params.output_path else None

        try:
            markdown_content = pdf_to_markdown(
                pdf_path=params.pdf_path,
                output_path=output_path,
                extract_imgs=params.extract_images,
                ocr=params.ocr,
                extract_tbls=params.extract_tables,
                page_range=page_range,
            )

            if output_path:
                return ToolOk(
                    output=f"Markdown saved to: {output_path}",
                )
            else:
                # Return content directly (truncated if too long)
                max_length = 10000
                if len(markdown_content) > max_length:
                    truncated = markdown_content[:max_length] + "\n\n... [content truncated]"
                    return ToolOk(
                        output=truncated,
                        message="Content was truncated. Use output_path parameter to save full content to file.",
                    )
                return ToolOk(output=markdown_content)

        except FileNotFoundError as e:
            return ToolError(
                output="",
                message=str(e),
                brief="File not found",
            )
        except Exception as e:
            return ToolError(
                output="",
                message=str(e),
                brief="PDF conversion failed",
            )
