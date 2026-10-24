# Publishing the public app (Streamlit Community Cloud)

For the team. This puts the chatbot online so assessors can try it without installing anything. It is
free, and it takes about 15 minutes once the GitHub repository is up to date.

## Before you start

- The submission repository on GitHub must be **public**, with the chatbot's contents in `SystemCode/`
  (everything in this folder except `.venv`).
- Copy the folder `SystemCode/.streamlit/` to the **root** of the repository as well, so the root has
  `.streamlit/config.toml`. Community Cloud only reads the theme from the root; without it the app still
  works but uses Streamlit's default red buttons.

## Steps

1. Go to https://share.streamlit.io and sign in with the GitHub account that owns the repository.
2. Click **Create app**, then **Deploy a public app from GitHub**.
3. Fill in:
   - **Repository:** the submission repository
   - **Branch:** `main`
   - **Main file path:** `SystemCode/streamlit_app.py`
   - **App URL:** choose something readable, for example `sg-culture-pass-chatbot`
4. Open **Advanced settings** and choose **Python 3.12**. No secrets are needed.
5. Click **Deploy**. The first build takes a few minutes while it installs `requirements.txt`.
6. Test it: try one of the example requests, then "Something to do with my kids".
7. Paste the app's URL into:
   - the repository README's User Guide section,
   - `SystemCode/README.md` (replace `PUBLIC_APP_URL`),
   - Appendix C of the report (Installation and User Guide).

## Good to know

- **No local LLM online.** Ollama is not available on Community Cloud, so the app uses keyword retrieval
  and template replies there. The report already says the chatbot works this way without Ollama, and
  none of the reasoning uses an LLM.
- **The app sleeps when unused.** Community Cloud puts an app to sleep after a few days without visits.
  Anyone can wake it with one click, which takes about a minute. Open it yourself on the day of
  submission and again before marking if you can.
- **Updating it.** Every push to `main` redeploys the app automatically.
