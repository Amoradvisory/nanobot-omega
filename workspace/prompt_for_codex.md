```
You are an OpenAI Codex model, tasked with developing or integrating a new functionality for a Gemini CLI AI assistant.

## Context about the Gemini CLI Assistant:
- **Name**: Gemini CLI (an AI assistant specialized in software engineering tasks).
- **Runtime Environment**: Windows AMD64, Python 3.14.0.
- **Current Capabilities**:
    - Can execute shell commands (`run_shell_command`).
    - Can read/write files (`read_file`, `write_file`).
    - Can list directories (`list_dir`).
    - Can perform web searches (`web_search`).
    - Can interact with a browser via Playwright (though currently opening native Chrome directly for some tasks).
    - Can take screenshots.
- **Current Limitation**: While capable of taking screenshots, the assistant **cannot interpret the visual content** of these screenshots (e.g., cannot read text, identify UI elements, or verify content within an opened document). Its interaction is primarily text-based, file-based, and command-line based.

## The Request: Integrate OCR (Optical Character Recognition) Functionality

The Gemini CLI assistant needs to be enhanced with the ability to perform OCR on image files, specifically screenshots it has taken. This will allow it to "read" the text present in images, significantly improving its capacity to verify UI actions, extract information from visual output, and interact more intelligently with graphical applications.

## Detailed Requirements for the OCR Functionality:

1.  **Integration Method**:
    *   The OCR functionality should be provided as an **external, callable tool or script**.
    *   The Gemini CLI assistant will invoke this tool, passing it the path to an image file (e.g., a `.png` screenshot).
    *   The tool should return the extracted text as a string to the Gemini CLI assistant.
    *   It should ideally be callable via a simple command-line interface or a Python script that the Gemini CLI can execute.

2.  **Compatibility**:
    *   The solution **MUST be compatible with Windows (AMD64)**.
    *   Prefer solutions that are easy to install and set up on a Windows environment.

3.  **Core Functionality**:
    *   Given an image file path (e.g., `C:\AI
anobot-omega\workspace\output\screenshot.png`), the tool should process it and return all recognizable text.
    *   Consider standard OCR libraries/engines like Tesseract OCR. If Tesseract is used, provide clear instructions on how to install Tesseract-OCR for Windows and the Python wrapper (`pytesseract`).

4.  **Proposed Solution Structure (Example - you can suggest alternatives)**:
    *   A Python script (e.g., `ocr_tool.py`) that takes an image path as a command-line argument.
    *   `ocr_tool.py` would then use an OCR library (e.g., `pytesseract`) to process the image and print the extracted text to `stdout`.
    *   Example invocation by Gemini CLI: `python ocr_tool.py C:\path	o\image.png`
    *   Example output to `stdout`: `Extracted text from image: "Hello World"`

5.  **Error Handling**:
    *   The tool should handle cases where the image file does not exist, is corrupted, or contains no recognizable text.
    *   Informative error messages should be printed to `stderr` or `stdout` (prefixed for easy parsing).

## Why this is important for Gemini CLI:
This OCR capability will enable the Gemini CLI assistant to:
-   **Verify UI actions**: Confirm that specific text appears on screen after an action (e.g., "Login successful").
-   **Extract data**: Read information from web pages, documents, or application interfaces directly from screenshots.
-   **Improve debugging**: Understand visual error messages or log outputs in image format.
-   **Enhance interaction**: Navigate complex UIs by identifying text labels on buttons or fields.

Please provide:
1.  **The code for the OCR tool/script** (e.g., `ocr_tool.py`).
2.  **Step-by-step instructions** on how to set up the OCR engine (e.g., Tesseract) and any required Python libraries on a Windows system.
3.  Any other configuration or considerations needed for successful integration.
```