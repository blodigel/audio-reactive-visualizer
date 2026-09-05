.PHONY: dev test lock docker run

dev:
	uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8080

test:
	uv run pytest -q

lock:
	uv lock

docker:
	docker compose up --build

run:
	docker compose up --build
