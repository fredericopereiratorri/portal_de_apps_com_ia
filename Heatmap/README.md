## Mapa de Calor - Bairros de Recife

Aplicação interativa que visualiza densidade demográfica e pontos de interesse dos bairros de Recife.

### Recursos

- **Mapa de calor** baseado em densidade demográfica
- **Tooltips interativos** ao passar o mouse sobre os bairros
- **Informações detalhadas** ao clicar em cada bairro:
  - População e área
  - Densidade demográfica
  - Quantidade de farmácias
  - Shoppings
  - Postos de gasolina
  - Supermercados
  - Escolas

### Setup

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### Executar

```bash
python app.py
```

Acesse: http://localhost:8002

### Tecnologias

- **Flask**: Framework web
- **Folium**: Mapas interativos (baseado em Leaflet.js)
- **GeoJSON**: Dados geográficos dos bairros

### Dados

Os dados dos bairros estão em `data/recife_bairros.json` e incluem:
- Polígonos GeoJSON de cada bairro
- Informações demográficas
- Contagem de pontos de interesse

**Nota**: Os dados são aproximados e baseados em estimativas para fins de demonstração.
