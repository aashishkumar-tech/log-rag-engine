# FastAPI backend (LangChain version)
import os
import uuid
import tempfile
from typing import List, Dict, Any
import threading
import shutil
from datetime import datetime
import time

from fastapi import FastAPI, UploadFile, File, HTTPException, BackgroundTasks, Response, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from dotenv import load_dotenv

from rag.loaders import load_log_files, extract_issue_docs
from rag.splitter import split_context
from rag.vectorstore import VectorStores, FAISS_DIR, BM25_STATE
from rag.retriever import build_ensemble, fetch_sources
from rag.chain import build_chain, run_qa, build_summary_chain, build_extended_summary_chain  # updated import
from utils.logger import get_logger, log_startup_summary
from utils.grouping import group_key  # NEW

load_dotenv()
logger = get_logger("API")
log_startup_summary(logger)
VERBOSE = os.getenv('LOG_VERBOSE','0') == '1'

def vdebug(msg,*args,**kw):
    if VERBOSE:
        logger.debug(msg,*args,**kw)

def vinfo(msg,*args,**kw):
    if VERBOSE:
        logger.info(msg,*args,**kw)

# Global state
VECTORSTORES = VectorStores(embedding_backend=os.getenv("EMBED_BACKEND", "hf"))  # default hf; FAST_EMBED=1 switches to fastembed internally
ENSEMBLE = None
QA_CHAIN = None
SUMMARY_CHAIN = None
EXT_SUMMARY_CHAIN = None  # NEW
LAST_BUILD_TS: float | None = None
LAST_BUILD_ERROR: str | None = None  # NEW: capture last build failure
STATE_LOCK = threading.Lock()
BUILDING = False  # NEW: track background build state

ERROR_STORE: Dict[str, Dict[str, Any]] = {}
GROUPS: Dict[str, Dict[str, Any]] = {}  # NEW grouping store
GROUP_ISSUES = os.getenv("GROUP_ISSUES", "1") == "1"  # feature flag
DEDUP_ERRORS = os.getenv('DEDUP_ERRORS', '1') == '1'
OCCURRENCE_COUNTS: Dict[str, int] = {}  # NEW: total occurrences per group_key/error

app = FastAPI(title="Log RAG API (LangChain)", version="0.3")  # RE-ADD app instantiation (version bumped)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.mount("/ui", StaticFiles(directory="web", html=True), name="ui")

CONTEXT_CHUNK_SIZE = int(os.getenv("CHUNK_SIZE", 1500))  # increased default chunk size for fewer chunks (faster small corpora)
CONTEXT_CHUNK_OVERLAP = int(os.getenv("CHUNK_OVERLAP", 150))
TOP_K = int(os.getenv("TOP_K", 8))
# Use Azure deployment name first (if present) so logs show actual model used
MODEL_NAME = os.getenv("AZURE_OPENAI_DEPLOYMENT") or os.getenv("OPENAI_MODEL", "gpt-3.5-turbo")  # UPDATED
ASYNC_BUILD = os.getenv("ASYNC_BUILD", "1") == "1"
TRACE_RUN = os.getenv("TRACE_RUN", "0") == "1"
RUN_ID: str | None = None
RUN_DIR = os.path.join("logs", "runs")
if TRACE_RUN:
    os.makedirs(RUN_DIR, exist_ok=True)

METRICS_LOG = os.getenv("METRICS_LOG", "1") == "1"  # enable metrics comparison logging
EMBEDDING_DIM = int(os.getenv("EMBEDDING_DIM", "384"))  # default for MiniLM-L6
METRICS_PATH = os.path.join("logs", "runs", "metrics.jsonl")

DIAG_ENABLE = os.getenv('DIAG_ENABLE', '1') == '1'
DIAG_ISSUE_SAMPLE = int(os.getenv('DIAG_ISSUE_SAMPLE', '50'))
DIAG_CONTEXT_SAMPLE = int(os.getenv('DIAG_CONTEXT_SAMPLE', '20'))


class ResolveRequest(BaseModel):
    id: str

class ResolveBatchRequest(BaseModel):
    ids: List[str]

class MarkResolvedRequest(BaseModel):
    ids: List[str]
    resolved: bool = True

class SummaryRequest(BaseModel):
    id: str


