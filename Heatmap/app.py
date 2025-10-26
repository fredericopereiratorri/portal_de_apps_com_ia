import os
import json
from flask import Flask, render_template
import folium
from folium import plugins
import branca.colormap as cm

app = Flask(__name__, static_folder="static", template_folder="templates")

# Carregar dados dos bairros
DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
BAIRROS_FILE = os.path.join(DATA_DIR, "recife_bairros.json")

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

def calculate_poder_aquisitivo(props):
    """Calcula poder aquisitivo baseado em POIs e escolaridade"""
    # Peso maior para shoppings e supermercados
    pois_score = (
        props.get('farmacias', 0) * 1 +
        props.get('shoppings', 0) * 3 +
        props.get('postos_gasolina', 0) * 1 +
        props.get('supermercados', 0) * 2 +
        props.get('escolas', 0) * 0.5
    )

    # Componente de escolaridade (superior tem mais peso)
    educ_score = (
        props.get('ensino_superior_pct', 0) * 3 +
        props.get('ensino_medio_pct', 0) * 1.5
    )

    # Normalizar para escala 0-100
    poder = min(100, (pois_score * 0.6) + (educ_score * 0.4))

    return poder

def classify_poder_aquisitivo(poder):
    """Classifica o poder aquisitivo em Alto/Médio/Baixo"""
    if poder >= 70:
        return "Alto"
    elif poder >= 40:
        return "Médio"
    else:
        return "Baixo"

def get_escolaridade_score(nivel):
    """Converte nível de escolaridade em score numérico"""
    mapping = {
        'Superior': 100,
        'Médio': 60,
        'Fundamental': 30,
        'N/A': 0
    }
    return mapping.get(nivel, 0)

