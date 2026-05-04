from kimi_agent_sdk import CallableTool2, ToolError, ToolOk, ToolReturnValue
from pydantic import BaseModel, Field


class Params(BaseModel):
    image_path: str = Field(
        description="Image file path."
    )
    output_path: str = Field(
        default="",
        description="Output text file path (optional)."
    )
    language: str = Field(
        default="eng",
        description="Language code for OCR (default: eng)."
    )
    preprocess: bool = Field(
        default=False,
        description="Apply preprocessing to improve OCR accuracy."
    )


class Ocr(CallableTool2):
    name: str = "Ocr"
    description: str = "Extract text from images via OCR."
    params: type[Params] = Params

    async def __call__(self, params: Params) -> ToolReturnValue:
        import os
        import sys
        from pathlib import Path

        # Validate image path
        if not os.path.exists(params.image_path):
            return ToolError(
                output="",
                message=f"Image file not found: {params.image_path}",
                brief="File not found",
            )

        # Check file extension
        valid_extensions = {'.png', '.jpg', '.jpeg', '.gif', '.bmp', '.tiff', '.webp'}
        ext = os.path.splitext(params.image_path)[1].lower()
        if ext not in valid_extensions:
            return ToolError(
                output="",
                message=f"Unsupported image format: {ext}. Supported formats: {', '.join(valid_extensions)}",
                brief="Unsupported image format",
            )

        # Try importing required libraries
        try:
            from PIL import Image, ImageEnhance
        except ImportError:
            return ToolError(
                output="",
                message="PIL (Pillow) is not installed. Install with: pip install pillow",
                brief="Missing dependency: pillow",
            )

        try:
            import pytesseract
        except ImportError:
            return ToolError(
                output="",
                message="pytesseract is not installed. Install with: pip install pytesseract",
                brief="Missing dependency: pytesseract",
            )

        try:
            # Open image
            image = Image.open(params.image_path)

            # Preprocess if requested
            if params.preprocess:
                # Convert to grayscale
                image = image.convert('L')
                # Enhance contrast
                enhancer = ImageEnhance.Contrast(image)
                image = enhancer.enhance(2.0)

            # Extract text using OCR
            text = pytesseract.image_to_string(image, lang=params.language)

            # Clean up the extracted text
            text = text.strip()

            if not text:
                return ToolOk(
                    output="[No text detected in the image]",
                    message="OCR completed but no text was found in the image.",
                )

            # Save to file if output path specified
            if params.output_path:
                output_dir = os.path.dirname(os.path.abspath(params.output_path))
                if output_dir and not os.path.exists(output_dir):
                    os.makedirs(output_dir, exist_ok=True)
                
                with open(params.output_path, 'w', encoding='utf-8') as f:
                    f.write(text)
                
                return ToolOk(
                    output=f"Text extracted and saved to: {params.output_path}",
                    message=f"Extracted {len(text)} characters from the image.",
                )
            else:
                # Return content directly (truncated if too long)
                max_length = 10000
                if len(text) > max_length:
                    truncated = text[:max_length] + "\n\n... [content truncated]"
                    return ToolOk(
                        output=truncated,
                        message=f"Content was truncated (total: {len(text)} characters). Use output_path parameter to save full content to file.",
                    )
                return ToolOk(
                    output=text,
                    message=f"Extracted {len(text)} characters from the image.",
                )

        except pytesseract.TesseractNotFoundError:
            return ToolError(
                output="",
                message="Tesseract OCR engine is not installed or not in PATH. Please install Tesseract: https://github.com/UB-Mannheim/tesseract/wiki",
                brief="Tesseract not found",
            )
        except Exception as e:
            return ToolError(
                output="",
                message=f"OCR failed: {str(e)}",
                brief="Image text extraction failed",
            )
