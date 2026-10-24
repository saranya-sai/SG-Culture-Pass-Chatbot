"""Entry point for Streamlit Community Cloud.

Community Cloud looks for requirements.txt next to the entry point, so this small launcher sits beside it
and runs the real app in app/app.py. Locally, `streamlit run app/app.py` and `streamlit run streamlit_app.py`
do the same thing.
"""
import runpy
from pathlib import Path

runpy.run_path(str(Path(__file__).resolve().parent / "app" / "app.py"), run_name="__main__")
