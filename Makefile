.PHONY: check test smoke planning-audit challenge-validate challenges harness-version harness-lock harness-eval-validate pi-runtime-check

check:
	python3 tools/harness_check.py

test:
	python3 -m unittest discover -s tests -v

smoke: check test

planning-audit:
	python3 tools/github_planning.py audit --offline

challenge-validate:
	python3 tools/run_challenges.py

challenges:
	python3 tools/run_challenges.py --run

harness-version:
	python3 tools/harness_upgrade.py status

harness-lock:
	python3 tools/harness_upgrade.py lock --yes

harness-eval-validate:
	python3 tools/evaluate_harness.py

pi-runtime-check:
	python3 tools/pi_adapter_check.py
