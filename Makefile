.PHONY: install dev api web doctor test eval seed demo lint db-dedupe db-dedupe-apply

install:
	cd api && uv sync
	cd web && npm install

api:
	cd api && uv run uvicorn app.main:app --reload --port 8000

web:
	cd web && npm run dev

dev:
	@echo "Run 'make api' and 'make web' in two terminals."

# Resolve every role against the live OpenRouter catalogue, check capabilities and
# Atlas reachability, print the table. Fails loudly rather than at request time.
doctor:
	cd api && uv run python -m app.doctor

test:
	cd api && uv run pytest -q

lint:
	cd api && uv run ruff check app tests

# Comparator regression: MATERIAL recall must stay at 1.0. Runs off recorded
# completions, so it costs nothing and works offline.
eval:
	cd api && uv run python -m app.evalset.harness

# Report duplicate runs left behind by repeated development runs. Read-only by default;
# `make db-dedupe-apply` is the one command in this project that deletes history.
db-dedupe:
	cd api && uv run python -m app.store.maintenance

db-dedupe-apply:
	cd api && uv run python -m app.store.maintenance --apply

# Load the recorded demo traces into Mongo.
seed:
	cd api && uv run python -m app.demo.seed

# Replay all five demo deliberations with no OpenRouter key.
demo: seed
	cd api && DELIBERATOR_REPLAY=1 uv run uvicorn app.main:app --port 8000