def _rebuild_chain():
    global ENSEMBLE, QA_CHAIN, SUMMARY_CHAIN, LAST_BUILD_TS  # include SUMMARY_CHAIN
    logger.debug("Rebuilding chain: retrieving retrievers (TOP_K=%s)", TOP_K)
    vect, bm25 = VECTORSTORES.as_retrievers(k=TOP_K)
    ENSEMBLE = build_ensemble(vect, bm25, weights=(0.6, 0.4))
    QA_CHAIN = build_chain(ENSEMBLE, model_name=MODEL_NAME)
    SUMMARY_CHAIN = None  # force lazy rebuild of summary chain with new retriever
    LAST_BUILD_TS = time.time()
    logger.info("QA chain rebuilt (vector=%s bm25=%s)", bool(vect), bool(bm25))


def _index_build(issue_docs, context_docs, raw_docs, original_issue_count: int | None = None, distinct_issue_count: int | None = None):  # background build helper
    global BUILDING, ENSEMBLE, QA_CHAIN, LAST_BUILD_TS, LAST_BUILD_ERROR
    BUILDING = True
    LAST_BUILD_ERROR = None
    logger.info("Background build started: issues=%d context_chunks=%d", len(issue_docs), len(context_docs))
    t0 = time.time()
    try:
        with STATE_LOCK:
            first_time = VECTORSTORES.faiss_store is None or ENSEMBLE is None
            if VECTORSTORES.faiss_store is None:
                VECTORSTORES.build(issue_docs, context_docs)
            else:
                VECTORSTORES.add(issue_docs, context_docs)
            timing = VECTORSTORES.get_last_timing() if hasattr(VECTORSTORES, 'get_last_timing') else {}
            small_fast = timing.get('small_corpus_fast_path')
            # ALWAYS early release after vector index build; chain build deferred
            LAST_BUILD_TS = time.time()
            logger.info("Early release indexing (first=%s small_fast=%s) total_ms=%s", first_time, small_fast, timing.get('total_ms'))
        # Record metrics & diagnostics before releasing BUILDING flag to preserve ordering
        try:
            _record_ingest_metrics(RUN_ID, source_files=len(issue_docs), docs=issue_docs + context_docs, issue_docs=issue_docs, context_docs=context_docs, incremental=not first_time and VECTORSTORES.faiss_store is not None, original_issue_count=original_issue_count, distinct_issue_count=distinct_issue_count)
            _write_run_diagnostic(RUN_ID, raw_docs, issue_docs, context_docs, incremental=not first_time and VECTORSTORES.faiss_store is not None)
        except Exception:
            pass
        # Defer chain (and retriever ensemble) build to separate thread so UI sees indexing complete quickly
        def _defer_chain():
            global ENSEMBLE, QA_CHAIN, SUMMARY_CHAIN
            try:
                if ENSEMBLE is None:  # need to create retrievers
                    vect, bm25 = VECTORSTORES.as_retrievers(k=TOP_K)
                    ENSEMBLE = build_ensemble(vect, bm25, weights=(0.6,0.4))
                if QA_CHAIN is None:
                    _rebuild_chain()  # will rebuild and log
            except Exception as e:  # pragma: no cover
                logger.warning("Deferred chain build failed: %s", e)
        import threading as _t
        _t.Thread(target=_defer_chain, daemon=True).start()
    except Exception as e:  # pragma: no cover
        LAST_BUILD_ERROR = str(e)
        logger.exception(f"Background index build failed: {e}")
    finally:
        BUILDING = False
        logger.debug("BUILDING flag cleared (universal early release)")


def _trace_write_initial(run_id: str, issues: list[dict], context_docs):
    if not TRACE_RUN:
        return
    try:
        initial_path = os.path.join(RUN_DIR, f"{run_id}-initial.json")
        # Summarize context chunks (avoid huge file): metadata + first 160 chars
        summarized = [
            {
                'idx': i,
                'source': getattr(d, 'metadata', {}).get('source'),
                'line_no': getattr(d, 'metadata', {}).get('line_no'),
                'preview': getattr(d, 'page_content', '')[:160]
            } for i, d in enumerate(context_docs)
        ]
        import json
        with open(initial_path, 'w', encoding='utf-8') as f:
            json.dump({'run_id': run_id, 'issues': issues, 'context_chunks': summarized}, f, ensure_ascii=False, indent=2)
    except Exception as e:  # pragma: no cover
        logger.warning("Trace initial write failed: %s", e)


def _trace_append_resolve(run_id: str, record: dict):
    if not TRACE_RUN:
        return
    try:
        import json, time as _t
        path = os.path.join(RUN_DIR, f"{run_id}-resolves.jsonl")
        record['ts'] = datetime.utcnow().isoformat() + 'Z'
        with open(path, 'a', encoding='utf-8') as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception as e:  # pragma: no cover
        logger.warning("Trace append failed: %s", e)


