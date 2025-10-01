.PHONY: api worker web

api:
	cd api && uvicorn app.main:app --reload --log-level info

worker:
	cd worker && python main.py

web:
	cd web && npm run dev -- --host
