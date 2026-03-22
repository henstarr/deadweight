FROM python:3.12-slim

WORKDIR /app
COPY pyproject.toml README.md ./
COPY src/ src/
COPY agents/ agents/
COPY schema/ schema/

RUN pip install --no-cache-dir .

EXPOSE 8340

CMD ["deadweight", "serve", "--port", "8340"]
