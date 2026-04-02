# Technology Stack & Constraints

- **Language Environment:** Python 3.8+ required.
- **Dependencies:** Strict standard-library ONLY. Core text logic is limited to pure modules such as `re`, `datetime`, `typing`, and `dataclasses`; the CLI layer may additionally use `argparse`, `json`, `os`, `pathlib`, `sys`, `urllib.request`, and `urllib.error`.
- **Packaging:** Standard `setuptools` distribution via `setup.py`.
- **Command-Line Interface:** Entry points strictly mapped via `console_scripts` in setup.
- **Limits:** In-memory string manipulation bounds the application. Extreme file sizes dictate future architectural shifts.
- **Module Structure:** The CLI owns I/O and external API access; `talk_to_blog.converter` remains a pure planning/composition module.