def _estimate_context_tokens(chunk_size: int, chunk_count: int) -> int:
    # heuristic: average utilized chars ~ 0.75 * chunk_size, 4 chars/token
    return int(chunk_count * (chunk_size * 0.75 / 4))


def _write_metrics(record: dict):
    if not METRICS_LOG:
        return
    try:
        os.makedirs(os.path.dirname(METRICS_PATH), exist_ok=True)
        with open(METRICS_PATH, 'a', encoding='utf-8') as f:
            import json
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception as e:
        logger.warning("Failed writing metrics record: %s", e)


def _record_ingest_metrics(run_id: str | None, source_files: int, docs, issue_docs, context_docs, incremental: bool, original_issue_count: int | None = None, distinct_issue_count: int | None = None):
    if not METRICS_LOG:
        return
    timing = VECTORSTORES.get_last_timing() if hasattr(VECTORSTORES, 'get_last_timing') else {}
    embedded_docs = len(getattr(VECTORSTORES, '_embedded_docs', []))
    bm25_enabled = VECTORSTORES.bm25_retriever is not None
    bm25_auto_disabled = getattr(VECTORSTORES, 'bm25_auto_disabled', False)
    bm25_auto_threshold = getattr(VECTORSTORES, 'bm25_auto_threshold', 0)
    total_lines = len(docs)
    filtered_lines = total_lines  # placeholder until pre-filter implemented
    context_chunks = len(context_docs)
    est_ctx_tokens = _estimate_context_tokens(CONTEXT_CHUNK_SIZE, context_chunks)
    memory_est_mb = round(embedded_docs * EMBEDDING_DIM * 4 / 1e6, 3)  # float32 bytes
    record = {
        'run_id': run_id or str(uuid.uuid4()),
        'timestamp': datetime.utcnow().isoformat() + 'Z',
        'source_files': source_files,
        'issues_total': original_issue_count if original_issue_count is not None else len(issue_docs),  # NEW
        'issues_distinct': distinct_issue_count if distinct_issue_count is not None else len(issue_docs),  # NEW
        'total_lines': total_lines,
        'filtered_lines': filtered_lines,
        'issue_count': len(issue_docs),  # retained for backward compatibility
        'context_chunks': context_chunks,
        'chunk_size': CONTEXT_CHUNK_SIZE,
        'chunk_overlap': CONTEXT_CHUNK_OVERLAP,
        'embedded_docs': embedded_docs,
        'bm25_enabled': bm25_enabled,
        'bm25_auto_disabled': bm25_auto_disabled,
        'bm25_auto_threshold': bm25_auto_threshold,
        'bm25_docs_used': timing.get('bm25_docs_used'),
        'faiss_ms': timing.get('faiss_ms'),
        'bm25_ms': timing.get('bm25_ms'),
        'persist_ms': timing.get('persist_ms'),
        'total_ms': timing.get('total_ms'),
        'incremental': incremental,
        'model_name': MODEL_NAME,
        'embed_backend': os.getenv('EMBED_BACKEND', 'hf'),
        'estimated_context_tokens': est_ctx_tokens,
        'memory_est_mb': memory_est_mb,
    }
    _write_metrics(record)


def _write_run_diagnostic(run_id: str | None, raw_docs, issue_docs, context_docs, incremental: bool):
    if not DIAG_ENABLE:
        return
    try:
        diag = {}
        diag['run_id'] = run_id or ''
        diag['timestamp'] = datetime.utcnow().isoformat() + 'Z'
        diag['lines_total'] = len(raw_docs) if raw_docs is not None else (len(issue_docs) + len(context_docs))
        diag['issues'] = len(issue_docs)
        diag['context_chunks'] = len(context_docs)
        diag['chunk_size'] = CONTEXT_CHUNK_SIZE
        diag['chunk_overlap'] = CONTEXT_CHUNK_OVERLAP
        diag['incremental'] = incremental
        timing = VECTORSTORES.get_last_timing() if hasattr(VECTORSTORES, 'get_last_timing') else {}
        diag['timing'] = timing
        diag['bm25_enabled'] = VECTORSTORES.bm25_retriever is not None
        diag['bm25_auto_disabled'] = getattr(VECTORSTORES, 'bm25_auto_disabled', False)
        diag['bm25_auto_threshold'] = getattr(VECTORSTORES, 'bm25_auto_threshold', 0)
        diag['embedded_docs'] = len(getattr(VECTORSTORES, '_embedded_docs', []))
        diag['embedding_backend'] = os.getenv('EMBED_BACKEND','hf')
        diag['model_name'] = MODEL_NAME
        # Sample issues
        diag['sample_issues'] = [
            {
                'id': getattr(d, 'metadata', {}).get('id'),
                'line_no': d.metadata.get('line_no'),
                'source': d.metadata.get('source'),
                'severity': d.metadata.get('severity', ''),
                'text': d.page_content[:500]
            } for d in issue_docs[:DIAG_ISSUE_SAMPLE]
        ]
        # Sample context chunks
        diag['sample_context_chunks'] = [
            {
                'idx': i,
                'source': c.metadata.get('source'),
                'line_no': c.metadata.get('line_no'),
                'preview': c.page_content[:300]
            } for i, c in enumerate(context_docs[:DIAG_CONTEXT_SAMPLE])
        ]
        fname = f"{run_id}-diag.json" if run_id else f"diag-{int(time.time())}.json"
        path = os.path.join(RUN_DIR, fname)
        os.makedirs(RUN_DIR, exist_ok=True)
        import json
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(diag, f, ensure_ascii=False, indent=2)
        logger.info("Diagnostic written %s (issues=%d chunks=%d)", path, len(issue_docs), len(context_docs))
    except Exception as e:  # pragma: no cover
        logger.warning("Diagnostic write failed: %s", e)


