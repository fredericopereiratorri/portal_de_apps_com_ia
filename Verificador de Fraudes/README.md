## 1) Pré-requisitos
- Python 3.11+
- **Tesseract OCR** instalado (Ubuntu/Debian: `sudo apt-get install -y tesseract-ocr`)
- **Redis** (local `redis-server` ou via Docker)

## 2) Configuração (local)
```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.sample .env
# edite .env e coloque sua OPENAI_API_KEY
export $(cat .env | xargs)
```

## 3) Rodando
### Local
```bash
flask --app app.py run --host=0.0.0.0 --port=8000
```
Acesse: http://localhost:8000

### Com Docker Compose
```bash
docker compose up --build
```

## 4) Observações
- Sem banco de dados (uso de cache via Redis).
- Cache:
  - OCR por **hash da imagem**
  - Download/parse de **URL** por URL
  - Resposta do **LLM** por **hash do conteúdo**
- Limite de upload padrão: 10MB (`MAX_CONTENT_LENGTH_MB`).
