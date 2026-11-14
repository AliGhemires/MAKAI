.PHONY: help setup setup-lite check test lint fmt sim mission teleop markers calibrate-ground sync

help:            ## list the commands
	@grep -E '^[a-z-]+:.*##' $(MAKEFILE_LIST) | awk -F ':.*## ' '{printf "  make %-18s %s\n", $$1, $$2}'

setup:           ## install everything (LeRobot, torch, ultralytics): several GB
	uv sync --all-extras

setup-lite:      ## install the core only (simulation, navigation, geometry): seconds
	uv sync

check: lint test ## what CI runs: run it before every push

test:            ## unit tests + full mission in simulation
	uv run --no-sync pytest

lint:            ## style and import checks
	uv run --no-sync ruff check .
	uv run --no-sync ruff format --check .

fmt:             ## fix style automatically
	uv run --no-sync ruff check --fix .
	uv run --no-sync ruff format .

sim:             ## run the whole mission in the 2D simulator (no robot)
	uv run --no-sync makai-mission --sim

mission:         ## run the mission on the real robot (host must run on the Pi)
	uv run --no-sync makai-mission

teleop:          ## leader arm + keyboard teleoperation, press p to save an arm pose
	uv run --no-sync python scripts/teleop.py

markers:         ## generate the printable ArUco markers into assets/markers/
	uv run --no-sync python scripts/make_markers.py

calibrate-ground: ## calibrate pixel -> floor mapping from the printed sheet
	uv run --no-sync makai-calibrate-ground

sync:            ## get the latest main under your work
	git pull --rebase origin main
