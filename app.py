import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import requests
from io import BytesIO
import json
import unicodedata

# --- CONFIGURACIÓN DE LA PÁGINA ---
st.set_page_config(
    page_title="Dashboard de Inversiones Públicas (con Inflación)",
    page_icon="inflation",
    layout="wide",
)

# --- DATOS DE INFLACIÓN (IPC ANUAL COLOMBIA) ---
# Fuente: DANE, via gerencie.com, consultorcontable.com
IPC_ANUAL = {
    2010: 3.17, 2011: 3.73, 2012: 2.44, 2013: 1.94, 2014: 3.66, 2015: 6.77,
    2016: 5.75, 2017: 4.09, 2018: 3.18, 2019: 3.80, 2020: 1.61, 2021: 5.62,
    2022: 13.12, 2023: 9.28, 2024: 5.20 # Nota: El valor de 2024 puede ser parcial/proyectado
}
BASE_YEAR_INFLATION = 2023

# --- PALETA DE COLORES Y ESTILOS ---
PRIMARY_COLOR = "#1A5276"
SECONDARY_COLOR = "#5DADE2"
BACKGROUND_COLOR = "#F4F6F7"
TEXT_COLOR = "#212F3D"
SIDEBAR_COLOR = "#2C3E50"
CHART_PALETTE = ['#D6EBEC', '#7AD8DF', '#51D2DA', '#34AAB6', '#3D7688', '#306F83']

# --- CONFIGURACIÓN DE LA API DE SOCRATA ---
BASE_URL = "https://www.datos.gov.co/resource/"
RESOURCE_ID = "u3qu-swda" # ID de Gasto Público en Inversión

# --- FUNCIONES DE APOYO ---
def format_number(num):
    if abs(num) >= 1_000_000_000_000:
        return f"${num / 1_000_000_000_000:,.2f} B"
    if abs(num) >= 1_000_000:
        return f"${num / 1_000_000:,.1f} M"
    if abs(num) >= 1_000:
        return f"${num / 1_000:,.1f} K"
    return f"${num:,.0f}"

def normalize_text(text):
    if not isinstance(text, str):
        return text
    text = unicodedata.normalize('NFD', text)
    text = ''.join(c for c in text if unicodedata.category(c) != 'Mn')
    return text.lower().strip()

def get_inflation_factors(ipc_data, base_year):
    factors = {}
    ipc_index = {min(ipc_data.keys()) - 1: 100}
    for year in sorted(ipc_data.keys()):
        ipc_index[year] = ipc_index[year - 1] * (1 + ipc_data[year] / 100)
    
    base_ipc = ipc_index.get(base_year)
    if not base_ipc:
        st.warning(f"Año base {base_year} para inflación no encontrado. No se aplicará el ajuste.")
        return None

    for year, index_val in ipc_index.items():
        factors[year] = base_ipc / index_val
    return factors

def load_geojson(path):
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        st.warning(f"Advertencia: Archivo GeoJSON no encontrado en '{path}'. El mapa no se mostrará.")
        return None

def apply_styles():
    st.markdown(f'''
    <style>
        .stApp {{ background-color: {BACKGROUND_COLOR} !important; }}
        [data-testid="stSidebar"] {{ background-color: {SIDEBAR_COLOR} !important; }}
        [data-testid="stSidebar"] h1, [data-testid="stSidebar"] h2, [data-testid="stSidebar"] h3, [data-testid="stSidebar"] h4, [data-testid="stSidebar"] label, [data-testid="stSidebar"] p, [data-testid="stSidebar"] .stMultiSelect, [data-testid="stSidebar"] .stSlider, [data-testid="stSidebar"] .stToggle {{ color: white !important; }}
        [data-testid="stMultiSelect"] {{ color: black; }}
        h1, h2, h3, h4, h5, h6 {{ color: {PRIMARY_COLOR}; font-family: 'Segoe UI', sans-serif; }}
        .stMetric {{ background-color: #FFFFFF; border: 1px solid #E0E0E0; border-left: 5px solid {SECONDARY_COLOR}; border-radius: 8px; padding: 1rem; box-shadow: 0 4px 6px rgba(0,0,0,0.05); }}
        .stButton>button {{ background-color: {SECONDARY_COLOR}; color: white; border-radius: 8px; padding: 0.5rem 1rem; border: none; }}
        .stContainer {{ border: 1px solid #D3D3D3; border-radius: 10px; padding: 15px; margin-bottom: 20px; box-shadow: 0 2px 5px rgba(0,0,0,0.05); background-color: #FFFFFF; }}
    </style>
    ''', unsafe_allow_html=True)

