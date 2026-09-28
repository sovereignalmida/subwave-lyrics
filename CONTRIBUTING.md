# Contributing

Issues and pull requests are welcome. Keep the application small, dependency-light, and compatible
with SUB/WAVE's public listener API.

```bash
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
python -m unittest discover -s tests -v
```

For a container-level check:

```bash
docker build --target test -t subwave-lyrics:test .
docker run --rm subwave-lyrics:test
```

Never commit station credentials, `.env`, SQLite databases, or copyrighted lyric fixtures.
