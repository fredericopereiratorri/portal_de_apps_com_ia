"""
Script para buscar dados reais dos bairros de Recife via OpenStreetMap e IBGE
"""
import json
import time
import requests
from typing import Dict, List, Any

OVERPASS_URL = "https://overpass-api.de/api/interpreter"

# Recife city boundary
RECIFE_AREA_ID = 3600302486  # OpenStreetMap relation ID for Recife

def fetch_neighborhoods_geojson():
    """Busca os polígonos dos bairros de Recife via Overpass API"""
    print("Buscando limites dos bairros de Recife...")

    # Query Overpass para obter todos os bairros de Recife
    # Tenta diferentes tags: admin_level, place=suburb, place=neighbourhood
    overpass_query = """
    [out:json][timeout:90];
    area(3600302486)->.recife;
    (
      relation["boundary"="administrative"]["admin_level"](area.recife);
      way["place"="suburb"](area.recife);
      way["place"="neighbourhood"](area.recife);
      relation["place"="suburb"](area.recife);
      relation["place"="neighbourhood"](area.recife);
    );
    out geom;
    """

    try:
        response = requests.post(
            OVERPASS_URL,
            data={'data': overpass_query},
            timeout=120
        )
        response.raise_for_status()
        data = response.json()

        print(f"[OK] Encontrados {len(data.get('elements', []))} bairros")
        return data
    except Exception as e:
        print(f"[ERRO] Erro ao buscar bairros: {e}")
        return None

def fetch_pois_in_bbox(bbox: List[float], poi_type: str, tags: Dict[str, str]) -> int:
    """Conta POIs de um tipo específico dentro de um bbox"""

    # Construir filtros de tags
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

        # Contar elementos
        count = len(data.get('elements', []))
        return count
    except Exception as e:
        print(f"  [ERRO] Erro ao buscar {poi_type}: {e}")
        return 0

def get_bbox_from_geometry(geometry: Dict) -> List[float]:
    """Calcula o bounding box de uma geometria"""
    coords = []

    if geometry['type'] == 'Polygon':
        for ring in geometry['coordinates']:
            coords.extend(ring)
    elif geometry['type'] == 'MultiPolygon':
        for polygon in geometry['coordinates']:
            for ring in polygon:
                coords.extend(ring)

    if not coords:
        return [0, 0, 0, 0]

    lons = [c[0] for c in coords]
    lats = [c[1] for c in coords]

    # bbox format: [min_lat, min_lon, max_lat, max_lon]
    return [min(lats), min(lons), max(lats), max(lons)]

def calculate_area_km2(geometry: Dict) -> float:
    """Calcula área aproximada em km² usando fórmula de Shoelace"""
    def shoelace_area(coords):
        """Fórmula de Shoelace para calcular área de polígono"""
        n = len(coords)
        area = 0.0
        for i in range(n):
            j = (i + 1) % n
            area += coords[i][0] * coords[j][1]
            area -= coords[j][0] * coords[i][1]
        area = abs(area) / 2.0
        return area

    # Converter de graus² para km² (aproximação para latitude de Recife ~-8°)
    # 1 grau de latitude ≈ 111 km
    # 1 grau de longitude em Recife ≈ 110 km (depende da latitude)
    deg_to_km_lat = 111.0
    deg_to_km_lon = 110.0

    total_area = 0.0

    if geometry['type'] == 'Polygon':
        for ring in geometry['coordinates']:
            area_deg2 = shoelace_area(ring)
            total_area += area_deg2 * deg_to_km_lat * deg_to_km_lon
    elif geometry['type'] == 'MultiPolygon':
        for polygon in geometry['coordinates']:
            for ring in polygon:
                area_deg2 = shoelace_area(ring)
                total_area += area_deg2 * deg_to_km_lat * deg_to_km_lon

    return round(total_area, 2)