@app.post("/upload")
async def upload(files: List[UploadFile] = File(...), background: BackgroundTasks = None):
    vinfo("/upload files=%d async=%s", len(files) if files else 0, ASYNC_BUILD)
    if not files:
        raise HTTPException(status_code=400, detail="No files provided")

    staged: list[tuple[str,str]] = []  # (temp_path, original_name)
    try:
        for f in files:
            original_name = (f.filename or '').strip() or 'upload.log'
            suffix = os.path.splitext(original_name)[1]
            tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
            data = await f.read()
            tmp.write(data)
            tmp.close()
            staged.append((tmp.name, original_name))
        vdebug("Staged %d temp files", len(staged))
    except Exception as e:
        logger.exception("Failed staging uploads")
        raise HTTPException(status_code=500, detail=f"Failed to stage uploads: {e}")

    temp_paths = [p for p,_ in staged]
    temp_to_orig = {os.path.basename(p): orig for p,orig in staged}

    try:
        docs = load_log_files(temp_paths)
        remapped = 0
        for d in docs:
            base = d.metadata.get('source')
            if base in temp_to_orig:
                d.metadata['source'] = temp_to_orig[base]
                # keep original full temp path separately if needed for debugging
                d.metadata['source_path'] = temp_to_orig[base]
                remapped += 1
        if remapped:
            vdebug("Remapped %d document sources", remapped)
        vdebug("Loaded %d raw line docs", len(docs))
    finally:
        for p,_ in staged:
            try: os.unlink(p)
            except Exception: pass

    issue_docs = extract_issue_docs(docs)
    original_issue_count = len(issue_docs)
    # Build occurrence counts BEFORE dedup using grouping key (or message fallback)
    OCCURRENCE_COUNTS.clear()
    for d in issue_docs:
        try:
            gk = group_key(d.page_content)
        except Exception:
            gk = d.page_content.strip()[:120]
        OCCURRENCE_COUNTS[gk] = OCCURRENCE_COUNTS.get(gk, 0) + 1
    if DEDUP_ERRORS:
        dedup = []
        seen_keys = set()
        for d in issue_docs:
            k = group_key(d.page_content)
            if k in seen_keys:
                continue
            seen_keys.add(k)
            dedup.append(d)
        vinfo("Deduplicated issues: original=%d distinct=%d removed=%d", original_issue_count, len(dedup), original_issue_count - len(dedup))
        issue_docs = dedup
    distinct_issue_count = len(issue_docs)
    by_file: Dict[str, List[Dict[str, Any]]] = {}
    for d in docs:
        by_file.setdefault(d.metadata['source'], []).append({'text': d.page_content, 'line_no': d.metadata['line_no']})

    returned = []
    global RUN_ID
    if TRACE_RUN:
        RUN_ID = str(uuid.uuid4())
    for d in issue_docs:
        src = d.metadata['source']
        full_src = d.metadata.get('source_path') or src
        line_no = d.metadata['line_no']  # FIX: closed bracket
        lines = by_file.get(src, [])
        window = [l for l in lines if line_no-3 <= l['line_no'] <= line_no+2]
        snippet = '\n'.join((('>> ' if l['line_no'] == line_no else '') + l['text']) for l in window)
        eid = str(uuid.uuid4())
        # Determine group key once
        try:
            gk = group_key(d.page_content)
        except Exception:
            gk = d.page_content.strip()[:120]
        occurrences = OCCURRENCE_COUNTS.get(gk, 1)
        entry = {
            'id': eid,
            'severity': d.metadata.get('severity',''),
            'task_name': '',
            'process_name': '',
            'error_type': '',
            'message': d.page_content,
            'run_id': RUN_ID or '',
            'file_id': src,
            'file_path': full_src,
            'line_no': line_no,
            'snippet': snippet,
            'manual_resolved': False,
            'answer_ts': None,
            'group_key': gk,
            'occurrences': occurrences,  # NEW
        }
        if GROUP_ISSUES:
            grp = GROUPS.setdefault(gk, {
                'group_key': gk,
                'issue_ids': [],
                'severity': entry['severity'],
                'rep_id': eid,
                'occurrences': occurrences,  # NEW propagate
            })
            grp['issue_ids'].append(eid)
            if entry['severity'] == 'ERROR' and grp['severity'] != 'ERROR':
                grp['severity'] = 'ERROR'
        ERROR_STORE[eid] = {**entry}
        returned.append(entry)

    context_docs = split_context(docs, chunk_size=CONTEXT_CHUNK_SIZE, chunk_overlap=CONTEXT_CHUNK_OVERLAP)
    vdebug("Split into %d context chunks", len(context_docs))
    if TRACE_RUN and RUN_ID:
        _trace_write_initial(RUN_ID, returned, context_docs)
    if ASYNC_BUILD:
        if background is not None:
            background.add_task(_index_build, issue_docs, context_docs, docs, original_issue_count, distinct_issue_count)
            vdebug("Scheduled background build task")
        else:
            import threading as _t
            _t.Thread(target=_index_build, args=(issue_docs, context_docs, docs, original_issue_count, distinct_issue_count), daemon=True).start()
            vdebug("Spawned background thread for build")
        return {'errors': returned, 'index_building': True, 'qa_ready': False, 'issues_total': original_issue_count, 'issues_distinct': distinct_issue_count}
    else:
        with STATE_LOCK:
            vdebug("Synchronous build path acquiring STATE_LOCK")
            if VECTORSTORES.faiss_store is None:
                VECTORSTORES.build(issue_docs, context_docs)
            else:
                VECTORSTORES.add(issue_docs, context_docs)
            _rebuild_chain()
        vinfo("Synchronous build complete (issues=%d context=%d)", len(issue_docs), len(context_docs))
        _record_ingest_metrics(RUN_ID, source_files=len(issue_docs), docs=issue_docs + context_docs, issue_docs=issue_docs, context_docs=context_docs, incremental=False, original_issue_count=original_issue_count, distinct_issue_count=distinct_issue_count)
        _write_run_diagnostic(RUN_ID, docs, issue_docs, context_docs, incremental=False)
        return {'errors': returned, 'index_building': False, 'qa_ready': True, 'issues_total': original_issue_count, 'issues_distinct': distinct_issue_count}


