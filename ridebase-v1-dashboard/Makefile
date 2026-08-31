.PHONY: help install backend frontend dev test build lint typecheck docker smoke clean

API ?= http://localhost:8000

help:
	@echo "make install     - backend venv deps + frontend npm deps"
	@echo "make dev         - run backend (:8000) and frontend (:3000) together"
	@echo "make backend     - run FastAPI (uvicorn --reload) on :8000"
	@echo "make frontend    - run Next.js dev server on :3000"
	@echo "make test        - backend pytest + frontend vitest"
	@echo "make lint        - frontend eslint"
	@echo "make typecheck   - frontend tsc --noEmit"
	@echo "make build       - frontend production build"
	@echo "make docker      - docker compose up --build"
	@echo "make smoke       - end-to-end API smoke test against $(API)"

install:
	cd backend && python3 -m pip install -r requirements.txt
	cd frontend && npm install

backend:
	cd backend && python3 -m uvicorn app.main:app --reload --port 8000

frontend:
	cd frontend && NEXT_PUBLIC_API_BASE_URL=$(API) npm run dev

dev:
	@echo "backend :8000  +  frontend :3000  (Ctrl-C stops both)"
	@( cd backend && python3 -m uvicorn app.main:app --reload --port 8000 & \
	   cd frontend && NEXT_PUBLIC_API_BASE_URL=$(API) npm run dev & \
	   wait )

test:
	cd backend && python3 -m pytest -q
	cd frontend && npm run test -- --run

lint:
	cd frontend && npm run lint

typecheck:
	cd frontend && npm run typecheck

build:
	cd frontend && npm run build

docker:
	docker compose up --build

smoke:
	cd backend && API_BASE=$(API) python3 scripts/smoke_e2e.py

clean:
	rm -rf frontend/.next frontend/node_modules backend/.pytest_cache
