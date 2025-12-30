FROM python:3.11-slim

WORKDIR /app

# Kopē requirements.txt un instalē Python atkarības
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Kopē visu projektu
COPY . .

# Izveido data mapi, ja tā nav
RUN mkdir -p data

# EXPOSE portu (Render izmanto $PORT mainīgo)
EXPOSE 10000

# Palaiž Streamlit aplikāciju
CMD streamlit run app.py --server.address=0.0.0.0 --server.port=${PORT:-10000} --server.headless=true

