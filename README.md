# Color Dice Rigged Backend

FastAPI backend that farms `online-dice.com` tokens 24/7 and serves them
to the Chrome extension via REST API.

## One-click deploy to Render

[![Deploy to Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com/deploy)

## Endpoints

- `GET /api/health` — service health, no auth
- `GET /api/find?count=N&colors=A,B,C,...` — get a token matching colors (Bearer auth)
- `GET /api/stats` — index size + coverage % per dice count (Bearer auth)

## Environment

- `CDR_API_KEY` — Bearer token clients must send. Generated automatically on Render.
- `CDR_DB_PATH` — SQLite file path. Default: `/tmp/cdr.sqlite`
- `PORT` — listen port (set automatically by Render)

## Local run

```bash
pip install -r requirements.txt
CDR_API_KEY=secret CDR_DB_PATH=./cdr.sqlite python server.py
```

See **README_PL.md** for full Polish step-by-step deployment instructions.
