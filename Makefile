.PHONY: install install-pipx dev test clean uninstall release

# ── Global install (isolated env, claudre on PATH) ────────────────────────
# Requires pipx  (brew install pipx / apt install pipx / pip install --user pipx)
install:
	pipx install --force --editable .
	@echo ""
	@echo "claudre installed. Run 'claudre setup' to add tmux keybindings."

# Alternative: uv tool (requires uv >= 0.4)
install-uv:
	uv tool install --editable . --force
	@echo ""
	@echo "claudre installed via uv tool. Run 'claudre setup' to add tmux keybindings."

uninstall:
	pipx uninstall claudre

# ── Developer install (in active virtualenv) ──────────────────────────────
dev:
	uv pip install -e ".[dev]"

# ── Tests ─────────────────────────────────────────────────────────────────
test:
	python -m pytest tests/ -v

# ── Release ───────────────────────────────────────────────────────────────
# Usage: make release VERSION=3.1.0
release:
	@[ -n "$(VERSION)" ] || (echo "Usage: make release VERSION=x.y.z"; exit 1)
	@git diff --quiet HEAD || (echo "error: working tree is dirty — commit or stash first"; exit 1)
	@git diff --quiet --cached || (echo "error: staged changes present — commit first"; exit 1)
	git tag v$(VERSION)
	git push origin v$(VERSION)
	@echo ""
	@echo "Tag v$(VERSION) pushed."
	@echo "Go to GitHub → Releases → Draft a new release → choose tag v$(VERSION) → Publish."
	@echo "The publish workflow will run automatically."

# ── Cleanup ───────────────────────────────────────────────────────────────
clean:
	rm -rf build/ dist/ *.egg-info src/*.egg-info
	find . -type d -name __pycache__ -exec rm -rf {} +
