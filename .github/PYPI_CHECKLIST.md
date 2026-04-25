# PyPI Publishing Checklist

## Before First Release

- [ ] Register on PyPI: https://pypi.org/account/register/
- [ ] Set up GitHub trusted publisher: https://pypi.org/manage/account/publishing/
  - Repository: `henstarr/deadweight`
  - Repository owner: `henry.j.starr`
  - Workflow name: `publish.yml`
  - Environment: `publish`
- [ ] Create GitHub environment `publish`:
  - Go to Settings → Environments → New environment
  - Name: `publish`
  - No secrets needed (trusted publishing handles auth)
- [ ] Verify `pyproject.toml` has all metadata:
  - name ✓
  - version ✓
  - description ✓
  - readme ✓
  - license ✓
  - authors ✓
  - urls ✓

## For Each Release

### Local Validation
```bash
# Run tests
uv run pytest

# Build
uv build

# Check artifacts
ls -lh dist/

# Verify CLI still works
python -m deadweight.cli --version
```

### Release Steps
```bash
# 1. Update version
# vim pyproject.toml

# 2. Commit
git add pyproject.toml
git commit -m "Bump version to X.Y.Z"

# 3. Tag (triggers GitHub Actions)
git tag vX.Y.Z
git push origin main
git push origin vX.Y.Z

# 4. Monitor
# https://github.com/henstarr/deadweight/actions

# 5. Verify
# https://pypi.org/project/deadweight/
```

## Quick Links

- **PyPI Project**: https://pypi.org/project/deadweight/
- **PyPI Trusted Publishers**: https://pypi.org/manage/account/publishing/
- **GitHub Actions**: https://github.com/henstarr/deadweight/actions
- **Full Guide**: PUBLISHING.md

## Notes

- Trusted publishing eliminates need for PyPI API tokens
- Tags must start with `v` (e.g., `v0.1.0`)
- First-time setup takes ~5 minutes
- Subsequent releases are just: edit version → tag → push
