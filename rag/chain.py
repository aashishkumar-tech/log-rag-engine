from typing import List, Dict, Any
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.documents import Document
import os
from utils.logger import get_logger

logger = get_logger("chain")

# Prefer new langchain_openai package
try:  # pragma: no cover
    from langchain_openai import ChatOpenAI, AzureChatOpenAI
except ImportError:  # fallback (deprecated path)
    from langchain_community.chat_models import ChatOpenAI  # type: ignore
    AzureChatOpenAI = None  # type: ignore

# Import Groq
try:
    from langchain_groq import ChatGroq
except ImportError:
    ChatGroq = None  # type: ignore

from langchain.chains import RetrievalQA

# UPDATED RESOLUTION PROMPT: only Fix and Next sections (2-3 lines each, max 6 lines total)
PROMPT_TMPL = """You are a remediation assistant for application logs.
Given an error line and retrieved context, output ONLY two sections:
Fix: concrete immediate remediation steps (2-3 short lines, imperative, actionable)
Next: follow-up / prevention / verification steps (2-3 short lines)
Rules:
- Output ONLY these sections starting with 'Fix:' then 'Next:'
- No other headings, no apologies, no chit-chat
- Each line <=160 chars; avoid repeating full raw log line
- Be specific (commands, config keys, checks) without sensitive data
Error / Question:
{question}

Context:
{context}
"""

# SUMMARY PROMPT: snapshot only (no remediation)
SUMMARY_PROMPT_TMPL = """You summarize the current incident from logs.
Only describe what happened, probable cause, impact, scope. No remediation or next steps.
Format lines (omit if unknown):
Event: ...
Cause: ...
Impact: ...
Scope: ...
Max 7 lines total, each <=160 chars, no fix instructions.

Error / Question:
{question}

Context:
{context}
"""

# NEW: EXTENDED SUMMARY PROMPT (richer detail for full toggle)
EXTENDED_SUMMARY_PROMPT_TMPL = """You produce a richer incident narrative from logs.
Provide concise multi-line breakdown (max 12 lines, each <=170 chars):
Event: single sentence of what occurred
Cause: likely root cause (include key component/path)
Impact: affected system/users & severity
Scope: breadth (# occurrences / modules if inferable)
Timeline: earliest -> latest notable timestamps (compact)
Evidence: 1-2 critical log cues (no raw stack trace spam)
Gaps: unknowns needing further investigation (optional)
No remediation/fix steps. Avoid repetition. Do not exceed 12 lines.

Error / Question:
{question}

Context:
{context}
"""

MAX_RESOLUTION_LINES = 6  # Fix + Next (up to 3 each)
MAX_SUMMARY_LINES = 7

def _post_trim_answer(text: str, max_lines: int) -> str:
    if not text:
        return ""
    lines = [l.strip() for l in text.strip().splitlines() if l.strip()]
    return "\n".join(lines[:max_lines])

def _build_llm(model_name: str, temperature: float):
    # Priority 1: Groq (if GROQ_API_KEY is set)
    groq_api_key = os.getenv("GROQ_API_KEY")
    if groq_api_key:
        if not ChatGroq:
            raise ImportError("langchain-groq not installed. Install: pip install langchain-groq")
        
        groq_model = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
        logger.info("Building ChatGroq model=%s temp=%.2f", groq_model, temperature)
        return ChatGroq(
            groq_api_key=groq_api_key,
            model_name=groq_model,
            temperature=temperature,
        )
    
    # Priority 2: Azure OpenAI (if AZURE_OPENAI_API_KEY is set)
    if os.getenv("AZURE_OPENAI_API_KEY") and AzureChatOpenAI:
        logger.info("Building AzureChatOpenAI model=%s temp=%.2f", os.getenv("AZURE_OPENAI_DEPLOYMENT", model_name), temperature)
        return AzureChatOpenAI(
            azure_deployment=os.getenv("AZURE_OPENAI_DEPLOYMENT", model_name),
            openai_api_key=os.getenv("AZURE_OPENAI_API_KEY"),
            azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
            api_version=os.getenv("AZURE_API_VERSION", "2024-02-01"),
            temperature=temperature,
        )
    
    # Priority 3: Standard OpenAI (fallback)
    logger.info("Building ChatOpenAI model=%s temp=%.2f", model_name, temperature)
    return ChatOpenAI(model_name=model_name, temperature=temperature)

