"""FastAPI application exposing search and RAG answering."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, StreamingResponse
from pydantic import BaseModel

from ..config import Config
from ..generate import build_generator
from ..generate.base import Generator
from ..generate.rag import rag_answer, stream_events
from ..index.embed import OllamaEmbedder
from ..index.store import SearchIndex
from ..retrieve.hybrid import HybridRetriever
from ..store import Catalog

PAGE = r"""<!doctype html>
<html lang="sk">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Bratislava Open Data</title>
<style>
  :root { --ink:#0f172a; --muted:#64748b; --accent:#0ea5e9; --line:#e2e8f0; }
  * { box-sizing:border-box; }
  body { font-family:system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;
         background:#f1f5f9; color:var(--ink); max-width:820px; margin:0 auto;
         padding:2.5rem 1rem 4rem; }
  h1 { font-size:1.5rem; margin:0 0 1.2rem; }
  .badge { font-size:.65rem; font-weight:600; letter-spacing:.06em; padding:.2rem .5rem;
           border-radius:999px; background:#e0f2fe; color:#0369a1; vertical-align:middle; }
  .bar { display:flex; gap:.5rem; }
  input { flex:1; font-size:1rem; padding:.75rem .9rem; border:1px solid #cbd5e1;
          border-radius:10px; outline:none; }
  input:focus { border-color:var(--accent); box-shadow:0 0 0 3px #0ea5e933; }
  button { font-size:1rem; padding:.75rem 1.3rem; border:0; border-radius:10px;
           background:var(--accent); color:#fff; cursor:pointer; }
  button:disabled { opacity:.5; cursor:default; }
  .status { display:none; align-items:center; gap:.6rem; margin:1rem 0 .2rem;
            color:#475569; font-size:.9rem; }
  .status.on { display:flex; }
  .spinner { width:15px; height:15px; border:2px solid #cbd5e1; border-top-color:var(--accent);
             border-radius:50%; animation:spin .9s linear infinite; }
  @keyframes spin { to { transform:rotate(360deg); } }
  .thread { display:flex; flex-direction:column; gap:1.6rem; margin-top:1.4rem; }
  .question { font-weight:600; margin:0 0 .5rem; }
  .question::before { content:"› "; color:var(--accent); }
  .answer { background:#fff; border-left:5px solid var(--accent); border-radius:12px;
            padding:1.1rem 1.25rem; margin:0 0 .6rem; white-space:pre-wrap; line-height:1.6;
            box-shadow:0 1px 3px #0f172a14; }
  .answer:empty { display:none; }
  .verify { margin:.2rem 0 .4rem; font-size:.85rem; color:#b45309; }
  .sources { background:#f8fafc; border:1px solid var(--line); border-radius:12px;
             padding:1rem 1.25rem; margin-top:1rem; }
  .sources h2 { font-size:.75rem; letter-spacing:.08em; text-transform:uppercase;
                color:var(--muted); margin:.1rem 0 .7rem; }
  .sources ol { margin:0; padding-left:1.3rem; }
  .sources li { margin:.35rem 0; }
  .sources a { color:#0369a1; text-decoration:none; }
  .sources a:hover { text-decoration:underline; }
  .evidence { margin-top:.8rem; padding-top:.7rem; border-top:1px dashed #cbd5e1;
              font-size:.85rem; color:#475569; }
  .evidence pre { background:#0f172a; color:#e2e8f0; padding:.6rem .8rem; border-radius:8px;
                  overflow:auto; margin:.45rem 0; font-size:.8rem; }
</style>
</head>
<body>
<h1>Bratislava Open Data <span class="badge">RAG</span></h1>
<form class="bar" onsubmit="ask(event)">
  <input id="q" placeholder="Napíšte otázku / Ask a question" autocomplete="off">
  <button id="go">Ask</button>
</form>

<div class="status" id="status"><span class="spinner"></span><span id="statusText"></span></div>
<div class="thread" id="thread"></div>

<script>
const el = (id) => document.getElementById(id);
let history = [];
let current = null;

async function ask(e){
  e.preventDefault();
  const q = el('q').value.trim();
  if(!q) return;
  el('go').disabled = true;
  el('q').value = '';
  current = addExchange(q);
  el('status').classList.add('on');
  el('statusText').textContent = '…';
  try {
    const r = await fetch('/ask/stream', {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({query:q, history:history})
    });
    const reader = r.body.getReader();
    const dec = new TextDecoder();
    let buf = '';
    while(true){
      const {value, done} = await reader.read();
      if(done) break;
      buf += dec.decode(value, {stream:true});
      let idx;
      while((idx = buf.indexOf('\n\n')) >= 0){
        const part = parseSSE(buf.slice(0, idx));
        buf = buf.slice(idx + 2);
        if(part) handle(part.event, part.data);
      }
    }
  } catch(err) {
    if(current) current.answer.textContent += '\n[error] ' + err;
  } finally {
    el('status').classList.remove('on');
    el('go').disabled = false;
    if(current){
      history.push({role:'user', content:q});
      history.push({role:'assistant', content:current.answer.textContent});
      if(history.length > 12) history = history.slice(-12);
    }
    current = null;
  }
}

function addExchange(q){
  const wrap = document.createElement('div');
  wrap.className = 'exchange';
  wrap.innerHTML =
    '<div class="question">' + escapeHtml(q) + '</div>' +
    '<div class="answer"></div>' +
    '<div class="verify" style="display:none"></div>' +
    '<div class="sources" style="display:none">' +
      '<h2>Zdroje / Sources</h2><ol></ol>' +
      '<div class="evidence" style="display:none"></div>' +
    '</div>';
  el('thread').appendChild(wrap);
  return {
    answer: wrap.querySelector('.answer'),
    verify: wrap.querySelector('.verify'),
    sources: wrap.querySelector('.sources'),
    sourceList: wrap.querySelector('.sources ol'),
    evidence: wrap.querySelector('.evidence')
  };
}

function parseSSE(chunk){
  let event = 'message', data = '';
  for(const line of chunk.split('\n')){
    if(line.startsWith('event:')) event = line.slice(6).trim();
    else if(line.startsWith('data:')) data += line.slice(5).trim();
  }
  if(!data) return null;
  try { return {event, data: JSON.parse(data)}; }
  catch(e){ return null; }
}

function handle(event, data){
  if(!current) return;
  if(event === 'status'){
    el('statusText').textContent = data.message;
  } else if(event === 'sources'){
    renderSources(current, data.sources || []);
    renderEvidence(current, data.data);
    current.sources.style.display = 'block';
  } else if(event === 'token'){
    current.answer.textContent += data.text;
  } else if(event === 'verification'){
    if((data.warnings || []).length){
      current.verify.textContent = '⚠️ ' + data.warnings.join('; ');
      current.verify.style.display = 'block';
    }
  } else if(event === 'error'){
    current.answer.textContent += '\n[error] ' + data.error;
  }
}

function renderSources(ex, items){
  ex.sourceList.innerHTML = items.slice(0, 8).map(s =>
    '<li><a href="' + s.url + '" target="_blank" rel="noopener">' +
    escapeHtml(s.title || s.dataset_id) + '</a></li>').join('');
}

function renderEvidence(ex, d){
  if(!d || !d.sql) return;
  let html = '<strong>Vypočítané z:</strong> ' + escapeHtml(d.title || '') +
             '<pre>' + escapeHtml(d.sql) + '</pre>';
  if(d.note) html += escapeHtml(d.note) + '<br>';
  if(d.district){
    html += 'Filter: ' + escapeHtml((d.district_column || '') + ' = ' + (d.district_value || ''));
  }
  ex.evidence.innerHTML = html;
  ex.evidence.style.display = 'block';
}

function escapeHtml(s){
  return String(s).replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
}
</script>
</body>
</html>"""


class Turn(BaseModel):
    role: str = "user"
    content: str


class QueryRequest(BaseModel):
    query: str
    top_k: int | None = None
    rerank: bool | None = None
    history: list[Turn] | None = None

    def history_dicts(self) -> list[dict[str, str]] | None:
        if not self.history:
            return None
        return [turn.model_dump() for turn in self.history]


def _sse(event: str, data: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def create_app(config_path: str | None = None) -> FastAPI:
    config = Config.load(config_path)
    state: dict[str, Any] = {"generator": None, "embedder": None}

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        # Load the heavy models once so the first request is fast.
        state["generator"] = build_generator(config)
        state["embedder"] = OllamaEmbedder(
            model=config.embeddings.model,
            host=config.embeddings.host,
            timeout=config.embeddings.timeout,
            batch_size=config.embeddings.batch_size,
        )
        try:
            warmup = getattr(state["generator"], "warmup", None)
            if callable(warmup):
                warmup()
            if config.search.rerank:
                from ..retrieve.rerank import get_reranker

                get_reranker(config.search.rerank_model)
        except Exception as exc:  # noqa: BLE001 - server should still start
            print(f"[warn] warmup failed: {type(exc).__name__}: {exc}")
        try:
            yield
        finally:
            state["embedder"].close()

    app = FastAPI(title="Bratislava Open Data RAG", lifespan=lifespan)

    def generator() -> Generator:
        current = state["generator"]
        if current is None:
            current = build_generator(config)
            state["generator"] = current
        return current

    def embedder() -> OllamaEmbedder:
        current = state["embedder"]
        if current is None:
            current = OllamaEmbedder(
                model=config.embeddings.model,
                host=config.embeddings.host,
                timeout=config.embeddings.timeout,
                batch_size=config.embeddings.batch_size,
            )
            state["embedder"] = current
        return current

    @app.get("/health")
    def health() -> dict[str, Any]:
        return {"status": "ok", "model": config.generation.model}

    @app.post("/search")
    def search(request: QueryRequest) -> list[dict[str, Any]]:
        catalog = Catalog(config.paths.db)
        try:
            index = SearchIndex(catalog.con, config.embeddings.dim)
            retriever = HybridRetriever(catalog, index, embedder(), config)
            results = retriever.search(
                request.query, top_k=request.top_k, rerank=request.rerank
            )
        finally:
            catalog.close()
        return [
            {
                "dataset_id": r.dataset_id,
                "title": r.title,
                "url": r.url,
                "license": r.license,
                "score": r.score,
                "concepts": r.concepts,
            }
            for r in results
        ]

    @app.post("/ask")
    def ask(request: QueryRequest) -> dict[str, Any]:
        catalog = Catalog(config.paths.db)
        try:
            result = rag_answer(
                config,
                catalog,
                request.query,
                generator(),
                top_k=request.top_k,
                rerank=request.rerank,
                embedder=embedder(),
                history=request.history_dicts(),
            )
        finally:
            catalog.close()
        return {
            "answer": result.answer,
            "intent": result.intent,
            "sources": result.sources,
            "data": result.data,
            "answer_verified": result.answer_verified,
            "warnings": result.warnings,
        }

    @app.post("/ask/stream")
    def ask_stream(request: QueryRequest) -> StreamingResponse:
        catalog = Catalog(config.paths.db)

        def event_stream() -> Iterator[str]:
            try:
                for event in stream_events(
                    config,
                    catalog,
                    request.query,
                    generator(),
                    top_k=request.top_k,
                    rerank=request.rerank,
                    embedder=embedder(),
                    history=request.history_dicts(),
                ):
                    name = event.pop("event")
                    yield _sse(name, event)
            except Exception as exc:  # noqa: BLE001 - report over the stream
                yield _sse("error", {"error": f"{type(exc).__name__}: {exc}"})
            finally:
                catalog.close()

        return StreamingResponse(event_stream(), media_type="text/event-stream")

    @app.get("/", response_class=HTMLResponse)
    def index() -> str:
        return PAGE

    return app
