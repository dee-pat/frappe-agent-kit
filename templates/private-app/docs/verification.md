# Verification

## Definition of done

Run the gates affected by the change and record their observed exit statuses
in the PR or handoff. Keep upstream copies identical to skills.lock. Verify
hosted CI on the final revision before claiming it passes.

## Required gates

| Change | Command |
| --- | --- |
| Guidance, kit or merge tooling | `scripts/check-agent-kit.sh` |
| Python, configuration or workflows | `scripts/lint.sh` and kit checks |
| Server, installation or CI bootstrap | Lint, kit checks, migration and complete app tests |

Run lint and kit checks from the app root. From the bench root, run
`bench --site __TEST_SITE__ migrate` and
`bench --site __TEST_SITE__ run-tests --app __APP_NAME__`.
Tests require the separate installed test site with allow_tests enabled.
Interactive development uses __DEV_SITE__; never run tests there.

## Failure and recovery

Report unavailable or failing gates with their actual error. Fix the cause and
rerun; preserve assertions. For a workflow change, a passing local suite does
not substitute for GitHub's Linux bootstrap. CI pins Frappe to
__FRAPPE_VERSION__, Python __PYTHON_VERSION__, and MariaDB 11.8.
