# PDFShield 🛡️

**PDFShield** is a privacy-focused Chrome Extension that automatically redacts Personally Identifiable Information (PII) from PDF documents. It runs locally on your machine to ensure your sensitive data never leaves your computer.

## Features

*   **Local Processing**: All redaction happens on your own machine. No files are uploaded to the cloud.
*   **Automated PII Detection**:
    *   **English**: Detects Names, Phone Numbers, Emails, US SSN, and Driver Licenses using `Microsoft Presidio`.
    *   **Hebrew**: Detects Names, Locations, Organizations using `heBERT` (Hugging Face) and Israeli IDs/Phone Numbers using custom patterns.
*   **Chrome Extension**: Easy-to-use popup interface for uploading and downloading files.
*   **Free & Unlimited**: No API limits or subscription costs.

## Architecture

*   **Frontend**: Chrome Extension (Manifest V3)
*   **Backend**: Local Python Server (Flask)
    *   **PDF Processing**: `PyMuPDF`
    *   **PII Detection**: `Microsoft Presidio` + `Transformers` (Hugging Face)

## Installation

### 1. Backend Setup (Python Server)

1.  Clone the repository:
    ```bash
    git clone https://github.com/udivak/PDFShield.git
    cd PDFShield
    ```

2.  Create and activate a virtual environment (optional but recommended):
    ```bash
    python3 -m venv .venv
    source .venv/bin/activate
    ```

3.  Install dependencies:
    ```bash
    pip install -r backend/requirements.txt
    python -m spacy download en_core_web_sm
    ```

4.  Start the server:
    ```bash
    python backend/app.py
    ```
    *Note: The first run may take a few minutes to download the Hebrew NER model (~440MB).*

### 2. Extension Setup (Chrome)

1.  Open Chrome and navigate to `chrome://extensions`.
2.  Enable **Developer mode** (toggle in the top right).
3.  Click **Load unpacked**.
4.  Select the `extension` folder from this repository.

## Usage

1.  Ensure the backend server is running (`python backend/app.py`).
2.  Click the **PDFShield** icon in your Chrome toolbar.
3.  Select the document language (**English** or **Hebrew**).
4.  Click **Choose PDF File** and select your document.
5.  Click **Redact & Download**.
6.  The redacted PDF will be automatically downloaded.

## Technologies

*   [Flask](https://flask.palletsprojects.com/)
*   [Microsoft Presidio](https://microsoft.github.io/presidio/)
*   [PyMuPDF](https://pymupdf.readthedocs.io/)
*   [Hugging Face Transformers](https://huggingface.co/docs/transformers/index)
*   [heBERT](https://huggingface.co/avichr/heBERT_NER)