@st.cache_data(show_spinner="Cargando datos base desde la API de Socrata...")
def get_base_data():
    query = "$select=vigencia,departamento,municipio,fuentefinanciacion,valorpagado,sectorproyecto,nombreproyecto WHERE vigencia >= '2010' AND vigencia <= '2025'"
    url = f"{BASE_URL}{RESOURCE_ID}.json?{query}&$limit=99999999"
    try:
        response = requests.get(url)
        response.raise_for_status()
        df = pd.DataFrame(response.json())
        df['vigencia'] = pd.to_numeric(df['vigencia'], errors='coerce')
        df['valorpagado'] = pd.to_numeric(df['valorpagado'], errors='coerce')
        df.dropna(subset=['vigencia', 'valorpagado'], inplace=True)
        df['vigencia'] = df['vigencia'].astype(int)
        return df
    except Exception as e:
        st.error(f"Ocurrió un error al cargar los datos: {e}")
        return pd.DataFrame()

# --- INICIO DE LA APP ---
apply_styles()

df_base = get_base_data()
if df_base.empty:
    st.error("No se pudieron cargar los datos base. La aplicación no puede continuar.")
    st.stop()

# Cargar GeoJSON
geojso_path = "colombia.geo.json"
colombia_geojson = load_geojson(geojso_path)

# --- BARRA LATERAL DE FILTROS ---
st.sidebar.image("https://herramientas.camara.gov.co/htdocs/portal/mifirma/imagen/45.png", width=120)
st.sidebar.title("⚙️ Panel de Filtros Principal")

# 1. FILTRO PRINCIPAL DE VIGENCIA
st.sidebar.header("1. Seleccione el Periodo")
selected_vigencia_range = st.sidebar.slider(
    "Rango de Vigencias", 2010, 2025, (2010, 2025), key='selected_vigencia_range'
)

# 2. FILTROS SECUNDARIOS
st.sidebar.header("2. Filtros Geográficos y de Fuente")
if st.sidebar.button("🧹 Limpiar Filtros Adicionales"):
    st.session_state.selected_departamentos = []
    st.session_state.selected_municipios = []
    st.session_state.selected_fuentes = []
    st.rerun()

df_filtered_by_year = df_base[
    (df_base['vigencia'] >= selected_vigencia_range[0]) &
    (df_base['vigencia'] <= selected_vigencia_range[1])
]

deptos_disponibles = sorted(df_filtered_by_year['departamento'].dropna().unique())
selected_departamentos = st.sidebar.multiselect("Departamento(s)", deptos_disponibles, key='selected_departamentos')

if selected_departamentos:
    municipios_disponibles = sorted(df_filtered_by_year[df_filtered_by_year['departamento'].isin(selected_departamentos)]['municipio'].dropna().unique())
else:
    municipios_disponibles = sorted(df_filtered_by_year['municipio'].dropna().unique())
selected_municipios = st.sidebar.multiselect("Municipio(s)", municipios_disponibles, key='selected_municipios')

fuentes_disponibles = sorted(df_filtered_by_year['fuentefinanciacion'].dropna().unique())
selected_fuentes = st.sidebar.multiselect("Fuente(s) de Financiación", fuentes_disponibles, key='selected_fuentes')

# 3. AJUSTE DE INFLACIÓN
st.sidebar.header("3. Ajustes de Visualización")
adjust_inflation = st.sidebar.toggle(
    "📊 Ajustar por Inflación (Valor Real)",
    value=False,
    help=f"Calcula los valores monetarios en pesos equivalentes al año {BASE_YEAR_INFLATION} para una comparación real."
)