@app.get("/errors")
async def list_errors(distinct: int | None = Query(None), group_key_filter: str | None = Query(None, alias="group_key")):
    vdebug("/errors distinct=%s group_filter=%s", distinct, group_key_filter)
    if distinct and GROUP_ISSUES:
        out = []
        for gk, grp in GROUPS.items():
            issue_ids = grp['issue_ids']
            resolved_count = 0
            for iid in issue_ids:
                r = ERROR_STORE.get(iid, {})
                if r.get('_answer') or r.get('manual_resolved'):
                    resolved_count += 1
            rep_issue = ERROR_STORE.get(grp['rep_id'])
            out.append({
                'group_key': gk,
                'severity': grp.get('severity'),
                'count': len(issue_ids),  # number of distinct stored issues (always 1 in dedup mode)
                'occurrences': grp.get('occurrences') or OCCURRENCE_COUNTS.get(gk, len(issue_ids)),  # NEW total occurrences
                'resolved_count': resolved_count,
                'message': rep_issue.get('message') if rep_issue else '',
                'representative_id': grp.get('rep_id'),
                'fully_resolved': resolved_count == len(issue_ids)
            })
        return {'groups': out}
    out = []
    for k, r in ERROR_STORE.items():
        if group_key_filter and r.get('group_key') != group_key_filter:
            continue
        resolved = bool(r.get('_answer')) or r.get('manual_resolved')
        out.append({**r, 'answer': r.get('_answer', {}).get('answer') if r.get('_answer') else None, 'resolved': resolved})
    return {'errors': out}


