from pathlib import Path
from typing import List, Tuple
from langchain_core.documents import Document
import re
import os
from utils.logger import get_logger
from concurrent.futures import ThreadPoolExecutor, as_completed
import time

logger = get_logger("loaders")

SEVERITY_RE = re.compile(r"\b(ERROR|WARN|WARNING|FATAL|INFO|DEBUG)\b", re.IGNORECASE)


def _process_single_file(path: Path, prefilter: bool, ctx_window: int) -> List[Document]:
    docs: List[Document] = []
    if not path.exists() or not path.is_file():
        logger.warning("Missing file: %s", path)
        return docs
    try:
        with path.open('r', encoding='utf-8', errors='replace') as fh:
            lines = fh.readlines()
    except Exception as e:  # pragma: no cover
        logger.warning("Failed reading %s: %s", path, e)
        return docs
    total_lines = len(lines)
    keep_indices = None
    if prefilter:
        error_indices = []
        for i, line in enumerate(lines):
            m = SEVERITY_RE.search(line)
            if not m:
                continue
            sev = m.group(1).upper()
            if sev == 'WARNING':
                sev = 'WARN'
            if sev == 'ERROR':
                error_indices.append(i)
        if not error_indices:
            return docs  # no ERROR lines, skip entire file
        keep = set()
        for idx in error_indices:
            for j in range(idx - ctx_window, idx + ctx_window + 1):
                if 0 <= j < total_lines:
                    keep.add(j)
        keep_indices = keep
    for i, line in enumerate(lines):
        if keep_indices is not None and i not in keep_indices:
            continue
        m = SEVERITY_RE.search(line)
        sev = ''
        if m:
            sev = m.group(1).upper()
            if sev == 'WARNING':
                sev = 'WARN'
        meta = {
            'source': str(path.name),
            'source_path': str(path.resolve()),
            'line_no': i + 1,
            'severity': sev,
        }
        docs.append(Document(page_content=line.strip(), metadata=meta))
    return docs


def load_log_files(paths: List[str]) -> List[Document]:
    prefilter = os.getenv('PREFILTER_ERRORS', '1') == '1'  # enable by default for speed on large files
    ctx_window = int(os.getenv('PREFILTER_WINDOW', '2'))  # lines before & after each ERROR line
    t0 = time.time()
    docs: List[Document] = []
    path_objs = [Path(p) for p in paths]
    # Thread pool for I/O bound reads
    max_workers = min(len(path_objs), max(4, os.cpu_count() or 4))
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futures = {ex.submit(_process_single_file, p, prefilter, ctx_window): p for p in path_objs}
        for fut in as_completed(futures):
            part = fut.result() or []
            docs.extend(part)
    elapsed = (time.time() - t0) * 1000
    logger.info("Loaded documents=%d files=%d prefilter=%s elapsed_ms=%.1f workers=%d", len(docs), len(paths), prefilter, elapsed, max_workers)
    return docs


def extract_issue_docs(docs: List[Document]) -> List[Document]:
    issues = [d for d in docs if d.metadata.get('severity') == 'ERROR']
    logger.info("Issue docs (ERROR)=%d", len(issues))
    return issues
