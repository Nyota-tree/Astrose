# Astrose

**Write your romance in the stars.**

A small web app that turns your story and words into AI-generated poems and portrait cards. Enter your story, how you see them, and a line for them — get a text-only card right away, then a portrait card when the image is ready.

---

## Features

- **Dual workflow**: Poem first (fast), then portrait image (slower). You see a text-only card immediately and can download it; the portrait card appears when the image is ready.
- **Two card types**: Plain text card (poem only) and portrait card (image + poem), both as downloadable PNGs.
- **Rate limiting**: Per-user (browser fingerprint), per-IP, and global daily cap to prevent abuse and control cost.
- **Session persistence**: Same user returning the same day can land back on the result page with their last cards.

---

## Tech stack

| Role           | Technology        |
|----------------|-------------------|
| Frontend / app | [Streamlit](https://streamlit.io) |
| AI (poem + image) | [Coze](https://www.coze.cn) workflow API |
| Image composition | [Pillow](https://pillow.readthedocs.io) (PIL) |

---

## Project structure

```
Astrose/
├── app.py                      # Single entrypoint
├── requirements.txt            # Python dependencies
├── .streamlit/
│   ├── secrets.toml            # Local secrets (do not commit)
│   └── secrets.toml.example    # Example config
├── assets/                      # Optional: QR images, custom font
└── README.md
```

Generated at runtime (and gitignored): `rate_limits.json`, `last_results.json`.

---

## Quick start

### 1. Clone and install

```bash
git clone https://github.com/<your-username>/<repo-name>.git
cd <repo-name>
pip install -r requirements.txt
```

### 2. Configure secrets

```bash
cp .streamlit/secrets.toml.example .streamlit/secrets.toml
```

Edit `.streamlit/secrets.toml`. You must set:

- `COZE_API_KEY` — Your Coze API key (from [Coze](https://www.coze.cn)).

Optional (defaults are in code):

- `COZE_WORKFLOW_ID_POEM` — Poem workflow ID.
- `COZE_WORKFLOW_ID_IMAGE` — Image workflow ID.

Rate limits (optional, have defaults):

- `MAX_PER_SESSION` — Max generations per user (fingerprint) per day (default: 3).
- `MAX_PER_IP` — Max per IP per day (default: 10).
- `TOTAL_LIMIT` — Global max per day (default: 200).

### 3. Run locally

```bash
streamlit run app.py
```

Open `http://localhost:8501`.

---

## Deploy to Streamlit Cloud

1. Push this repo to GitHub (do **not** commit `secrets.toml`; it is in `.gitignore`).
2. Go to [share.streamlit.io](https://share.streamlit.io), sign in with GitHub, and create a new app from this repository.
3. Set the main file to `app.py`.
4. In the app **Settings → Secrets**, paste your secrets in TOML, for example:

   ```toml
   COZE_API_KEY = "pat_your-real-key"
   MAX_PER_SESSION = 3
   MAX_PER_IP = 10
   TOTAL_LIMIT = 200
   ```

5. Deploy. The app will use Streamlit Cloud’s environment; `rate_limits.json` and `last_results.json` are ephemeral (reset on restart unless you add external storage).

---

## Security and abuse prevention

- **Secrets**: API key and workflow IDs are read only from `st.secrets` (e.g. `.streamlit/secrets.toml` or Streamlit Cloud Secrets). They are not hardcoded.
- **Git**: `.gitignore` includes `.streamlit/secrets.toml`, `rate_limits.json`, and `last_results.json` so they are not committed.
- **Rate limiting**: Three layers — browser fingerprint (primary), IP (fallback), and a global daily cap — with configurable limits above.

---

## Coze workflow parameters

The app sends these parameter names to your Coze workflow “Start” node:

- `input` — Your story with them.
- `image` — How you see them (for the portrait).
- `telling` — One sentence you want to say to them.
- `gender` — Their gender.

Poem workflow is expected to return `data.poem`; image workflow, `data.image_url`. If your workflows use different keys, adjust `call_coze_workflow_poem` and `call_coze_workflow_image` in `app.py`.

---

## License

MIT (or specify your license).
