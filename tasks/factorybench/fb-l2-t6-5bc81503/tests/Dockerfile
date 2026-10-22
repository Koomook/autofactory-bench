# Separate verifier: only /app/answer.json crosses from the agent.
FROM python:3.12-slim
COPY test.sh grade.py gold.json /tests/
RUN chmod 755 /tests/test.sh
WORKDIR /app