@app.get("/context")
async def get_context(id: str):
    logger.debug("/context id=%s", id)
    row = ERROR_STORE.get(id)
    if not row:
        raise HTTPException(status_code=404, detail='Not found')
    if ENSEMBLE is None:
        raise HTTPException(status_code=503, detail='Retriever not ready')
    query = row['message']
    docs = fetch_sources(ENSEMBLE, query, k=TOP_K)
    ctx_texts = []
    citations = []
    for d in docs:
        ctx_texts.append(d.page_content)
        citations.append({'source': d.metadata.get('source'), 'line_no': d.metadata.get('line_no')})
    return {'query': query, 'context': {'context_text': '\n'.join(ctx_texts), 'citations': citations}, 'snippet': row.get('snippet'), 'line_no': row.get('line_no')}


@app.post("/resolve")
async def resolve(req: ResolveRequest):
    logger.debug("/resolve id=%s", req.id)
    t0 = time.time()  # FIX: correct module usage
    row = ERROR_STORE.get(req.id)
    if not row:
        raise HTTPException(status_code=404, detail='Not found')
    if QA_CHAIN is None:
        raise HTTPException(status_code=503, detail='QA chain not ready (upload first)')
    res = run_qa(QA_CHAIN, row['message'])
    row['_answer'] = res
    row['answer_ts'] = datetime.utcnow().isoformat() + 'Z'
    if TRACE_RUN and RUN_ID:
        _trace_append_resolve(RUN_ID, {
            'type': 'single',
            'id': req.id,
            'question': row['message'],
            'answer': res.get('answer'),
            'sources': res.get('sources'),
            'formatted_sources': res.get('formatted_sources'),
            'elapsed_ms': (time.time() - t0) * 1000.0,
        })
    return {'answer': {'text': res['answer'], 'citations': res.get('sources', [])}}

@app.post('/resolve_batch')
async def resolve_batch(req: ResolveBatchRequest):
    logger.info("/resolve_batch size=%d", len(req.ids))
    if QA_CHAIN is None:
        raise HTTPException(status_code=503, detail='QA chain not ready (upload first)')
    results = []
    for _id in req.ids:
        row = ERROR_STORE.get(_id)
        if not row:
            results.append({'id': _id, 'error': 'not_found'})
            continue
        try:
            res = run_qa(QA_CHAIN, row['message'])
            row['_answer'] = res
            row['answer_ts'] = datetime.utcnow().isoformat() + 'Z'
            results.append({'id': _id, 'ok': True})
            if TRACE_RUN and RUN_ID:
                _trace_append_resolve(RUN_ID, {
                    'type': 'batch',
                    'id': _id,
                    'question': row['message'],
                    'answer': res.get('answer'),
                    'sources': res.get('sources'),
                    'formatted_sources': res.get('formatted_sources'),  # FIX: closed call
                })
        except Exception as e:  # pragma: no cover
            results.append({'id': _id, 'error': str(e)})
    return {'results': results}

@app.post('/mark_resolved')
async def mark_resolved(req: MarkResolvedRequest):
    logger.info("/mark_resolved size=%d state=%s", len(req.ids), req.resolved)
    changed = []
    for _id in req.ids:
        row = ERROR_STORE.get(_id)
        if not row:  # FIX: removed stray comma
            continue
        row['manual_resolved'] = bool(req.resolved)
        if req.resolved and not row.get('answer_ts'):
            row['answer_ts'] = datetime.utcnow().isoformat() + 'Z'
        changed.append(_id)
    return {'updated': changed, 'resolved': req.resolved}


@app.post("/summary")
async def summary(req: SummaryRequest, full: bool = False):
    row = ERROR_STORE.get(req.id)
    if not row:
        raise HTTPException(status_code=404, detail='Not found')
    if ENSEMBLE is None:
        raise HTTPException(status_code=503, detail='Retriever not ready')
    global SUMMARY_CHAIN, EXT_SUMMARY_CHAIN
    if full:
        if EXT_SUMMARY_CHAIN is None:
            EXT_SUMMARY_CHAIN = build_extended_summary_chain(ENSEMBLE, model_name=MODEL_NAME)
        res = run_qa(EXT_SUMMARY_CHAIN, row['message'])
    else:
        if SUMMARY_CHAIN is None:
            SUMMARY_CHAIN = build_summary_chain(ENSEMBLE, model_name=MODEL_NAME)
        res = run_qa(SUMMARY_CHAIN, row['message'])
    row['_summary'] = res['answer']
    return {'summary': res['answer'], 'full': res.get('full_answer'), 'sources': res.get('sources'), 'extended': full}


