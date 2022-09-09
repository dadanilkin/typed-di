P_RUN = pdm run
P_NAME = typed_di

lint:
	@${P_RUN} mypy ${P_NAME}/
	@${P_RUN} flake8 ${P_NAME}/

format:
	@${P_RUN} black ${P_NAME}/ tests/
	@${P_RUN} isort ${P_NAME}/ tests/

test:
	@${P_RUN} pytest tests/ -vv

build:
	@${P_RUN} build