def osm_to_geojson(osm_data: Dict) -> Dict:
    """Converte dados do Overpass para GeoJSON"""

    features = []

    for element in osm_data.get('elements', []):
        tags = element.get('tags', {})
        name = tags.get('name', 'Sem nome')

        # Extrair geometria baseado no tipo
        if element['type'] == 'relation':
            geometry = extract_geometry_from_relation(element)
        elif element['type'] == 'way':
            geometry = extract_geometry_from_way(element)
        else:
            continue

        if not geometry:
            print(f"  [AVISO] Pulando {name} - sem geometria valida")
            continue

        # Calcular área
        area_km2 = calculate_area_km2(geometry)

        if area_km2 == 0:
            print(f"  [AVISO] Pulando {name} - area zero")
            continue

        print(f"  Processando: {name} ({area_km2} km²)")

        # Buscar POIs
        bbox = get_bbox_from_geometry(geometry)

        print(f"    Buscando POIs...")
        farmacias = fetch_pois_in_bbox(bbox, "farmácias", {"amenity": "pharmacy"})
        time.sleep(0.5)  # Rate limiting

        shoppings = fetch_pois_in_bbox(bbox, "shoppings", {"shop": "mall"})
        time.sleep(0.5)

        postos = fetch_pois_in_bbox(bbox, "postos", {"amenity": "fuel"})
        time.sleep(0.5)

        supermercados = fetch_pois_in_bbox(bbox, "supermercados", {"shop": "supermarket"})
        time.sleep(0.5)

        escolas = fetch_pois_in_bbox(bbox, "escolas", {"amenity": "school"})
        time.sleep(0.5)

        print(f"    [OK] POIs: {farmacias} farmacias, {shoppings} shoppings, {postos} postos, {supermercados} supermercados, {escolas} escolas")

        # População estimada (será atualizado manualmente com dados do IBGE)
        # Por enquanto, estimativa baseada na área e densidade média de Recife
        densidade_media_recife = 7000  # hab/km²
        populacao_estimada = int(area_km2 * densidade_media_recife)

        feature = {
            "type": "Feature",
            "properties": {
                "nome": name,
                "populacao": populacao_estimada,  # Estimativa - será atualizada
                "area_km2": area_km2,
                "densidade": int(populacao_estimada / area_km2) if area_km2 > 0 else 0,
                "farmacias": farmacias,
                "shoppings": shoppings,
                "postos_gasolina": postos,
                "supermercados": supermercados,
                "escolas": escolas,
                "osm_id": element.get('id'),
            },
            "geometry": geometry
        }

        features.append(feature)

    return {
        "type": "FeatureCollection",
        "features": features
    }

def extract_geometry_from_way(way: Dict) -> Dict:
    """Extrai geometria de um way do OSM"""
    if 'geometry' not in way:
        return None

    coords = [(node['lon'], node['lat']) for node in way['geometry']]

    if not coords:
        return None

    # Verificar se é um polígono fechado (primeiro == último)
    if coords[0] != coords[-1]:
        coords.append(coords[0])  # Fechar o polígono

    return {
        "type": "Polygon",
        "coordinates": [coords]
    }

def extract_geometry_from_relation(relation: Dict) -> Dict:
    """Extrai geometria de uma relation do OSM"""

    # OSM relations têm membros que podem ser ways
    # Precisamos reconstruir a geometria a partir dos membros

    members = relation.get('members', [])

    if not members:
        return None

    # Coletar todos os ways (outer rings)
    outer_ways = []

    for member in members:
        if member.get('role') in ['outer', '']:
            if 'geometry' in member:
                coords = [(node['lon'], node['lat']) for node in member['geometry']]
                if coords:
                    outer_ways.append(coords)

    if not outer_ways:
        return None

    # Se temos apenas um way, é um polígono simples
    if len(outer_ways) == 1:
        return {
            "type": "Polygon",
            "coordinates": [outer_ways[0]]
        }

    # Se temos múltiplos ways, tentar criar MultiPolygon
    # (simplificado - assume que cada way é um polígono separado)
    return {
        "type": "MultiPolygon",
        "coordinates": [[way] for way in outer_ways]
    }

def main():
    print("=" * 60)
    print("BUSCANDO DADOS REAIS DOS BAIRROS DE RECIFE")
    print("=" * 60)
    print()

    # Buscar dados dos bairros
    osm_data = fetch_neighborhoods_geojson()

    if not osm_data:
        print("\n[ERRO] Falha ao buscar dados dos bairros")
        return

    print()
    print("Convertendo para GeoJSON e buscando POIs...")
    print("(Isso pode demorar vários minutos devido ao rate limiting da API)")
    print()

    geojson = osm_to_geojson(osm_data)

    # Salvar arquivo
    output_file = "data/recife_bairros_real.json"
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(geojson, f, ensure_ascii=False, indent=2)

    print()
    print("=" * 60)
    print(f"[OK] Dados salvos em: {output_file}")
    print(f"[OK] Total de bairros processados: {len(geojson['features'])}")
    print("=" * 60)
    print()
    print("NOTA: Os dados de populacao sao ESTIMATIVAS baseadas na area.")
    print("Para dados precisos, consulte o Censo IBGE 2022.")
    print()

if __name__ == "__main__":
    main()
