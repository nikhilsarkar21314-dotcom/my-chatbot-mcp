import os, re, sqlite3, hashlib, secrets
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, UploadFile, File, Header, HTTPException
from fastapi.responses import JSONResponse
from pypdf import PdfReader
from mcp.server.fastmcp import FastMCP

DATA_DIR = Path(os.getenv("DATA_DIR", "/var/data"))
PDF_DIR = DATA_DIR / "drawings"
DB_PATH = DATA_DIR / "drawings.sqlite3"
UPLOAD_API_KEY = os.getenv("UPLOAD_API_KEY", "")
MCP_ACCESS_TOKEN = os.getenv("MCP_ACCESS_TOKEN", "")
MAX_UPLOAD_MB = int(os.getenv("MAX_UPLOAD_MB", "100"))

PDF_DIR.mkdir(parents=True, exist_ok=True)


def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("""CREATE TABLE IF NOT EXISTS documents (
        id INTEGER PRIMARY KEY, filename TEXT UNIQUE NOT NULL,
        sha256 TEXT NOT NULL, page_count INTEGER NOT NULL,
        indexed_pages INTEGER NOT NULL DEFAULT 0, uploaded_at TEXT DEFAULT CURRENT_TIMESTAMP
    )""")
    conn.execute("""CREATE VIRTUAL TABLE IF NOT EXISTS pages USING fts5(
        filename UNINDEXED, page_no UNINDEXED, content,
        tokenize='unicode61 remove_diacritics 2'
    )""")
    conn.commit()
    return conn


def safe_filename(name: str) -> str:
    name = Path(name or "drawing.pdf").name
    name = re.sub(r"[^A-Za-z0-9._ -]", "_", name).strip(" .")
    if not name.lower().endswith(".pdf"):
        name += ".pdf"
    return name[:180] or "drawing.pdf"


def index_pdf(path: Path, digest: str):
    reader = PdfReader(str(path))
    conn = db()
    conn.execute("DELETE FROM pages WHERE filename=?", (path.name,))
    indexed = 0
    for page_no, page in enumerate(reader.pages, start=1):
        text = (page.extract_text() or "").strip()
        if text:
            conn.execute("INSERT INTO pages(filename,page_no,content) VALUES(?,?,?)",
                         (path.name, str(page_no), text))
            indexed += 1
    conn.execute("""INSERT INTO documents(filename,sha256,page_count,indexed_pages)
        VALUES(?,?,?,?) ON CONFLICT(filename) DO UPDATE SET
        sha256=excluded.sha256,page_count=excluded.page_count,indexed_pages=excluded.indexed_pages,
        uploaded_at=CURRENT_TIMESTAMP""",
        (path.name, digest, len(reader.pages), indexed))
    conn.commit()
    conn.close()
    return len(reader.pages), indexed


mcp = FastMCP("Ras Laffan Plant Drawing Assistant")

@mcp.tool()
def search_drawings(query: str, limit: int = 10) -> dict:
    """Search uploaded PDF drawing text for drawing numbers, line numbers, tags, valves, instruments, materials or keywords."""
    query = (query or "").strip()
    if not query:
        return {"results": [], "message": "Enter a drawing number, line number, tag or keyword."}
    limit = max(1, min(int(limit), 30))
    # FTS phrase search first; fall back to a safe token-AND query.
    conn = db()
    tokens = re.findall(r"[A-Za-z0-9_./-]+", query)
    if not tokens:
        conn.close(); return {"results": []}
    fts_query = " AND ".join('"' + t.replace('"', '') + '"' for t in tokens)
    try:
        rows = conn.execute("""SELECT filename,page_no,snippet(pages,2,'[',']',' … ',18) AS excerpt
            FROM pages WHERE pages MATCH ? LIMIT ?""", (fts_query, limit)).fetchall()
    except sqlite3.OperationalError:
        rows = []
    if not rows:
        like = "%" + query.replace("%", "") + "%"
        rows = conn.execute("""SELECT filename,page_no,substr(content,1,700) AS excerpt
            FROM pages WHERE content LIKE ? LIMIT ?""", (like, limit)).fetchall()
    conn.close()
    return {"query": query, "count": len(rows), "results": [dict(r) for r in rows],
            "note": "Search results are text matches. Always verify dimensions, revisions and construction details against the original controlled drawing."}

