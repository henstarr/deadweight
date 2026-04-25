# Publishing Deadweight to PyPI

## One-time Setup (First Release Only)

### 1. Reserve the PyPI Package Name
```bash
# Check if 'deadweight' is available
pip index versions deadweight 2>&1 | grep -i "no releases"

# If available, claim it: https://pypi.org/account/register/
# (Register, then come back here)
```

### 2. Configure GitHub for Trusted Publishing
This eliminates the need to store PyPI API tokens in secrets.

**Steps:**
1. Go to https://pypi.org/manage/account/publishing/
2. Add a new **Trusted Publisher**:
   - **Repository name**: `henstarr/deadweight`
   - **Repository owner**: `henry.j.starr` (your PyPI username)
   - **Workflow name**: `publish.yml`
   - **Environment name**: `publish`

3. Create the GitHub environment in your repo:
   - Settings → Environments → New environment → `publish`
   - No secrets needed (PyPI trusted publishing handles auth)

### 3. Verify pyproject.toml
The repository already has:
```toml
[project.urls]
Homepage = "https://github.com/henstarr/deadweight"
```

Optional: add more metadata
```toml
[project.urls]
Homepage = "https://github.com/henstarr/deadweight"
Documentation = "https://github.com/henstarr/deadweight#readme"
Repository = "https://github.com/henstarr/deadweight"
Issues = "https://github.com/henstarr/deadweight/issues"
```

---

## Publishing a Release

### Automated (Recommended)
```bash
# 1. Update version in pyproject.toml
sed -i '' 's/version = "0.1.0"/version = "0.2.0"/' pyproject.toml

# 2. Create a changelog entry
# (optional but recommended)

# 3. Commit
git add pyproject.toml
git commit -m "Bump version to 0.2.0"

# 4. Create a git tag (triggers GitHub Actions)
git tag v0.2.0
git push origin main
git push origin v0.2.0

# Wait for GitHub Actions to complete at:
# https://github.com/henstarr/deadweight/actions
# Then verify on PyPI: https://pypi.org/project/deadweight/
```

### Manual (If GitHub Actions fails)
```bash
# 1. Install build dependencies
uv sync --extra dev

# 2. Build distribution
uv build

# 3. Install twine (PyPI upload tool)
pip install twine

# 4. Upload to PyPI
twine upload dist/deadweight-0.2.0*

# Or use uv's built-in publish
uv publish
```

---

## After First PyPI Release

Update the README install instructions:
```markdown
## Install

```bash
uv tool install deadweight
```

Or pin a version:
```bash
uv tool install deadweight==0.2.0
```

Installs `dw` on your PATH.
```

---

## Versioning

Follow [Semantic Versioning](https://semver.org/):
- **0.1.0** → **0.2.0** (minor feature: new command, improved UX)
- **0.1.0** → **0.1.1** (patch: bug fix, docs)
- **0.1.0** → **1.0.0** (major: breaking changes, stable API)

Current status: **0.1.0** (alpha) — breaking changes are OK between minor versions.

---

## Troubleshooting

### "403 Forbidden" on publish
- Check PyPI trusted publisher is configured correctly
- Ensure tag format is `v*` (e.g., `v0.2.0`, not `0.2.0`)
- Verify GitHub environment `publish` exists and has no restrictive branch rules

### Package not appearing on PyPI after upload
- Wait 5-10 minutes (PyPI CDN cache)
- Check https://pypi.org/project/deadweight/
- Verify wheel filename matches: `deadweight-{version}-py3-none-any.whl`

### Want to yank a bad release?
```bash
# On PyPI web UI: Project → Release history → Yank button
# (Yanked versions won't be installed by default)
```

---

## Resources

- [PyPI Help](https://pypi.org/help/)
- [Trusted Publishing Guide](https://docs.pypi.org/trusted-publishers/)
- [uv publish docs](https://docs.astral.sh/uv/guides/publish/)
