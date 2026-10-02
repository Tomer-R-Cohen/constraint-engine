# Serves librechat.yaml on the project's private network only (no public domain).
FROM python:3.13-alpine
WORKDIR /srv
COPY librechat.yaml .
EXPOSE 8080
CMD ["python", "-m", "http.server", "8080", "--bind", "::"]
