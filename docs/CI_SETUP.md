# Continuous integration and merge gate

## Ready-to-run workflow

`.github/workflows/quality.yml` runs on every push, pull request, merge queue group,
and manual dispatch. It supports a standalone project or `thal_labconsult/`
inside a parent repository. The stable required check is **thallink-quality**.

The Windows/Python 3.12 job installs the complete 52-package runtime/development
lock with exact versions, artifact SHA-256 hashes, and binary wheels only,
checks imports and versions, runs correctness lint, rejects a stale rule inventory,
runs the full pytest suite with JUnit XML and application coverage, and checks the
source package allowlist. It then installs the Chromium revision selected by the
pinned Playwright version and runs synthetic browser/printable-report QA, including
DOM, keyboard interaction and PDF rendering evidence in `artifacts/browser/`.
Any failed step fails the job. Statement and branch
coverage across `logic`, `ui`, `utils`, `thalab`, and `pages` must reach 80% combined.
Tests, development scripts, and entrypoint `app.py` are outside that coverage
denominator; app.py is exercised through AppTest. Coverage is not clinical accuracy.

Always-run steps publish a GitHub job summary and upload XML, JSON, and HTML reports
for 14 days. Only synthetic cases are used. Permissions are read-only; PRs do not
receive write tokens or secrets. There are no path filters that leave a required
check permanently pending, and no `continue-on-error` bypass.

## GitHub destination and activation