# --- PROCESAMIENTO DE DATOS PRINCIPAL ---
dff = df_filtered_by_year.copy()
if selected_departamentos:
    dff = dff[dff['departamento'].isin(selected_departamentos)]
if selected_municipios:
    dff = dff[dff['municipio'].isin(selected_municipios)]
if selected_fuentes:
    dff = dff[dff['fuentefinanciacion'].isin(selected_fuentes)]

valor_columna = 'valorpagado'
display_mode = "(Nominal)"

if adjust_inflation:
    inflation_factors = get_inflation_factors(IPC_ANUAL, BASE_YEAR_INFLATION)
    if inflation_factors:
        dff['valorpagado_ajustado'] = dff.apply(
            lambda row: row['valorpagado'] * inflation_factors.get(row['vigencia'], 1),
            axis=1
        )
        valor_columna = 'valorpagado_ajustado'
        display_mode = f"(Real, base {BASE_YEAR_INFLATION})"

# --- DASHBOARD PRINCIPAL ---
st.markdown(f"<h1 style='text-align: center;'>DASHBOARD DE INVERSIONES PÚBLICAS {display_mode}</h1>", unsafe_allow_html=True)
st.markdown("<p style='text-align: center;'>Análisis interactivo de la ejecución de recursos públicos en Colombia.</p>", unsafe_allow_html=True)
st.markdown("<p style='text-align: center; font-weight: bold;'>EQUIPO DE ANÁLISIS DE DATOS - UTL SENADOR LEÓN FREDY MUÑOZ</p>", unsafe_allow_html=True)

if dff.empty:
    st.warning("⚠️ No se encontraron datos para los filtros seleccionados.")
    st.stop()

# Métricas Generales
with st.container(border=True):
    st.subheader(f"📈 Métricas Generales {display_mode}")
    col1, col2, col3 = st.columns(3)
    total_pagado = dff[valor_columna].sum()
    num_proyectos = dff['nombreproyecto'].nunique()
    vigencias_str = f"{selected_vigencia_range[0]} - {selected_vigencia_range[1]}"
    col1.metric(label=f"💰 Valor Total Pagado {display_mode}", value=format_number(total_pagado))
    col2.metric(label="🏗️ Número de Proyectos", value=f"{num_proyectos:,}")
    col3.metric(label="🗓️ Rango de Vigencia", value=vigencias_str)

# MAPA GEOGRÁFICO
if colombia_geojson:
    with st.container(border=True):
        st.subheader(f"🗺️ Distribución Geográfica de la Inversión {display_mode}")
        df_map = dff.groupby('departamento')[valor_columna].sum().reset_index()
        df_map['departamento_norm'] = df_map['departamento'].apply(normalize_text)

        for feature in colombia_geojson['features']:
            if 'properties' in feature and 'NOMBRE_DPT' in feature['properties']:
                feature['properties']['NOMBRE_DPT_NORM'] = normalize_text(feature['properties']['NOMBRE_DPT'])

        fig_map = px.choropleth_mapbox(
            df_map,
            geojson=colombia_geojson,
            featureidkey="properties.NOMBRE_DPT_NORM",
            locations="departamento_norm",
            color=valor_columna,
            color_continuous_scale=CHART_PALETTE,
            mapbox_style="carto-positron",
            zoom=4, center={"lat": 4.5709, "lon": -74.2973}, opacity=0.7,
            labels={valor_columna: f'Valor Pagado {display_mode}'},
            hover_name="departamento", hover_data={valor_columna: ":,.0f"}
        )
        fig_map.update_layout(margin={"r":0,"t":0,"l":0,"b":0}, paper_bgcolor='rgba(0,0,0,0)', font_color=TEXT_COLOR)
        st.plotly_chart(fig_map, use_container_width=True)

