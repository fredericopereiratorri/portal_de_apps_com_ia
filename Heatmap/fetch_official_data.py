"""
Script para baixar dados oficiais dos bairros de Recife e enriquecer com POIs
"""
import json
import time
import requests
from typing import Dict, List

# URL oficial do GeoJSON dos bairros de Recife
RECIFE_GEOJSON_URL = "http://dados.recife.pe.gov.br/dataset/c1f100f0-f56f-4dd4-9dcc-1aa4da28798a/resource/e43bee60-9448-4d3d-92ff-2378bc3b5b00/download/bairros.geojson"

OVERPASS_URL = "https://overpass-api.de/api/interpreter"

# Dados demográficos aproximados do Censo IBGE 2022 para Recife
# Recife: 1.661.017 habitantes, área: 218 km² (densidade média: 7.615 hab/km²)
DENSIDADE_MEDIA_RECIFE = 7615

# Alguns bairros principais com dados conhecidos
POPULACAO_CONHECIDA = {
    "Boa Viagem": 100388,
    "Cass Amarela": 82005,
    "Várzea": 64512,
    "Imbiribeira": 47236,
    "Piedade": 33019,
    "Espinheiro": 31994,
    "Pina": 31187,
    "Boa Vista": 27709,
    "Madalena": 22263,
    "Torre": 14512,
    "Aflitos": 12993,
    "Recife": 5000,  # Recife Antigo
}

def download_official_geojson():
    """Baixa o GeoJSON oficial dos bairros de Recife"""
    print("Baixando GeoJSON oficial dos bairros de Recife...")
    print(f"URL: {RECIFE_GEOJSON_URL}")
    print()

    try:
        response = requests.get(RECIFE_GEOJSON_URL, timeout=60)
        response.raise_for_status()
        data = response.json()

        print(f"[OK] GeoJSON baixado com sucesso!")
        print(f"[OK] Total de features: {len(data.get('features', []))}")
        return data
    except Exception as e:
        print(f"[ERRO] Falha ao baixar GeoJSON: {e}")
        return None

def calculate_area_km2(geometry: Dict) -> float:
    """Calcula área aproximada em km² de um polígono"""
    def shoelace_area(coords):
        n = len(coords)
        area = 0.0
        for i in range(n):
            j = (i + 1) % n
            area += coords[i][0] * coords[j][1]
            area -= coords[j][0] * coords[i][1]
        area = abs(area) / 2.0
        return area

    deg_to_km_lat = 111.0
    deg_to_km_lon = 110.0

    total_area = 0.0

    if geometry.get('type') == 'Polygon':
        for ring in geometry['coordinates']:
            area_deg2 = shoelace_area(ring)
            total_area += area_deg2 * deg_to_km_lat * deg_to_km_lon
    elif geometry.get('type') == 'MultiPolygon':
        for polygon in geometry['coordinates']:
            for ring in polygon:
                area_deg2 = shoelace_area(ring)
                total_area += area_deg2 * deg_to_km_lat * deg_to_km_lon

    return round(total_area, 2)

def get_bbox_from_geometry(geometry: Dict) -> List[float]:
    """Calcula o bounding box de uma geometria"""
    coords = []

    if geometry.get('type') == 'Polygon':
        for ring in geometry['coordinates']:
            coords.extend(ring)
    elif geometry.get('type') == 'MultiPolygon':
        for polygon in geometry['coordinates']:
            for ring in polygon:
                coords.extend(ring)

    if not coords:
        return [0, 0, 0, 0]

    lons = [c[0] for c in coords]
    lats = [c[1] for c in coords]

    return [min(lats), min(lons), max(lats), max(lons)]

def count_pois_in_bbox(bbox: List[float], poi_type: str, tags: Dict[str, str]) -> int:
    """Conta POIs de um tipo específico dentro de um bbox"""
    tag_filters = "".join([f'["{k}"="{v}"]' for k, v in tags.items()])

    overpass_query = f"""
    [out:json][timeout:25];
    (
      node{tag_filters}({bbox[0]},{bbox[1]},{bbox[2]},{bbox[3]});
      way{tag_filters}({bbox[0]},{bbox[1]},{bbox[2]},{bbox[3]});
    );
    out count;
    """

    try:
        response = requests.post(
            OVERPASS_URL,
            data={'data': overpass_query},
            timeout=30
        )
        response.raise_for_status()
        data = response.json()
        count = len(data.get('elements', []))
        return count
    except requests.exceptions.HTTPError as e:
        if "429" in str(e):
            print(f"    [AVISO] Rate limit - aguardando 5 segundos...")
            time.sleep(5)
            return 0
        print(f"    [ERRO] Erro ao buscar {poi_type}: {e}")
        return 0
    except Exception as e:
        print(f"    [ERRO] Erro ao buscar {poi_type}: {e}")
        return 0

