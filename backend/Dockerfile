FROM python:3.12-slim

WORKDIR /srv

# The project is installed for its dependencies; code is mounted/copied whole,
# so there is no deps-only layer to cache separately.
COPY . .
RUN pip install --no-cache-dir --upgrade pip && pip install --no-cache-dir .

ENV PYTHONPATH=/srv PYTHONUNBUFFERED=1
EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
