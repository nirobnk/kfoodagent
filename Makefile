# Common tasks. Run from the repository root.

.PHONY: help setup images backend dashboard test lint tunnel webhook check

help:
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

setup: ## Install backend and dashboard dependencies
	cd backend && python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
	cd dashboard && npm install
	$(MAKE) images

images: ## Copy the studio product photos into the dashboard's public folder
	@# The dashboard serves its own photos because kfoods.lk only hosts the older
	@# web shots. Vercel builds from dashboard/, so the files have to live inside it.
	mkdir -p dashboard/public/assets/products
	cp assets/products/*.jpeg assets/products/*.webp dashboard/public/assets/products/

backend: ## Run the API on http://localhost:8000
	cd backend && .venv/bin/uvicorn main:app --reload --port 8000

dashboard: ## Run the dashboard on http://localhost:3000
	cd dashboard && npm run dev

tunnel: ## Expose the local API to Meta (point the webhook at the https URL + /webhook)
	@# A free ngrok account includes one static domain. Claim it, then export
	@# NGROK_DOMAIN=your-name.ngrok-free.app and the URL stops changing on every
	@# restart — otherwise Meta's callback URL has to be re-entered each time.
	ngrok http 8000 $(if $(NGROK_DOMAIN),--url=$(NGROK_DOMAIN),)

webhook: ## Point Meta's webhook at the tunnel that is running now
	@# Inbound messages are only delivered to the URL registered on the Meta app.
	@# A free tunnel changes URL on every restart, which silences the agent.
	python3 scripts/set_webhook.py

test: ## Run the backend test suite
	cd backend && .venv/bin/pytest

lint: ## Lint both sides
	cd backend && .venv/bin/ruff check .
	cd dashboard && npm run lint

check: test lint ## Everything CI runs
	cd dashboard && npm run typecheck && npm run build
