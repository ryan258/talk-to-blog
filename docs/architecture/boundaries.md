# System Boundaries & Contracts

- **CLI-Core Seam:** `cli.py` owns filesystem, environment, and network I/O; `converter.py` performs pure transcript planning and blog composition.
- **Contract: IO:** CLI guarantees valid UTF-8 transcript input and AI body responses; Core guarantees structured prompt payloads and formatted Markdown output.
- **Contract: Errors:** CLI owns all `OSError`, `IOError`, HTTP, and API-shape handling before data crosses into the pure conversion layer.
- **Contract: Parsers:** Format-specific parsers (`parse_srt`, `parse_vtt`) expect raw strings and guarantee cleaned plain text strings.
- **Seals:** Do not import system I/O utilities (`sys`, `argparse`, `urllib`, `os`) into `converter.py`.
- **Side-Effects Restriction:** `converter.py` is forbidden from interacting with the filesystem, environment, network, or stdout.