def create_folium_map():
    """Cria o mapa de calor interativo com Folium"""

    # Carregar dados
    bairros_data = load_bairros_data()

    # Configuração do mapa centrado em Recife
    recife_coords = [-8.0476, -34.8770]
    m = folium.Map(
        location=recife_coords,
        zoom_start=12,
        tiles='OpenStreetMap',
        prefer_canvas=True
    )

    # Calcular ranges para cada métrica
    populations = [f['properties']['populacao'] for f in bairros_data['features']]
    min_pop, max_pop = min(populations), max(populations)

    escolaridade_scores = [get_escolaridade_score(f['properties'].get('nivel_escolaridade', 'N/A'))
                          for f in bairros_data['features']]
    min_esc, max_esc = min(escolaridade_scores), max(escolaridade_scores)

    poder_scores = [calculate_poder_aquisitivo(f['properties']) for f in bairros_data['features']]
    min_poder, max_poder = min(poder_scores), max(poder_scores)

    # Criar três feature groups (camadas)
    fg_populacao = folium.FeatureGroup(name='População', show=True)
    fg_escolaridade = folium.FeatureGroup(name='Escolaridade', show=False)
    fg_poder = folium.FeatureGroup(name='Poder Aquisitivo', show=False)

    # Criar colormaps
    colormap_pop = cm.LinearColormap(
        colors=['#00ff00', '#7fff00', '#ffff00', '#ffcc00', '#ff9900', '#ff6600', '#ff3300', '#ff0000', '#cc0000'],
        vmin=min_pop, vmax=max_pop, caption='População (habitantes)'
    )

    colormap_esc = cm.LinearColormap(
        colors=['#00ff00', '#7fff00', '#ffff00', '#ffcc00', '#ff9900', '#ff6600', '#ff3300', '#ff0000', '#cc0000'],
        vmin=min_esc, vmax=max_esc, caption='Escolaridade (score)'
    )

    colormap_poder = cm.LinearColormap(
        colors=['#00ff00', '#7fff00', '#ffff00', '#ffcc00', '#ff9900', '#ff6600', '#ff3300', '#ff0000', '#cc0000'],
        vmin=min_poder, vmax=max_poder, caption='Poder Aquisitivo (score)'
    )

    # Adicionar cada bairro às três camadas
    for feature in bairros_data['features']:
        props = feature['properties']

        # Calcular métricas
        population = props['populacao']
        nivel_escolaridade = props.get('nivel_escolaridade', 'N/A')
        esc_score = get_escolaridade_score(nivel_escolaridade)
        poder_score = calculate_poder_aquisitivo(props)
        poder_classificado = classify_poder_aquisitivo(poder_score)

        # Cores para cada camada
        color_pop = colormap_pop(population)
        color_esc = colormap_esc(esc_score)
        color_poder = colormap_poder(poder_score)

        # Criar tooltip
        tooltip_html = f"""
        <div style="font-family: Arial; font-size: 13px; max-width: 320px; padding: 5px;">
            <h3 style="margin: 0 0 12px 0; color: #2c3e50; border-bottom: 2px solid #3498db; padding-bottom: 5px;">
                📍 {props['nome']}
            </h3>

            <div style="margin-bottom: 12px; padding: 8px; background: linear-gradient(135deg, #f5f7fa 0%, #c3cfe2 100%); border-radius: 5px; border-left: 4px solid #3498db;">
                <b style="color: #2c3e50;">📊 Dados do bairro</b><br>
                <div style="margin-top: 6px; line-height: 1.6;">
                    <span style="color: #555;">População:</span> <b style="color: #2c3e50;">{props['populacao']:,}</b> hab<br>
                    <span style="color: #555;">Escolaridade:</span> <b style="color: #2c3e50;">{nivel_escolaridade}</b><br>
                    <span style="color: #555;">Poder Aquisitivo:</span> <b style="color: #e67e22;">{poder_classificado}</b>
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

        # Adicionar à camada de população
        folium.GeoJson(
            feature,
            style_function=lambda x, color=color_pop: {
                'fillColor': color, 'color': '#333333', 'weight': 2,
                'fillOpacity': 0.6, 'opacity': 0.8
            },
            highlight_function=lambda x: {'fillOpacity': 0.8, 'weight': 3},
            tooltip=folium.Tooltip(tooltip_html, sticky=True)
        ).add_to(fg_populacao)

        # Adicionar à camada de escolaridade
        folium.GeoJson(
            feature,
            style_function=lambda x, color=color_esc: {
                'fillColor': color, 'color': '#333333', 'weight': 2,
                'fillOpacity': 0.6, 'opacity': 0.8
            },
            highlight_function=lambda x: {'fillOpacity': 0.8, 'weight': 3},
            tooltip=folium.Tooltip(tooltip_html, sticky=True)
        ).add_to(fg_escolaridade)

        # Adicionar à camada de poder aquisitivo
        folium.GeoJson(
            feature,
            style_function=lambda x, color=color_poder: {
                'fillColor': color, 'color': '#333333', 'weight': 2,
                'fillOpacity': 0.6, 'opacity': 0.8
            },
            highlight_function=lambda x: {'fillOpacity': 0.8, 'weight': 3},
            tooltip=folium.Tooltip(tooltip_html, sticky=True)
        ).add_to(fg_poder)

    # Adicionar feature groups ao mapa
    fg_populacao.add_to(m)
    fg_escolaridade.add_to(m)
    fg_poder.add_to(m)

    # Adicionar as três legendas com IDs únicos
    # População
    m.get_root().html.add_child(folium.Element(f'''
        <style>
            #legend-pop, #legend-esc, #legend-poder {{
                position: absolute;
                top: 10px;
                right: 10px;
                z-index: 1000;
                background: white;
                padding: 10px;
                border-radius: 5px;
                box-shadow: 0 0 15px rgba(0,0,0,0.2);
            }}
            #legend-esc, #legend-poder {{
                display: none;
            }}
        </style>
    '''))

    colormap_pop_html = colormap_pop._repr_html_()
    m.get_root().html.add_child(folium.Element(f'<div id="legend-pop">{colormap_pop_html}</div>'))

    colormap_esc_html = colormap_esc._repr_html_()
    m.get_root().html.add_child(folium.Element(f'<div id="legend-esc">{colormap_esc_html}</div>'))

    colormap_poder_html = colormap_poder._repr_html_()
    m.get_root().html.add_child(folium.Element(f'<div id="legend-poder">{colormap_poder_html}</div>'))

    # Adicionar controle de camadas
    folium.LayerControl().add_to(m)

    # Adicionar plugin de tela cheia
    plugins.Fullscreen(
        position='topleft',
        title='Tela cheia',
        title_cancel='Sair da tela cheia',
        force_separate_button=True
    ).add_to(m)

    # Adicionar painel lateral customizado
    custom_html = """
    <style>
        .heat-selector {
            position: fixed;
            top: 80px;
            right: 20px;
            background: white;
            padding: 15px 20px;
            border-radius: 10px;
            box-shadow: 0 4px 12px rgba(0,0,0,0.2);
            z-index: 1000;
            font-family: Arial, sans-serif;
            min-width: 200px;
        }
        .heat-selector h4 {
            margin: 0 0 12px 0;
            color: #2c3e50;
            font-size: 14px;
            font-weight: 600;
            border-bottom: 2px solid #3498db;
            padding-bottom: 8px;
        }
        .heat-selector label {
            display: block;
            padding: 8px 5px;
            cursor: pointer;
            color: #555;
            font-size: 13px;
            transition: all 0.2s;
            border-radius: 5px;
        }
        .heat-selector label:hover {
            background: #f0f0f0;
        }
        .heat-selector input[type="radio"] {
            margin-right: 8px;
            cursor: pointer;
        }
        .heat-selector input[type="radio"]:checked + span {
            color: #3498db;
            font-weight: 600;
        }
    </style>

    <div class="heat-selector">
        <h4>🗺️ Tipo de Mapa de Calor</h4>
        <label>
            <input type="radio" name="heat" value="populacao" checked>
            <span>População</span>
        </label>
        <label>
            <input type="radio" name="heat" value="escolaridade">
            <span>Escolaridade</span>
        </label>
        <label>
            <input type="radio" name="heat" value="poder">
            <span>Poder Aquisitivo</span>
        </label>
    </div>

    <script>
        // Aguardar o mapa carregar
        setTimeout(function() {
            var radios = document.querySelectorAll('input[name="heat"]');

            // Função para alternar camadas e legendas
            function toggleLayers(selectedValue) {
                // Encontrar todos os layer controls
                var layerControl = document.querySelector('.leaflet-control-layers');
                if (!layerControl) return;

                // Encontrar inputs de camadas
                var inputs = layerControl.querySelectorAll('input[type="checkbox"]');

                inputs.forEach(function(input) {
                    var label = input.parentElement.querySelector('span');
                    if (!label) return;

                    var layerName = label.textContent.trim();

                    // Determinar se deve estar visível
                    var shouldBeVisible = false;
                    if (selectedValue === 'populacao' && layerName === 'População') {
                        shouldBeVisible = true;
                    } else if (selectedValue === 'escolaridade' && layerName === 'Escolaridade') {
                        shouldBeVisible = true;
                    } else if (selectedValue === 'poder' && layerName === 'Poder Aquisitivo') {
                        shouldBeVisible = true;
                    }

                    // Alternar se necessário
                    if (input.checked !== shouldBeVisible) {
                        input.click();
                    }
                });

                // Alternar legendas usando IDs específicos
                var legendPop = document.getElementById('legend-pop');
                var legendEsc = document.getElementById('legend-esc');
                var legendPoder = document.getElementById('legend-poder');

                if (legendPop && legendEsc && legendPoder) {
                    // Ocultar todas primeiro
                    legendPop.style.display = 'none';
                    legendEsc.style.display = 'none';
                    legendPoder.style.display = 'none';

                    // Mostrar apenas a selecionada
                    if (selectedValue === 'populacao') {
                        legendPop.style.display = 'block';
                    } else if (selectedValue === 'escolaridade') {
                        legendEsc.style.display = 'block';
                    } else if (selectedValue === 'poder') {
                        legendPoder.style.display = 'block';
                    }
                }
            }

            // Adicionar listeners aos radio buttons
            radios.forEach(function(radio) {
                radio.addEventListener('change', function() {
                    toggleLayers(this.value);
                });
            });
        }, 1000);
    </script>
    """

    from branca.element import Element
    m.get_root().html.add_child(Element(custom_html))

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
