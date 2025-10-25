import os
import json
from flask import Flask, render_template
import folium
from folium import plugins
import branca.colormap as cm

app = Flask(__name__, static_folder="static", template_folder="templates")

# Carregar dados dos bairros
DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
BAIRROS_FILE = os.path.join(DATA_DIR, "olinda_bairros.json")

def load_bairros_data():
    """Carrega dados GeoJSON dos bairros de Recife"""
    with open(BAIRROS_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)

def get_population_range(geojson_data):
    """Calcula o range de população para o mapa de calor"""
    populations = [
        feature['properties']['populacao']
        for feature in geojson_data['features']
    ]
    return min(populations), max(populations)

def create_folium_map():
    """Cria o mapa de calor interativo com Folium"""

    # Carregar dados
    bairros_data = load_bairros_data()

    # Configuração do mapa centrado em Olinda
    olinda_coords = [-8.0089, -34.8553]
    m = folium.Map(
        location=olinda_coords,
        zoom_start=12,
        tiles='OpenStreetMap',
        prefer_canvas=True
    )

    # Criar escala de cores baseada na população (VERDE -> AMARELO -> VERMELHO)
    min_population, max_population = get_population_range(bairros_data)

    colormap = cm.LinearColormap(
        colors=['#00ff00', '#7fff00', '#ffff00', '#ffcc00', '#ff9900', '#ff6600', '#ff3300', '#ff0000', '#cc0000'],
        vmin=min_population,
        vmax=max_population,
        caption='População (habitantes)'
    )

    # Adicionar cada bairro ao mapa
    for feature in bairros_data['features']:
        props = feature['properties']

        # Cor baseada na população
        population = props['populacao']
        color = colormap(population)

        # Obter dados de escolaridade (pode não existir em dados antigos)
        nivel_escolaridade = props.get('nivel_escolaridade', 'N/A')
        ensino_superior = props.get('ensino_superior_pct', 0)
        ensino_medio = props.get('ensino_medio_pct', 0)
        ensino_fundamental = props.get('ensino_fundamental_pct', 0)

        # Criar tooltip COMPLETO com todas as informações
        tooltip_html = f"""
        <div style="font-family: Arial; font-size: 13px; max-width: 320px; padding: 5px;">
            <h3 style="margin: 0 0 12px 0; color: #2c3e50; border-bottom: 2px solid #3498db; padding-bottom: 5px;">
                📍 {props['nome']}
            </h3>

            <div style="margin-bottom: 12px; padding: 8px; background: linear-gradient(135deg, #f5f7fa 0%, #c3cfe2 100%); border-radius: 5px; border-left: 4px solid #3498db;">
                <b style="color: #2c3e50;">👥 Dados Demográficos</b><br>
                <div style="margin-top: 6px; line-height: 1.6;">
                    <span style="color: #555;">População:</span> <b style="color: #2c3e50;">{props['populacao']:,}</b> hab<br>
                    <span style="color: #555;">Área:</span> <b style="color: #2c3e50;">{props['area_km2']}</b> km²<br>
                    <span style="color: #555;">Densidade:</span> <b style="color: #e74c3c;">{props['densidade']:,}</b> hab/km²
                </div>
            </div>

            <div style="margin-bottom: 12px; padding: 8px; background: linear-gradient(135deg, #ffeaa7 0%, #fdcb6e 100%); border-radius: 5px; border-left: 4px solid #f39c12;">
                <b style="color: #2c3e50;">🎓 Escolaridade</b><br>
                <div style="margin-top: 6px; line-height: 1.6;">
                    <span style="color: #555;">Nível:</span> <b style="color: #2c3e50;">{nivel_escolaridade}</b><br>
                    <span style="color: #555;">Ens. Superior:</span> <b style="color: #27ae60;">{ensino_superior}%</b><br>
                    <span style="color: #555;">Ens. Médio:</span> <b style="color: #3498db;">{ensino_medio}%</b><br>
                    <span style="color: #555;">Ens. Fundamental:</span> <b style="color: #e67e22;">{ensino_fundamental}%</b>
                </div>
            </div>

            <div style="margin-bottom: 12px; padding: 8px; background: linear-gradient(135deg, #dfe6e9 0%, #b2bec3 100%); border-radius: 5px; border-left: 4px solid #16a085;">
                <b style="color: #2c3e50;">🏢 Pontos de Interesse</b><br>
                <div style="margin-top: 6px; line-height: 1.6;">
                    💊 Farmácias: <b style="color: #2c3e50;">{props['farmacias']}</b><br>
                    🛒 Shoppings: <b style="color: #2c3e50;">{props['shoppings']}</b><br>
                    ⛽ Postos: <b style="color: #2c3e50;">{props['postos_gasolina']}</b><br>
                    🏪 Supermercados: <b style="color: #2c3e50;">{props['supermercados']}</b><br>
                    🏫 Escolas: <b style="color: #2c3e50;">{props['escolas']}</b>
                </div>
            </div>

            <div style="margin-top: 10px; padding-top: 8px; border-top: 1px solid #ccc; font-size: 11px; color: #777; text-align: center;">
                📅 Dados: Censo IBGE 2022 / OpenStreetMap 2024<br>
                🔄 Atualizado: Outubro 2025
            </div>
        </div>
        """

        # Adicionar polígono do bairro (sem popup, só tooltip)
        folium.GeoJson(
            feature,
            style_function=lambda x, color=color: {
                'fillColor': color,
                'color': '#333333',
                'weight': 2,
                'fillOpacity': 0.6,
                'opacity': 0.8
            },
            highlight_function=lambda x: {
                'fillOpacity': 0.8,
                'weight': 3
            },
            tooltip=folium.Tooltip(tooltip_html, sticky=True)
        ).add_to(m)

    # Adicionar legenda do mapa de calor
    colormap.add_to(m)

    # Adicionar controle de camadas
    folium.LayerControl().add_to(m)

    # Adicionar plugin de tela cheia
    plugins.Fullscreen(
        position='topleft',
        title='Tela cheia',
        title_cancel='Sair da tela cheia',
        force_separate_button=True
    ).add_to(m)

    return m

@app.route('/')
def index():
    """Renderiza a página principal com o mapa"""
    mapa = create_folium_map()
    mapa_html = mapa._repr_html_()

    return render_template('index.html', mapa=mapa_html)

@app.route('/api/bairros')
def get_bairros():
    """API endpoint para obter dados dos bairros (opcional)"""
    return load_bairros_data()

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=8002)
