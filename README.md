# ProjectSilpPrint (starter)

FastAPI-based starter for receipt printing + membership service.

Quick start (development):

1. Copy `.env.example` to `.env` and adjust if needed.
2. Start services:

```bash
docker-compose up
```

3. Open API docs: http://localhost:8000/docs

Simulators:
- `simulators/printer_sim.py` — simple TCP listener to emulate a receipt printer.
- `simulators/pump_sim.py` — simple HTTP helper to POST sample pump transactions to the app.
