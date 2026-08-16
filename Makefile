up:
	docker compose up --build --remove-orphans -d

down:
	docker compose down --remove-orphans

start:
	docker compose start

stop:
	docker compose stop

linters:
	. .venv/bin/activate && pre-commit run --all-files

.PHONY: tests
tests:
	@sh -c 'set -eu; \
		project=shorty_tests; \
		cleanup() { docker compose -p "$$project" -f compose.test.yaml down --volumes --remove-orphans; }; \
		trap cleanup EXIT INT TERM; \
		docker compose -p "$$project" -f compose.test.yaml up \
			--build --abort-on-container-exit --exit-code-from tests; \
		docker compose -p "$$project" -f compose.test.yaml \
			cp tests:/app/coverage.xml ./coverage.xml'