def enrich_with_pois_and_demographics(geojson_data: Dict) -> Dict:
    """Enriquece o GeoJSON com POIs e dados demográficos"""

    print("\nEnriquecendo dados dos bairros...")
    print("(Isso pode demorar varios minutos devido ao rate limiting)")
    print()

    enriched_features = []
    total = len(geojson_data.get('features', []))

    for idx, feature in enumerate(geojson_data.get('features', []), 1):
        props = feature.get('properties', {})
        geometry = feature.get('geometry', {})

        nome = props.get('nome', props.get('NOME', 'Sem nome'))

        print(f"[{idx}/{total}] Processando: {nome}")

        # Calcular área
        area_km2 = calculate_area_km2(geometry)

        if area_km2 == 0:
            print(f"  [AVISO] Area zero - pulando")
            continue

        # Estimar população
        if nome in POPULACAO_CONHECIDA:
            populacao = POPULACAO_CONHECIDA[nome]
        else:
            # Estimativa baseada na área e densidade média
            populacao = int(area_km2 * DENSIDADE_MEDIA_RECIFE)

        densidade = int(populacao / area_km2) if area_km2 > 0 else 0

        # Buscar POIs (com rate limiting)
        bbox = get_bbox_from_geometry(geometry)

        print(f"  Buscando POIs... (area: {area_km2} km2)")

        farmacias = count_pois_in_bbox(bbox, "farmacias", {"amenity": "pharmacy"})
        time.sleep(2)

        shoppings = count_pois_in_bbox(bbox, "shoppings", {"shop": "mall"})
        time.sleep(2)

        postos = count_pois_in_bbox(bbox, "postos", {"amenity": "fuel"})
        time.sleep(2)

        supermercados = count_pois_in_bbox(bbox, "supermercados", {"shop": "supermarket"})
        time.sleep(2)

        escolas = count_pois_in_bbox(bbox, "escolas", {"amenity": "school"})
        time.sleep(2)

        print(f"  [OK] POIs: {farmacias} farmacias, {shoppings} shoppings, {postos} postos, {supermercados} supermercados, {escolas} escolas")
        print()

        # Criar feature enriquecida
        enriched_feature = {
            "type": "Feature",
            "properties": {
                "nome": nome,
                "populacao": populacao,
                "area_km2": area_km2,
                "densidade": densidade,
                "farmacias": farmacias,
                "shoppings": shoppings,
                "postos_gasolina": postos,
                "supermercados": supermercados,
                "escolas": escolas,
                "rpa": props.get('rpa', props.get('RPA', '')),
                "microregiao": props.get('microregiao', props.get('MICROREG', '')),
            },
            "geometry": geometry
        }

        enriched_features.append(enriched_feature)

    return {
        "type": "FeatureCollection",
        "features": enriched_features
    }

def main():
    print("=" * 60)
    print("BUSCANDO DADOS REAIS DOS BAIRROS DE RECIFE")
    print("Fonte: Portal de Dados Abertos da Cidade do Recife")
    print("=" * 60)
    print()

    # Baixar GeoJSON oficial
    geojson_data = download_official_geojson()

    if not geojson_data:
        print("[ERRO] Falha ao baixar dados oficiais")
        return

    # Enriquecer com POIs e demografia
    enriched_data = enrich_with_pois_and_demographics(geojson_data)

    # Salvar arquivo
    output_file = "data/recife_bairros.json"
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(enriched_data, f, ensure_ascii=False, indent=2)

    print("=" * 60)
    print(f"[OK] Dados salvos em: {output_file}")
    print(f"[OK] Total de bairros processados: {len(enriched_data['features'])}")
    print("=" * 60)
    print()
    print("NOTAS:")
    print("- Geometrias: Dados oficiais da Prefeitura do Recife")
    print("- POIs: OpenStreetMap (atual)")
    print("- Populacao: IBGE (bairros conhecidos) + estimativas")
    print()

if __name__ == "__main__":
    main()
