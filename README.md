Ras Laffan Plant Drawing AI — MCP starter

A small PDF library and MCP server for searching plant drawing text. It is a starter implementation, not an approved engineering system.

## Features
- Upload PDF drawings through a protected HTTP endpoint.
- Extract selectable PDF text and index it in SQLite FTS5.
- MCP tools: `search_drawings`, `list_drawings`, `read_drawing_pages`.
- Persistent storage when deployed with the included Render disk configuration.

## Deploy on Render
1. Put these files in a GitHub repository.
2. In Render, create a new **Blueprint** and select that repository.
3. Review the generated environment secrets and persistent disk, then deploy.
4. Check `https://YOUR-SERVICE.onrender.com/health`.
5. MCP endpoint: `https://YOUR-SERVICE.onrender.com/mcp`.
6. In Render environment settings, copy `MCP_ACCESS_TOKEN` and `UPLOAD_API_KEY` securely. Do not share them in chat.

The included Render plan is `starter` because persistent disks generally require a paid web-service plan. Confirm current Render pricing before deploying.

## Upload a PDF
Use a REST client that can send a multipart file and header:

```bash
curl -X POST "https://YOUR-SERVICE.onrender.com/upload" \
-H "X-Upload-Key: YOUR_UPLOAD_API_KEY" \
-F "file=@P-1234-ISO-001.pdf"
```

## Connect an MCP client
- Transport: Streamable HTTP
- URL: `https://YOUR-SERVICE.onrender.com/mcp`
- Authentication: Bearer token using `MCP_ACCESS_TOKEN`

Exact authentication configuration depends on the MCP client. The server validates the bearer token at the MCP endpoint.

## Important limitations
- The first version indexes selectable text only. Scanned drawings and image-only pages need OCR; this code reports when no text was extracted.
- Text search can miss rotated, fragmented, handwritten, or poorly encoded drawing labels.
- Search results are not engineering approval. Always check the latest controlled revision, title block, legends, notes, dimensions, and site procedures before acting.
- Upload only documents you are authorized to store on the chosen cloud service. Check employer/client data-security rules first.

## Local run
```bash
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
export DATA_DIR=./data
export UPLOAD_API_KEY='replace-this'
export MCP_ACCESS_TOKEN='replace-this-too'
uvicorn server:app --reload --port 8000
```