On 2026-10-16 the owner selected
[`Pongphan/thal_labconsult_v2`](https://github.com/Pongphan/thal_labconsult_v2)
for source publication. Its existing default branch is `main`. Publish the project
at the repository root, preserving its initial README commit. The workflow belongs
at `.github/workflows/quality.yml`; check actual hosted results in
[GitHub Actions](https://github.com/Pongphan/thal_labconsult_v2/actions/workflows/quality.yml).
Source publication does not activate branch protection or prove merge enforcement.

The following parent-repository notes describe the original local workspace:

The current Git root is the **parent** `D:/Works/Python/py`, not this folder.
GitHub only discovers workflows in the repository root `.github/workflows`.
For the current parent layout, synchronize the reviewed project workflow to
`D:/Works/Python/py/.github/workflows/thal-labconsult-quality.yml`.
For a standalone repository, the workflow is already in the correct relative path.

On 2026-10-16 the parent-root copy was synchronized to the updated project workflow
and byte/hash equality verified. No parent Git index/config, remote, commit or hosted
repository protection was changed by that synchronization.

No Git remote or authenticated GitHub CLI was configured during the earlier local
verification. Its evidence does not claim a hosted run or repository protection. A YAML file cannot
by itself enforce a merge prohibition. The repository administrator must:

1. Commit/push the workflow and project changes to the intended GitHub repository.
2. Run the workflow once and confirm that **thallink-quality** appears.
3. In Settings → Rules → Rulesets (or branch protection), target the default and
   release branches; require pull requests and the **thallink-quality** status check.
4. Require up-to-date checks (or use merge queue), block force pushes/deletions, and
   remove bypass actors if the policy must also apply to administrators.
5. Open a throwaway PR with a failing synthetic test; record that merging is blocked.
   Correct the test and confirm that the check passes. Do not merge the intentional failure.

Record repository URL, protected branch, ruleset ID, check name, run URL, tester,
date, failed-PR evidence and corrected-PR evidence in the review sign-off package.
The publication target is now known; repository protection and enforcement verification
remain separate administration steps.

A local-only preparation helper creates a branch-specific ruleset and concrete
commands after the intended repository and branch are supplied. It checks an
existing `origin` against that repository, rejects mismatches, and never invokes
`gh`, changes Git configuration, stages files, commits, pushes, or enables rules.
With no origin it records that the checkout identity remains unverified.

```powershell
# Set these to the repository/branch confirmed by the owner; no defaults are assumed.
$targetRepository = Read-Host 'Confirmed GitHub owner/repository'
$targetBranch = Read-Host 'Confirmed protected branch'
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts/prepare_ci_activation.ps1 -Repository $targetRepository -Branch $targetBranch
```

Review the newly created `artifacts/ci-activation-*/REVIEW_COMMANDS.txt`, the exact
`refs/heads/...` target in its ruleset, and `ACTIVATION_STATUS.json`. The supplied
base `.github/required-checks.ruleset.json` requires a PR and **thallink-quality**,
with no bypass actors. Creating it is additive, so inspect existing repository and
organization rulesets first; do not create duplicates. Execute the prepared hosted
commands only after repository ownership, workflow placement, a successful hosted
run and authorization are established. Capture the returned ruleset ID and failed/
corrected PR evidence. A YAML file, local tests, a prepared JSON payload, or a
successful ruleset POST alone does not prove merge enforcement.
See the [GitHub rulesets API](https://docs.github.com/en/rest/repos/rules#create-a-repository-ruleset).

## Local reproduction

With the Windows launcher, use `powershell -NoProfile -ExecutionPolicy Bypass -File scripts/setup.ps1 -Dev` once and
`powershell -NoProfile -ExecutionPolicy Bypass -File scripts/test.ps1` thereafter. This process-only policy does not change the machine policy. This works with the project's
uv-created environment even when pip is absent. The commands below assume a
conventional Python environment with pip:

```powershell
python -m pip install --require-hashes --only-binary=:all: -r requirements-dev-lock-win-py312.txt
python scripts/check_environment.py --locked --development
python -m ruff check .
python scripts/generate_rule_inventory.py --check
python -m pytest --junitxml=artifacts/junit.xml --cov --cov-report=term-missing --cov-report=xml:artifacts/coverage.xml --cov-report=html:artifacts/htmlcov --cov-report=json:artifacts/coverage.json
python scripts/package_source.py --check
python -m playwright install chromium
python scripts/browser_smoke.py
python scripts/ci_summary.py
```

`requirements-dev.txt` contains direct development inputs; it is not the install
lock. `requirements-dev-lock-win-py312.txt` includes the runtime closure plus all
transitive test/browser/PDF dependencies (including coverage, pluggy, iniconfig,
pygments, colorama, greenlet and pyee). Runtime versions were preserved when hashes
were added. On 2026-10-16 a new isolated CPython 3.12.15 environment installed these
52 packages using uv 0.12.23 with `--require-hashes --only-binary=:all:` and passed
`check_environment.py --locked --development`. This is local clean-install evidence,
not a hosted CI result. Browser downloads are version-bound by Playwright but are
outside the Python artifact lock; record the actual browser version in QA evidence.

To reproduce the current locks with uv on Windows/Python 3.12, use the current lock
as a constraint; write candidates separately and review before replacing files:

```powershell
uv pip compile requirements.txt -c requirements-lock-win-py312.txt --python .venv/Scripts/python.exe --python-platform x86_64-pc-windows-msvc --generate-hashes --only-binary=:all: -o runtime-candidate.txt
uv pip compile requirements.txt requirements-dev.txt -c requirements-dev-lock-win-py312.txt --python .venv/Scripts/python.exe --python-platform x86_64-pc-windows-msvc --generate-hashes --only-binary=:all: -o dev-candidate.txt
```

For an intentional upgrade, first adjust direct inputs and the affected constraint;
review the resolver diff, retain exact pins and hashes for the full closure, then
repeat a fresh-environment install and all checks. Use a new empty venv to prove the
lock works without packages inherited from a developer machine. Setup preserves
existing unrelated packages rather than deleting them. Hashes are checked by the
installer; `check_environment.py` checks the lock format, installed versions,
dependency constraints/extras, closure and imports, not installed-file integrity.

After an intentional rule/engine edit, regenerate the inventory
with `python scripts/generate_rule_inventory.py`, review the diff, then run checks.
Do not regenerate silently in CI: a stale inventory must fail review.

## References

- [GitHub: build and test Python](https://docs.github.com/en/actions/tutorials/build-and-test-code/python)
- [GitHub: protected branches and required checks](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-protected-branches/about-protected-branches)
- [GitHub: troubleshooting required checks](https://docs.github.com/en/pull-requests/how-tos/merge-and-close-pull-requests/troubleshooting-required-status-checks)
- [pytest-cov configuration](https://pytest-cov.readthedocs.io/en/stable/config.html)
- [uv: locking environments](https://docs.astral.sh/uv/pip/compile/)
- [pip: hash-checking mode and binary-only installs](https://pip.pypa.io/en/stable/topics/secure-installs/)
