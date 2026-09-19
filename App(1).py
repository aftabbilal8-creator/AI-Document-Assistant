import io
import os
import re

import streamlit as st
import fitz  # PyMuPDF
from docx import Document
from pptx import Presentation
from openai import OpenAI


# ---------------------------------------------------------
# APP SETTINGS
# ---------------------------------------------------------

st.set_page_config(
    page_title="Grok AI Document Assistant",
    page_icon="📚",
    layout="wide"
)

MODEL = "grok-4.6"
MAX_CHUNK_CHARS = 9000
TOP_CHUNKS = 8


# ---------------------------------------------------------
# GET GROK API KEY
# ---------------------------------------------------------

def get_api_key():
    try:
        return st.secrets["GROK_API_KEY"]
    except Exception:
        return os.getenv("GROK_API_KEY")


# ---------------------------------------------------------
# TEXT CLEANING
# ---------------------------------------------------------

def clean_text(text):
    return re.sub(r"\s+", " ", text).strip()


# ---------------------------------------------------------
# CREATE DOCUMENT CHUNKS
# ---------------------------------------------------------

def chunk_text(text, filename, location):
    text = clean_text(text)

    if not text:
        return []

    chunks = []

    for i in range(0, len(text), MAX_CHUNK_CHARS):
        chunks.append({
            "filename": filename,
            "location": location,
            "text": text[i:i + MAX_CHUNK_CHARS]
        })

    return chunks


# ---------------------------------------------------------
# PDF READER
# ---------------------------------------------------------

def read_pdf(data, filename):
    chunks = []

    pdf = fitz.open(stream=data, filetype="pdf")

    for page_number, page in enumerate(pdf, start=1):

        text = page.get_text("text")

        page_chunks = chunk_text(
            text,
            filename,
            f"Page {page_number}"
        )

        chunks.extend(page_chunks)

    pdf.close()

    return chunks


# ---------------------------------------------------------
# DOCX READER
# ---------------------------------------------------------

def read_docx(data, filename):
    document = Document(io.BytesIO(data))

    chunks = []

    current_section = "Document"

    paragraphs = []

    for number, paragraph in enumerate(
        document.paragraphs,
        start=1
    ):

        text = clean_text(paragraph.text)

        if not text:
            continue

        # Detect Article / Section / Chapter
        if re.search(
            r"\b(article|section|chapter)\b",
            text,
            re.IGNORECASE
        ):
            if paragraphs:
                chunks.extend(
                    chunk_text(
                        "\n".join(paragraphs),
                        filename,
                        current_section
                    )
                )

                paragraphs = []

            current_section = text[:150]

        paragraphs.append(
            f"Paragraph {number}: {text}"
        )

    if paragraphs:
        chunks.extend(
            chunk_text(
                "\n".join(paragraphs),
                filename,
                current_section
            )
        )

    # Read tables
    for table_number, table in enumerate(
        document.tables,
        start=1
    ):

        rows = []

        for row in table.rows:

            row_text = " | ".join(
                clean_text(cell.text)
                for cell in row.cells
            )

            rows.append(row_text)

        chunks.extend(
            chunk_text(
                "\n".join(rows),
                filename,
                f"Table {table_number}"
            )
        )

    return chunks


# ---------------------------------------------------------
# POWERPOINT READER
# ---------------------------------------------------------

def read_pptx(data, filename):
    presentation = Presentation(
        io.BytesIO(data)
    )

    chunks = []

    for slide_number, slide in enumerate(
        presentation.slides,
        start=1
    ):

        texts = []

        for shape in slide.shapes:

            if hasattr(shape, "text"):

                text = clean_text(shape.text)

                if text:
                    texts.append(text)

        chunks.extend(
            chunk_text(
                "\n".join(texts),
                filename,
                f"Slide {slide_number}"
            )
        )

    return chunks


# ---------------------------------------------------------
# TEXT FILE READER
# ---------------------------------------------------------

def read_txt(data, filename):

    text = data.decode(
        "utf-8",
        errors="ignore"
    )

    return chunk_text(
        text,
        filename,
        "Text file"
    )


# ---------------------------------------------------------
# MAIN FILE READER
# ---------------------------------------------------------

def read_file(uploaded_file):

    data = uploaded_file.getvalue()

    filename = uploaded_file.name

    lower_name = filename.lower()

    if lower_name.endswith(".pdf"):

        return read_pdf(
            data,
            filename
        )

    elif lower_name.endswith(".docx"):

        return read_docx(
            data,
            filename
        )

    elif lower_name.endswith(".pptx"):

        return read_pptx(
            data,
            filename
        )

    elif lower_name.endswith(".txt"):

        return read_txt(
            data,
            filename
        )

    else:

        raise ValueError(
            "Unsupported file type."
        )


# ---------------------------------------------------------
# FIND RELEVANT DOCUMENT SECTIONS
# ---------------------------------------------------------

