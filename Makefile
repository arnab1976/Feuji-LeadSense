.PHONY: help install api worker seed test fmt up down web

help:
	@echo "install   Install backend and frontend dependencies"
	@echo "api       Run the FastAPI server on :8000"
	@echo "worker    Run the Celery worker"
	@echo "seed      Create tables and load demo data"
	@echo "web       Run the Next.js frontend on :3000"
	@echo "test      Run the backend test suite"
	@echo "up/down   Start or stop the full docker-compose stack"

install:
	cd backend && python -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt
	cd frontend && npm install

api:
	cd backend && uvicorn app.main:app --reload --port 8000

worker:
	cd backend && celery -A app.workers.celery_app.celery worker -l info -Q default,extraction,delivery

seed:
	cd backend && python -m app.db.seed

web:
	cd frontend && npm run dev

test:
	cd backend && pytest -q

fmt:
	cd backend && ruff check --fix . && ruff format .

up:
	docker compose up --build

down:
	docker compose down -v