@mcp.tool()
def list_drawings(limit: int = 50) -> dict:
    """List PDFs uploaded to the drawing library and show page/indexing counts."""
    limit = max(1, min(int(limit), 200))
    conn = db()
    rows = conn.execute("SELECT filename,page_count,indexed_pages,uploaded_at FROM documents ORDER BY filename LIMIT ?", (limit,)).fetchall()
    conn.close()
    return {"count": len(rows), "drawings": [dict(r) for r in rows]}

@mcp.tool()
def read_drawing_pages(filename: str, start_page: int = 1, end_page: int = 2) -> dict:
    """Extract text from a selected page range of an uploaded PDF. Page numbers start at 1."""
    filename = safe_filename(filename)
    path = PDF_DIR / filename
    if not path.exists():
        return {"error": "Drawing not found. Use list_drawings to see uploaded filenames."}
    start_page = max(1, int(start_page)); end_page = max(start_page, min(int(end_page), start_page + 9))
    reader = PdfReader(str(path))
    if start_page > len(reader.pages):
        return {"error": f"PDF has {len(reader.pages)} pages."}
    result = []
    for n in range(start_page, min(end_page, len(reader.pages)) + 1):
        result.append({"page": n, "text": (reader.pages[n-1].extract_text() or "[No selectable text found on this page; OCR may be needed.]" )[:12000]})
    return {"filename": filename, "pages": result,
            "warning": "Use the approved latest revision and verify all field work against the controlled original drawing."}


app = FastAPI(title="Ras Laffan Drawing AI MCP", version="1.0.0")

@app.middleware("http")
async def protect_mcp_endpoint(request, call_next):
    if request.url.path.startswith("/mcp"):
        expected = "Bearer " + MCP_ACCESS_TOKEN if MCP_ACCESS_TOKEN else ""
        supplied = request.headers.get("authorization", "")
        if not expected or not secrets.compare_digest(supplied, expected):
            return JSONResponse({"detail": "Missing or invalid bearer token"}, status_code=401)
    return await call_next(request)

@app.get("/health")
def health():
    return {"status": "ok", "service": "Ras Laffan Drawing AI MCP", "mcp_endpoint": "/mcp"}

@app.post("/upload")
async def upload_pdf(file: UploadFile = File(...), x_upload_key: Optional[str] = Header(default=None)):
    if not UPLOAD_API_KEY or not secrets.compare_digest(x_upload_key or "", UPLOAD_API_KEY):
        raise HTTPException(status_code=401, detail="Missing or invalid X-Upload-Key")
    if not (file.filename or "").lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are accepted")
    filename = safe_filename(file.filename)
    dest = PDF_DIR / filename
    temp = PDF_DIR / (filename + ".uploading")
    total = 0
    digest = hashlib.sha256()
    try:
        with temp.open("wb") as out:
            while True:
                chunk = await file.read(1024 * 1024)
                if not chunk: break
                total += len(chunk)
                if total > MAX_UPLOAD_MB * 1024 * 1024:
                    raise HTTPException(status_code=413, detail=f"PDF exceeds {MAX_UPLOAD_MB} MB limit")
                digest.update(chunk); out.write(chunk)
        # Validate PDF before replacing the existing file.
        reader = PdfReader(str(temp))
        if len(reader.pages) == 0:
            raise ValueError("PDF contains no pages")
        temp.replace(dest)
        pages, indexed = index_pdf(dest, digest.hexdigest())
        return {"uploaded": True, "filename": filename, "size_bytes": total,
                "pages": pages, "text_pages_indexed": indexed,
                "ocr_needed": indexed == 0,
                "message": "Uploaded and indexed" if indexed else "Uploaded, but no selectable text was found; OCR is required."}
    except HTTPException:
        if temp.exists(): temp.unlink()
        raise
    except Exception as exc:
        if temp.exists(): temp.unlink()
        raise HTTPException(status_code=400, detail=f"Could not read/index PDF: {str(exc)[:250]}")
    finally:
        await file.close()

# Mount the MCP Streamable HTTP endpoint at /mcp.
app.mount("/", mcp.streamable_http_app())