# Gráfico de Inversión por Año
with st.container(border=True):
    st.subheader(f"📈 Inversión por Año {display_mode}")
    inversion_anual = dff.groupby('vigencia')[valor_columna].sum().reset_index()
    inversion_anual['vigencia'] = inversion_anual['vigencia'].astype(str)
    fig_anual = px.bar(
        inversion_anual, x='vigencia', y=valor_columna,
        text=[format_number(v) for v in inversion_anual[valor_columna]],
        color='vigencia', color_discrete_sequence=CHART_PALETTE
    )
    fig_anual.update_layout(xaxis_title="Vigencia", yaxis_title=f"Valor Pagado {display_mode}", paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', font_color=TEXT_COLOR)
    st.plotly_chart(fig_anual, use_container_width=True)

# Análisis Comparativo por Periodos
with st.container(border=True):
    st.subheader(f"📊 Análisis Comparativo por Periodos {display_mode}")

    # --- Selección de Periodos para Comparación ---
    st.markdown("Seleccione los dos periodos que desea comparar. Los filtros geográficos y de fuente aplicados arriba también afectarán este análisis.")
    
    # CORRECTED LOGIC: Use the main filtered year range for the comparison sliders
    min_year, max_year = selected_vigencia_range[0], selected_vigencia_range[1]

    # Ensure default values are valid
    default_p1_end = min_year + 1 if min_year + 1 <= max_year else max_year
    default_p2_start = max_year - 1 if max_year - 1 >= min_year else min_year

    col_p1, col_p2 = st.columns(2)
    with col_p1:
        st.markdown("##### Periodo 1")
        periodo1_range = st.slider(
            "Rango de años para el Periodo 1",
            min_year, max_year,
            (min_year, default_p1_end), # Corrected default
            key='periodo1_slider'
        )

    with col_p2:
        st.markdown("##### Periodo 2")
        periodo2_range = st.slider(
            "Rango de años para el Periodo 2",
            min_year, max_year,
            (default_p2_start, max_year), # Corrected default
            key='periodo2_slider'
        )

    # Filtrar el dataframe `dff` (que ya tiene los filtros principales y el ajuste de inflación) para cada periodo
    df_p1 = dff[
        (dff['vigencia'] >= periodo1_range[0]) &
        (dff['vigencia'] <= periodo1_range[1])
    ]
    total_p1 = df_p1[valor_columna].sum()

    df_p2 = dff[
        (dff['vigencia'] >= periodo2_range[0]) &
        (dff['vigencia'] <= periodo2_range[1])
    ]
    total_p2 = df_p2[valor_columna].sum()

    # --- Visualización de la Comparación ---
    if total_p1 > 0 or total_p2 > 0:
        # Métricas
        comp_col1, comp_col2, comp_col3 = st.columns(3)
        comp_col1.metric(
            label=f"Total Invertido en Periodo 1 ({periodo1_range[0]}-{periodo1_range[1]})",
            value=format_number(total_p1)
        )
        comp_col2.metric(
            label=f"Total Invertido en Periodo 2 ({periodo2_range[0]}-{periodo2_range[1]})",
            value=format_number(total_p2)
        )

        # Cálculo de la diferencia
        diferencia = total_p2 - total_p1
        if total_p1 > 0:
            diferencia_percent = (diferencia / total_p1) * 100
            comp_col3.metric(
                label="Diferencia (P2 vs P1)",
                value=format_number(diferencia),
                delta=f"{diferencia_percent:.2f}%"
            )
        else:
             comp_col3.metric(
                label="Diferencia (P2 vs P1)",
                value=format_number(diferencia),
                delta="N/A"
            )

        # Gráfico de Barras Comparativo
        df_comparacion = pd.DataFrame({
            'Periodo': [f"Periodo 1 ({periodo1_range[0]}-{periodo1_range[1]})", f"Periodo 2 ({periodo2_range[0]}-{periodo2_range[1]})"],
            'Total Invertido': [total_p1, total_p2]
        })
        
        fig_comp = px.bar(
            df_comparacion,
            x='Periodo',
            y='Total Invertido',
            color='Periodo',
            color_discrete_sequence=[PRIMARY_COLOR, SECONDARY_COLOR],
            text=[format_number(v) for v in df_comparacion['Total Invertido']],
            title=f"Comparación de Inversión Total {display_mode}"
        )
        fig_comp.update_layout(
            showlegend=False,
            yaxis_title=f"Valor Pagado {display_mode}",
            xaxis_title=None,
            paper_bgcolor='rgba(0,0,0,0)',
            plot_bgcolor='rgba(0,0,0,0)',
            font_color=TEXT_COLOR
        )
        st.plotly_chart(fig_comp, use_container_width=True)
    else:
        st.info("No se encontraron datos en los periodos seleccionados para realizar la comparación.")

# Gráficas Detalladas de Top 10
with st.container(border=True):
    st.subheader(f"📈 Análisis Detallado por Categoría {display_mode}")
    col_a, col_b = st.columns(2)
    
    top_deptos = dff.groupby('departamento')[valor_columna].sum().nlargest(10).sort_values(ascending=True)
    top_municipios = dff.groupby('municipio')[valor_columna].sum().nlargest(10).sort_values(ascending=True)
    top_sectores = dff.groupby('sectorproyecto')[valor_columna].sum().nlargest(10).sort_values(ascending=True)
    
    with col_a:
        with st.expander(f"Top 10 Departamentos por Inversión {display_mode}", expanded=True):
            fig_deptos = px.bar(top_deptos, y=top_deptos.index, x=top_deptos.values, orientation='h', text=[format_number(v) for v in top_deptos.values], color=top_deptos.values, color_continuous_scale=CHART_PALETTE)
            fig_deptos.update_layout(yaxis_title=None, xaxis_title=None, showlegend=False, paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', font_color="black")
            st.plotly_chart(fig_deptos, use_container_width=True)

        with st.expander(f"Top 10 Sectores por Inversión {display_mode}", expanded=True):
            fig_sectores = px.bar(top_sectores, y=top_sectores.index, x=top_sectores.values, orientation='h', text=[format_number(v) for v in top_sectores.values], color=top_sectores.values, color_continuous_scale=CHART_PALETTE)
            fig_sectores.update_layout(yaxis_title=None, xaxis_title=None, showlegend=False, paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', font_color="black")
            st.plotly_chart(fig_sectores, use_container_width=True)
    
    with col_b:
        with st.expander(f"Top 10 Municipios por Inversión {display_mode}", expanded=True):
            fig_municipios = px.bar(top_municipios, y=top_municipios.index, x=top_municipios.values, orientation='h', text=[format_number(v) for v in top_municipios.values], color=top_municipios.values, color_continuous_scale=CHART_PALETTE)
            fig_municipios.update_layout(yaxis_title=None, xaxis_title=None, showlegend=False, paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', font_color="black")
            st.plotly_chart(fig_municipios, use_container_width=True)
        
        proyectos_por_municipio = dff.groupby('municipio')['nombreproyecto'].nunique().nlargest(10).sort_values(ascending=True)
        with st.expander("Top 10 Municipios por # de Proyectos", expanded=True):
            fig_proy_mun = px.bar(proyectos_por_municipio, y=proyectos_por_municipio.index, x=proyectos_por_municipio.values, orientation='h', text=proyectos_por_municipio.values, color=proyectos_por_municipio.values, color_continuous_scale=CHART_PALETTE)
            fig_proy_mun.update_layout(yaxis_title=None, xaxis_title=None, showlegend=False, paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', font_color="black")
            st.plotly_chart(fig_proy_mun, use_container_width=True)

# ... (resto de la app, como descargas y tabla de datos)

with st.container(border=True):
    st.subheader("🔍 Explorador de Proyectos (Según Filtros)")
    st.dataframe(dff, use_container_width=True)

st.markdown("---")
st.markdown("<p style='text-align: center; color: #888;'>Dashboard creado por el Equipo UTL - Senador León Fredy Muñoz</p>", unsafe_allow_html=True)
