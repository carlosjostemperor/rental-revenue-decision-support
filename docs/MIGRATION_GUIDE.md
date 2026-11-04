# Migration Guide: update the GitHub repository to v2.1.0

**No remote GitHub changes are made by this ZIP.** You may keep the repository **public** provided all committed material is approved for publication. Do not add real PriceLabs bookings, financial exports or operational analysis outputs to Git.

## 1. Back up the current repository

```bash
git clone https://github.com/<owner>/revenue-management-analytics.git rma-backup
cd rma-backup
git bundle create ../rma-before-v2-1.bundle --all
cd ..
```

## 2. Prepare a review branch

```bash
git clone https://github.com/<owner>/revenue-management-analytics.git rma
cd rma
git switch -c upgrade-v2-1
```

Extract `revenue-management-analytics-v2.1.zip` next to the clone. Copy the **contents** of the `revenue-management-analytics/` directory into the clone, replacing the corresponding files. Do **not** copy `_delivery/` or local PriceLabs exports into Git.

Inspect `git status` and `git diff` before staging. Remove obsolete v1 source files deliberately only after verifying their replacements; do not use blanket recursive deletion.

## 3. Run tests and review the project

```bash
python -m pip install -r requirements-dev.txt
python -m pytest -q

git status --short
```

Check that you are **not** about to commit `data/input/*.csv`, `output/`, executed notebooks, customer names, booking extracts, or unauthorized company reports. Only the synthetic examples should be public.

## 4. Commit after approval

```bash
git add README.md DATA_CHECKLIST.md CHANGELOG.md .gitignore pyproject.toml requirements.txt requirements-dev.txt Revenue_Management_EDA.ipynb rm_analytics/ tests/ docs/ data/example_synthetic/ data/input/.gitkeep
git diff --cached --stat
git commit -m "v2.1.0: review gates, minimum-stay sensitivity and duplicate screening"
git push -u origin upgrade-v2-1
```

Open a pull request; review it before merging. Do not push or merge automatically.

## 5. History and permissions (optional, separate decision)

Earlier Git commits may contain commercial material. Leaving the repository public is a governance decision for the owner and the data rights holder. Deleting a file in the latest commit does **not** erase earlier copies. History rewriting, permission changes and repository-visibility changes must be explicitly approved and separately coordinated; they are not prerequisites imposed by this technical package.

## 6. Internal pilot

1. Use `Revenue_Management_EDA.ipynb` with a synthetic example first.
2. Re-run with your authorized PriceLabs exports **outside Git**.
3. Read `REVIEW_SUMMARY.md`. Any WARN yields `REVIEW_REQUIRED` and must not be treated as fully validated.
4. Review the minimum-stay groups, comparable homes, stay windows and the PriceLabs UI.
5. Record a separate human pricing decision before making changes in PriceLabs.

## Rollback

The backup bundle contains the original refs and commits and can be used to restore the previous state if needed.
