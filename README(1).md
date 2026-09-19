# 📚 Grok AI Document Assistant

A simple Streamlit app that lets a user upload a **PDF, DOCX, PPTX, or TXT** file, ask questions about it, and receive answers from **Grok** with document references such as:

- `Source: report.pdf | Page 12`
- `Source: contract.docx | Article 4`
- `Source: presentation.pptx | Slide 8`
- `Source: report.docx | Table 2`

## 1. Files

Put these files in the root of your GitHub repository:

```text
your-repository/
├── App.py
├── requirements.txt
└── README.md
```

## 2. Get your xAI API key

Create an API key from the xAI Console.

The app uses the official xAI API through the OpenAI-compatible Python client and the endpoint:

`https://api.x.ai/v1`

The code currently uses the `grok-4.6` model. If your xAI account has access to a different model, change `MODEL` in `App.py`.

**Important:** An xAI API key is a credential. Do not paste it into `App.py` or commit it to GitHub.

## 3. Deploy on Streamlit Community Cloud

1. Upload `App.py`, `requirements.txt`, and `README.md` to GitHub.
2. Open Streamlit Community Cloud.
3. Create a new app.
4. Select your GitHub repository.
5. Set the main file to `App.py`.
6. Open **Advanced settings / Secrets**.
7. Add:

```toml
XAI_API_KEY = "YOUR_XAI_API_KEY"
```

8. Deploy.

The key is then available to the app through `st.secrets`.

## 4. Run locally

Install the dependencies:

```bash
pip install -r requirements.txt
```

Create:

```text
.streamlit/secrets.toml
```

Put this inside it:

```toml
XAI_API_KEY = "YOUR_XAI_API_KEY"
```

Then run:

```bash
streamlit run App.py
```

## 5. How it works

1. User uploads a file.
2. The app extracts text locally.
3. PDF pages are preserved.
4. DOCX paragraphs, headings, and tables are preserved.
5. PPTX slide numbers are preserved.
6. The app retrieves the most relevant document sections for the question.
7. Only the relevant excerpts are sent to Grok.
8. Grok answers using those excerpts and includes references.

This is a lightweight RAG-style approach and does not require a separate vector database.

## 6. Supported files

| File | Reference style |
|---|---|
| PDF | Page number |
| DOCX | Article / Section / Paragraph / Table |
| PPTX | Slide number |
| TXT | Text file |

## 7. Important limitation

This version extracts text from documents. Scanned/image-only PDFs will need OCR before their text can be searched reliably.

Also, the xAI API is not guaranteed to be free. API access and any credits/charges depend on the current xAI account and pricing. The application itself has no separate AI provider; it only uses your xAI API key.

## 8. Security

Never commit this file to GitHub:

```text
.streamlit/secrets.toml
```

If you use it locally, add it to `.gitignore`.

For Streamlit Community Cloud, enter the secret in the app's Secrets settings instead of putting it in GitHub.