@app.get("/export")
async def export(format: str = 'json', fmt: str | None = None, ids: str | None = Query(None, description='Comma separated IDs'), lite: bool = False):
    vinfo("/export format=%s lite=%s ids_filter=%s", fmt or format, lite, bool(ids))
    final = fmt or format or 'json'
    id_filter = None
    if ids:
        id_filter = set(i.strip() for i in ids.split(',') if i.strip())
    payload = []
    for k, r in ERROR_STORE.items():
        if id_filter and k not in id_filter:
            continue
        base = {k2: r.get(k2) for k2 in ('id','severity','task_name','process_name','error_type','message','file_id','run_id','line_no','snippet')}
        base['has_answer'] = 1 if r.get('_answer') else 0
        base['manual_resolved'] = 1 if r.get('manual_resolved') else 0
        base['resolved'] = 1 if (r.get('_answer') or r.get('manual_resolved')) else 0
        base['answer_ts'] = r.get('answer_ts')
        payload.append(base)
    if final == 'json':
        return {'errors': payload}
    if final == 'md':
        header = '|Severity|File|Line|Message|Resolved|\n|---|---|---|---|---|'
        rows = []
        for p in payload:
            msg = (p.get('message') or '').replace('|',' ')
            rows.append(f"|{p.get('severity')}|{p.get('file_id')}|{p.get('line_no')}|{msg}|{'Y' if p.get('resolved') else ''}|")
        return {'markdown': header + '\n' + '\n'.join(rows)}
    if final == 'csv':
        import csv, io
        if lite:
            fields = ['id','severity','message','resolved']
        else:
            fields = ['id','severity','file_id','line_no','message','has_answer','manual_resolved','resolved','answer_ts']
        buf = io.StringIO()
        writer = csv.DictWriter(buf, fieldnames=fields)
        writer.writeheader()
        for p in payload:
            writer.writerow({f: p.get(f) for f in fields})
        fname = 'issues_lite.csv' if lite else 'issues.csv'
        return Response(content=buf.getvalue(), media_type='text/csv', headers={'Content-Disposition': f'attachment; filename="{fname}"'})
    if final == 'xlsx':
        try:
            import io
            try:
                from openpyxl import Workbook  # type: ignore
            except ImportError:
                raise HTTPException(status_code=400, detail='openpyxl not installed (pip install openpyxl)')
            wb = Workbook()
            ws = wb.active
            ws.title = 'issues'
            if lite:
                headers_row = ['id','severity','message','resolved']
            else:
                headers_row = ['id','severity','file_id','line_no','message','has_answer','manual_resolved','resolved','answer_ts']
            ws.append(headers_row)
            for p in payload:
                ws.append([p.get(h) for h in headers_row])
            stream = io.BytesIO()
            wb.save(stream)
            fname = 'issues_lite.xlsx' if lite else 'issues.xlsx'
            return Response(content=stream.getvalue(), media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', headers={'Content-Disposition': f'attachment; filename="{fname}"'})
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=f'XLSX export failed: {e}')
    raise HTTPException(status_code=400, detail='Unsupported format')


@app.get("/health")
async def health():
    logger.debug("/health requested")
    return {
        'status': 'ok',
        'errors_cached': len(ERROR_STORE),
        'vector_initialized': VECTORSTORES.faiss_store is not None,
        'retriever_ready': ENSEMBLE is not None,
        'qa_ready': QA_CHAIN is not None,
        'embedding_backend': os.getenv('EMBED_BACKEND', 'hf'),
        'active_llm': MODEL_NAME,  # NEW
    }


@app.get("/ready")
async def ready():
    logger.debug("/ready requested")
    return { 'qa_ready': QA_CHAIN is not None, 'retriever_ready': ENSEMBLE is not None, 'index_building': BUILDING }


