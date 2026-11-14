# Ras Laffan Plant Drawing Chatbot

An AI-ready PDF drawing search server built with FastAPI and MCP.

## Features

- Upload PDF drawings through a protected API.
- Extract searchable text from PDF files.
- Store drawing and page information in SQLite.
- Search drawings by keywords.
- List uploaded drawings.
- Read extracted drawing pages.
- Provide MCP tools for AI assistants.

## Technology

- Python
- FastAPI
- SQLite FTS5
- PyPDF
- MCP
- Render

## Deployment

This project can be deployed on Render.

Render uses the following commands:

Build command:

pip install -r requirements.txt

Start command:

uvicorn server:app --host 0.0.0.0 --port $PORT

Health check:

/health

## Environment Variables

The following environment variables are configured in Render:

- DATA_DIR
- UPLOAD_API_KEY
- MCP_ACCESS_TOKEN

Render generates secure values for the API keys.

## Important Storage Note

The free Render plan uses temporary storage.

Uploaded PDF files and the SQLite database may disappear after a restart, redeployment, or service interruption.

Persistent storage requires an appropriate paid storage option.

## API Endpoints

- GET /health
- POST /upload
- MCP endpoint: /mcp

## Limitations

The current version extracts searchable text from PDFs.

Scanned PDFs and image-only drawings may require OCR support.

## Security

Keep API keys and access tokens private.

Do not upload confidential company or project drawings unless you have permission.