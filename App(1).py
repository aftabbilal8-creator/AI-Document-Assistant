import io
import os
import re
import streamlit as st
import fitz  # PyMuPDF
from docx import Document
from pptx import Presentation
from openai import OpenAI

st.set_page_config(page_title="Grok File Assistant", page_icon="📚", layout="wide")

MODEL = "grok-4.6"
MAX_CHUNK_CHARS = 9000
TOP_CHUNKS = 8

def get_api_key():
    try:
        return st.secrets["GROK_API_KEY"]
    except Exception:
        return os.getenv("GROK_API_KEY")
def clean(text):
    return re.sub(r"\s+", " ", text).strip()

def chunk_text(text, source, location, chunk_size=MAX_CHUNK_CHARS):
    text = clean(text)
    if not text:
        return []
    chunks = []
    for i in range(0, len(text), chunk_size):
        part = text[i:i + chunk_size]
        chunks.append({
            "source": source,
            "location": location,
            "text": part
        })
    return chunks

def extract_pdf(data, filename):
    chunks = []
    doc = fitz.open(stream=data, filetype="pdf")
    for page_no, page in enumerate(doc, start=1):
        text = page.get_text("text")
        chunks.extend(chunk_text(text, filename, f"Page {page_no}"))
    return chunks

def extract_docx(data, filename):
    doc = Document(io.BytesIO(data))
    chunks = []
    article = "Document body"
    buffer = []

    def flush():
        nonlocal buffer
        if buffer:
            chunks.extend(chunk_text("\n".join(buffer), filename, article))
            buffer = []

    for n, p in enumerate(doc.paragraphs, start=1):
        text = clean(p.text)
        if not text:
            continue
        # Treat headings containing Article/Section/Chapter as useful references.
        if re.search(r"\b(article|section|chapter)\b", text, re.I):
            flush()
            article = text[:160]
        buffer.append(f"Paragraph {n}: {text}")

    flush()

    # Tables are common in reports/contracts.
    for t_no, table in enumerate(doc.tables, start=1):
        rows = []
        for row in table.rows:
            rows.append(" | ".join(clean(cell.text) for cell in row.cells))
        chunks.extend(chunk_text("\n".join(rows), filename, f"Table {t_no}"))

    return chunks

def extract_pptx(data, filename):
    prs = Presentation(io.BytesIO(data))
    chunks = []
    for slide_no, slide in enumerate(prs.slides, start=1):
        texts = []
        for shape in slide.shapes:
            if hasattr(shape, "text") and shape.text.strip():
                texts.append(clean(shape.text))
        chunks.extend(chunk_text("\n".join(texts), filename, f"Slide {slide_no}"))
    return chunks

def extract_txt(data, filename):
    text = data.decode("utf-8", errors="ignore")
    return chunk_text(text, filename, "Text file")

def extract_file(uploaded):
    data = uploaded.getvalue()
    name = uploaded.name.lower()
    if name.endswith(".pdf"):
        return extract_pdf(data, uploaded.name)
    if name.endswith(".docx"):
        return extract_docx(data, uploaded.name)
    if name.endswith(".pptx"):
        return extract_pptx(data, uploaded.name)
    if name.endswith(".txt"):
        return extract_txt(data, uploaded.name)
    raise ValueError("Unsupported file type.")

def retrieve(chunks, question, limit=TOP_CHUNKS):
    # Lightweight local retrieval: score chunks by words from the question.
    words = set(re.findall(r"\b[a-zA-Z0-9]{3,}\b", question.lower()))
    scored = []
    for c in chunks:
        text_words = set(re.findall(r"\b[a-zA-Z0-9]{3,}\b", c["text"].lower()))
        score = len(words & text_words)
        scored.append((score, c))
    scored.sort(key=lambda x: x[0], reverse=True)
    useful = [c for score, c in scored[:limit] if score > 0]
    return useful or chunks[:limit]

def ask_grok(question, contexts):
    api_key = get_api_key()
    if not api_key:
        raise RuntimeError(
            "XAI_API_KEY is missing. Add it to Streamlit Secrets as XAI_API_KEY."
        )

    client = OpenAI(api_key=api_key, base_url="https://api.x.ai/v1")

    context_text = "\n\n".join(
        f"[REFERENCE: {c['source']} — {c['location']}]\n{c['text']}"
        for c in contexts
    )

    system = """You are a document question-answering assistant.
Answer ONLY from the supplied document excerpts.
If the answer is not supported by the excerpts, say: "I could not find this in the provided file."
Always cite the source after important factual statements using exactly:
[Source: filename | Page X]
or
[Source: filename | Article/Section/Paragraph/Table X]
For PDF files, prefer the page number. Never invent a page, article, section, or paragraph number.
Give a clear, direct answer. If useful, use bullets."""

    user = f"""QUESTION:
{question}

DOCUMENT EXCERPTS:
{context_text}"""

    response = client.responses.create(
        model=MODEL,
        instructions=system,
        input=user,
    )
    return response.output_text

st.title("📚 Grok AI Document Assistant")
st.caption("Upload a document, ask questions, and get answers with file references.")

with st.sidebar:
    st.header("Settings")
    st.write(f"Model: `{MODEL}`")
    st.info("Supported: PDF, DOCX, PPTX, TXT")
    st.caption("Your xAI API key stays in Streamlit Secrets and should never be committed to GitHub.")

uploaded = st.file_uploader(
    "Upload your file",
    type=["pdf", "docx", "pptx", "txt"],
    help="PDF, Word, PowerPoint, or text files"
)

if uploaded:
    if "file_name" not in st.session_state or st.session_state.file_name != uploaded.name:
        try:
            with st.spinner("Reading document..."):
                st.session_state.chunks = extract_file(uploaded)
                st.session_state.file_name = uploaded.name
            st.success(f"Loaded {uploaded.name} — {len(st.session_state.chunks)} document sections indexed.")
        except Exception as e:
            st.error(f"Could not read this file: {e}")
            st.stop()

    question = st.text_area(
        "Ask a question about the file",
        placeholder="Example: What is the main requirement in Article 4?",
        height=100,
    )

    if st.button("🔎 Ask Grok", type="primary", disabled=not question.strip()):
        try:
            with st.spinner("Analyzing the document..."):
                contexts = retrieve(st.session_state.chunks, question)
                answer = ask_grok(question, contexts)

            st.subheader("Answer")
            st.markdown(answer)

            with st.expander("References used"):
                for c in contexts:
                    st.markdown(f"**{c['source']} — {c['location']}**")
        except Exception as e:
            st.error(f"Grok API error: {e}")

else:
    st.info("Upload a file to begin.")