@app.get("/stats")
async def stats():
    vdebug("/stats")
    from collections import Counter
    sev_counter = Counter(r.get('severity') for r in ERROR_STORE.values())
    resolved_total = sum(1 for r in ERROR_STORE.values() if r.get('_answer') or r.get('manual_resolved'))
    groups_total = len(GROUPS) if GROUP_ISSUES else 0
    groups_unresolved = 0
    if GROUP_ISSUES:
        for gk, grp in GROUPS.items():
            issue_ids = grp['issue_ids']
            resolved_count = sum(1 for iid in issue_ids if (ERROR_STORE.get(iid, {}).get('_answer') or ERROR_STORE.get(iid, {}).get('manual_resolved')))
            if resolved_count < len(issue_ids):
                groups_unresolved += 1
    index_timing = VECTORSTORES.get_last_timing() if hasattr(VECTORSTORES, 'get_last_timing') else {}
    # Augment timing with live counts if missing
    if isinstance(index_timing, dict):
        index_timing.setdefault('embedded_docs', len(getattr(VECTORSTORES, '_embedded_docs', [])))
        index_timing.setdefault('context_docs', len(getattr(VECTORSTORES, '_context_docs', [])))
        index_timing.setdefault('issue_docs', len(getattr(VECTORSTORES, '_issue_docs', [])))
    bm25_auto_disabled = getattr(VECTORSTORES, 'bm25_auto_disabled', False)
    bm25_auto_threshold = getattr(VECTORSTORES, 'bm25_auto_threshold', 0)
    small_fast = index_timing.get('small_corpus_fast_path') or False
    lazy = getattr(VECTORSTORES, 'lazy_embed', False)
    return {
        'errors_cached': len(ERROR_STORE),
        'severity_counts': dict(sev_counter),
        'vector_initialized': VECTORSTORES.faiss_store is not None,
        'bm25_enabled': VECTORSTORES.bm25_retriever is not None,
        'bm25_auto_disabled': bm25_auto_disabled,
        'bm25_auto_threshold': bm25_auto_threshold,
        'retriever_ready': ENSEMBLE is not None,
        'qa_ready': QA_CHAIN is not None,
        'index_building': BUILDING,
        'resolved_total': resolved_total,
        'embedding_backend': os.getenv('EMBED_BACKEND', 'hf'),
        'last_build_ts': LAST_BUILD_TS,
        'last_build_iso': datetime.utcfromtimestamp(LAST_BUILD_TS).isoformat() + 'Z' if LAST_BUILD_TS else None,
        'groups_total': groups_total,
        'groups_unresolved': groups_unresolved,
        'active_llm': MODEL_NAME,
        'index_timing': index_timing,
        'build_error': LAST_BUILD_ERROR,
        'small_corpus_fast_path': small_fast,
        'lazy_embed': lazy,
    }


@app.post("/reset")
async def reset(confirm: bool = False, preserve_errors: bool = False):
    logger.warning("/reset confirm=%s preserve_errors=%s", confirm, preserve_errors)
    if not confirm:
        raise HTTPException(status_code=400, detail="Set confirm=true to execute reset")
    global VECTORSTORES, ENSEMBLE, QA_CHAIN
    with STATE_LOCK:
        # Remove on-disk indices
        try:
            if os.path.isdir(FAISS_DIR):
                shutil.rmtree(FAISS_DIR, ignore_errors=True)
            if os.path.isfile(BM25_STATE):
                os.remove(BM25_STATE)
        except Exception as e:
            logger.warning(f"Index file removal issue: {e}")
        # Reinit vector stores (will not load anything now)
        VECTORSTORES = VectorStores(embedding_backend=os.getenv("EMBED_BACKEND", "hf"))
        ENSEMBLE = None
        QA_CHAIN = None
        SUMMARY_CHAIN = None
        EXT_SUMMARY_CHAIN = None  # reset extended summary chain
        if not preserve_errors:
            ERROR_STORE.clear()
    return {"status": "reset", "errors_cleared": not preserve_errors}

@app.get('/metrics')
async def metrics(limit: int | None = Query(50, description='Max records to return'), summarize: bool = Query(False, description='Return summary aggregates only')):
    if not METRICS_LOG or not os.path.isfile(METRICS_PATH):
        return {'metrics': []}
    rows = []
    try:
        with open(METRICS_PATH, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                import json
                rows.append(json.loads(line))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f'Metrics read failed: {e}')
    rows = rows[-limit:] if limit else rows
    if summarize and rows:
        import statistics as stats
        total_ms = [r.get('total_ms') for r in rows if isinstance(r.get('total_ms'), (int,float))]
        faiss_ms = [r.get('faiss_ms') for r in rows if isinstance(r.get('faiss_ms'), (int,float))]
        bm25_ms = [r.get('bm25_ms') for r in rows if isinstance(r.get('bm25_ms'), (int,float))]
        summary = {
            'count': len(rows),
            'avg_total_ms': round(stats.mean(total_ms),2) if total_ms else None,
            'avg_faiss_ms': round(stats.mean(faiss_ms),2) if faiss_ms else None,
            'avg_bm25_ms': round(stats.mean(bm25_ms),2) if bm25_ms else None,
            'avg_embedded_docs': round(stats.mean([r.get('embedded_docs',0) for r in rows]),2),
            'bm25_enabled_runs': sum(1 for r in rows if r.get('bm25_enabled')), 
            'bm25_auto_disabled_runs': sum(1 for r in rows if r.get('bm25_auto_disabled')), 
        }
        return {'summary': summary}
    return {'metrics': rows}

# Run with: uvicorn api:app --reload