class QAWrapper:
    """Lightweight callable wrapper to attach metadata (summary_mode) without mutating RetrievalQA (pydantic)."""
    def __init__(self, chain: RetrievalQA, summary_mode: bool, max_lines_override: int | None = None):
        self._inner = chain
        self.summary_mode = summary_mode
        self.max_lines_override = max_lines_override
    def __call__(self, *args, **kwargs):
        return self._inner(*args, **kwargs)
    @property
    def retriever(self):  # expose retriever if ever needed
        return getattr(self._inner, 'retriever', None)

def build_chain(retriever, model_name: str = "gpt-3.5-turbo", temperature: float = 0.2):
    logger.debug("build_chain called model=%s", model_name)
    llm = _build_llm(model_name, temperature)
    prompt = ChatPromptTemplate.from_template(PROMPT_TMPL)
    inner = RetrievalQA.from_chain_type(
        llm=llm,
        retriever=retriever,
        chain_type="stuff",
        chain_type_kwargs={"prompt": prompt},
        return_source_documents=True,
    )
    logger.info("Resolution chain constructed")
    return QAWrapper(inner, summary_mode=False)

def build_summary_chain(retriever, model_name: str = "gpt-3.5-turbo", temperature: float = 0.2):
    logger.debug("build_summary_chain model=%s", model_name)
    llm = _build_llm(model_name, temperature)
    prompt = ChatPromptTemplate.from_template(SUMMARY_PROMPT_TMPL)
    inner = RetrievalQA.from_chain_type(
        llm=llm,
        retriever=retriever,
        chain_type="stuff",
        chain_type_kwargs={"prompt": prompt},
        return_source_documents=True,
    )
    logger.info("Summary chain constructed")
    return QAWrapper(inner, summary_mode=True, max_lines_override=4)

# NEW extended summary chain

def build_extended_summary_chain(retriever, model_name: str = "gpt-3.5-turbo", temperature: float = 0.2):
    logger.debug("build_extended_summary_chain model=%s", model_name)
    llm = _build_llm(model_name, temperature)
    prompt = ChatPromptTemplate.from_template(EXTENDED_SUMMARY_PROMPT_TMPL)
    inner = RetrievalQA.from_chain_type(
        llm=llm,
        retriever=retriever,
        chain_type="stuff",
        chain_type_kwargs={"prompt": prompt},
        return_source_documents=True,
    )
    logger.info("Extended summary chain constructed")
    return QAWrapper(inner, summary_mode=True, max_lines_override=12)

def format_sources(docs: List[Document]) -> str:
    out = []
    for d in docs:
        out.append(f"[{d.metadata.get('source')}:{d.metadata.get('line_no')}] {d.page_content[:180]}")
    return "\n".join(out)

def run_qa(chain, question: str) -> Dict[str, Any]:
    logger.debug("run_qa invoked query_len=%d", len(question))
    resp = chain({"query": question})  # chain is QAWrapper (callable)
    full_answer = resp.get('result', '') or resp.get('answer', '')
    summary_mode = getattr(chain, 'summary_mode', False)
    override = getattr(chain, 'max_lines_override', None)
    max_lines = override if override is not None else (MAX_SUMMARY_LINES if summary_mode else MAX_RESOLUTION_LINES)
    trimmed = _post_trim_answer(full_answer, max_lines)
    sources = resp.get('source_documents', []) or []
    logger.info(
        "run_qa completed mode=%s sources=%d full_chars=%d lines=%d",
        'summary' if summary_mode else 'resolution',
        len(sources),
        len(full_answer),
        trimmed.count('\n') + (1 if trimmed else 0)
    )
    return {
        'answer': trimmed,
        'full_answer': full_answer,
        'sources': [
            {'source': d.metadata.get('source'), 'line_no': d.metadata.get('line_no')}
            for d in sources
        ],
        'formatted_sources': format_sources(sources)
    }