def retrieve_relevant_chunks(
    chunks,
    question,
    limit=TOP_CHUNKS
):

    question_words = set(
        re.findall(
            r"\b[a-zA-Z0-9]{3,}\b",
            question.lower()
        )
    )

    scored_chunks = []

    for chunk in chunks:

        document_words = set(
            re.findall(
                r"\b[a-zA-Z0-9]{3,}\b",
                chunk["text"].lower()
            )
        )

        score = len(
            question_words &
            document_words
        )

        scored_chunks.append(
            (score, chunk)
        )

    scored_chunks.sort(
        key=lambda x: x[0],
        reverse=True
    )

    relevant = [
        chunk
        for score, chunk in scored_chunks[:limit]
        if score > 0
    ]

    if not relevant:
        relevant = chunks[:limit]

    return relevant


# ---------------------------------------------------------
# ASK GROK
# ---------------------------------------------------------

def ask_grok(question, relevant_chunks):

    api_key = get_api_key()

    if not api_key:

        raise RuntimeError(
            "GROK_API_KEY is missing. "
            "Add GROK_API_KEY in Streamlit Secrets."
        )

    client = OpenAI(
        api_key=api_key,
        base_url="https://api.x.ai/v1"
    )

    document_context = ""

    for chunk in relevant_chunks:

        document_context += (
            f"\n\n"
            f"[REFERENCE: {chunk['filename']} "
            f"| {chunk['location']}]\n"
            f"{chunk['text']}"
        )

    system_prompt = """
You are an AI document assistant.

Answer the user's question using ONLY the
provided document information.

Do not invent information.

If the answer cannot be found in the
provided document, clearly say:

"I could not find this information in the provided file."

IMPORTANT:
Always provide references for factual answers.

For PDF use:

[Source: filename.pdf | Page X]

For DOCX use:

[Source: filename.docx | Article X]

or:

[Source: filename.docx | Section X]

or:

[Source: filename.docx | Paragraph X]

For PowerPoint use:

[Source: filename.pptx | Slide X]

Never invent a page number, article number,
section number, or slide number.

Give clear and professional answers.

If the question asks for multiple items,
use bullet points or a numbered list.
"""

    user_prompt = f"""
USER QUESTION:

{question}


DOCUMENT INFORMATION:

{document_context}
"""

    response = client.responses.create(

        model=MODEL,

        instructions=system_prompt,

        input=user_prompt
    )

    return response.output_text


# ---------------------------------------------------------
# USER INTERFACE
# ---------------------------------------------------------

st.title("📚 Grok AI Document Assistant")

st.write(
    "Upload a document and ask questions about "
    "its contents."
)

st.caption(
    "Answers are generated from the uploaded "
    "document and include file references."
)


# ---------------------------------------------------------
# SIDEBAR
# ---------------------------------------------------------

with st.sidebar:

    st.header("⚙️ Settings")

    st.write(
        f"AI Model: `{MODEL}`"
    )

    st.write(
        "Supported files:"
    )

    st.write(
        "• PDF\n"
        "• DOCX\n"
        "• PPTX\n"
        "• TXT"
    )

    st.info(
        "Your GROK_API_KEY should be stored "
        "in Streamlit Secrets."
    )


# ---------------------------------------------------------
# FILE UPLOAD
# ---------------------------------------------------------

uploaded_file = st.file_uploader(

    "📁 Upload your document",

    type=[
        "pdf",
        "docx",
        "pptx",
        "txt"
    ]
)


if uploaded_file:

    # Read new file only
    if (
        "file_name" not in st.session_state
        or
        st.session_state.file_name
        != uploaded_file.name
    ):

        try:

            with st.spinner(
                "Reading your document..."
            ):

                chunks = read_file(
                    uploaded_file
                )

                st.session_state.chunks = chunks

                st.session_state.file_name = (
                    uploaded_file.name
                )

            st.success(
                f"Successfully loaded "
                f"**{uploaded_file.name}**"
            )

            st.info(
                f"Document sections indexed: "
                f"{len(chunks)}"
            )

        except Exception as error:

            st.error(
                f"Could not read the file: {error}"
            )

            st.stop()


    # -----------------------------------------------------
    # QUESTION
    # -----------------------------------------------------

    question = st.text_area(

        "💬 Ask a question about your document",

        placeholder=(
            "Example:\n"
            "What are the requirements mentioned "
            "in Article 4?"
        ),

        height=120
    )


    # -----------------------------------------------------
    # ASK BUTTON
    # -----------------------------------------------------

    if st.button(
        "🔎 Ask Grok",
        type="primary",
        disabled=not question.strip()
    ):

        try:

            with st.spinner(
                "Grok is analyzing the document..."
            ):

                relevant_chunks = (
                    retrieve_relevant_chunks(
                        st.session_state.chunks,
                        question
                    )
                )

                answer = ask_grok(
                    question,
                    relevant_chunks
                )

            st.subheader("🤖 Answer")

            st.markdown(answer)


            # -------------------------------------------------
            # REFERENCES
            # -------------------------------------------------

            with st.expander(
                "📖 Document references used"
            ):

                for chunk in relevant_chunks:

                    st.markdown(
                        f"**{chunk['filename']}** "
                        f"— "
                        f"**{chunk['location']}**"
                    )


        except Exception as error:

            st.error(
                f"Grok API Error: {error}"
            )


else:

    st.info(
        "👆 Upload a PDF, DOCX, PPTX, or TXT file "
        "to start."
    )
