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
    page_title="Dashboard de Inversiones Públicas",
    page_icon="💰",
    layout="wide",
)

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
    """
    Normaliza el texto: convierte a minúsculas, quita tildes y caracteres especiales.
    """
    if not isinstance(text, str):
        return text
    text = unicodedata.normalize('NFD', text)
    text = ''.join(c for c in text if unicodedata.category(c) != 'Mn')
    return text.lower().strip()

def load_geojson(path):
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        st.error(f"Error: Archivo GeoJSON no encontrado en '{path}'. Asegúrate de que el archivo 'colombia.geo.json' está en el directorio correcto.")
        return None

def apply_styles():
    st.markdown(f'''
    <style>
        .stApp {{ background-color: {BACKGROUND_COLOR} !important; }}
        [data-testid="stSidebar"] {{ background-color: {SIDEBAR_COLOR} !important; }}
        [data-testid="stSidebar"] h1, [data-testid="stSidebar"] h2, [data-testid="stSidebar"] h3, [data-testid="stSidebar"] h4, [data-testid="stSidebar"] label, [data-testid="stSidebar"] p, [data-testid="stSidebar"] .stMultiSelect, [data-testid="stSidebar"] .stSlider {{ color: white !important; }}
        [data-testid="stMultiSelect"] {{ color: black; }}
        h1, h2, h3, h4, h5, h6 {{ color: {PRIMARY_COLOR}; font-family: 'Segoe UI', sans-serif; }}
        .stMetric {{ background-color: #FFFFFF; border: 1px solid #E0E0E0; border-left: 5px solid {SECONDARY_COLOR}; border-radius: 8px; padding: 1rem; box-shadow: 0 4px 6px rgba(0,0,0,0.05); }}
        .stButton>button {{ background-color: {SECONDARY_COLOR}; color: white; border-radius: 8px; padding: 0.5rem 1rem; border: none; }}
        .stContainer {{ border: 1px solid #D3D3D3; border-radius: 10px; padding: 15px; margin-bottom: 20px; box-shadow: 0 2px 5px rgba(0,0,0,0.05); background-color: #FFFFFF; }}
    </style>
    ''', unsafe_allow_html=True)

@st.cache_data(show_spinner="Cargando datos base desde la API de Socrata...")
def get_base_data():
    """Obtiene todos los datos de 2010 a 2025 para optimizar."""
    query = "$select=vigencia,departamento,municipio,fuentefinanciacion,valorpagado,sectorproyecto,nombreproyecto WHERE vigencia >= '2010' AND vigencia <= '2025'"
    url = f"{BASE_URL}{RESOURCE_ID}.json?{query}&$limit=99999999"
    try:
        response = requests.get(url)
        response.raise_for_status()
        df = pd.DataFrame(response.json())
        df['vigencia'] = pd.to_numeric(df['vigencia'], errors='coerce')
        df['valorpagado'] = pd.to_numeric(df['valorpagado'], errors='coerce')
        return df
    except requests.exceptions.HTTPError as e:
        st.error(f"Error al contactar la API de datos.gov.co: {e}")
        return pd.DataFrame()
    except requests.exceptions.RequestException as e:
        st.error(f"Error de conexión: {e}")
        return pd.DataFrame()

# --- INICIO DE LA APP ---
apply_styles()

df_base = get_base_data()
if df_base.empty:
    st.error("No se pudieron cargar los datos base de la API. La aplicación no puede continuar.")
    st.stop()

# Cargar GeoJSON
geojson_path = "colombia.geo.json"
colombia_geojson = load_geojson(geojson_path)

# --- BARRA LATERAL DE FILTROS ---
st.sidebar.image("https://herramientas.camara.gov.co/htdocs/portal/mifirma/imagen/45.png", width=120)
st.sidebar.title("⚙️ Panel de Filtros Principal")

# 1. FILTRO PRINCIPAL DE VIGENCIA
st.sidebar.header("1. Seleccione el Periodo")
min_year = 2010
max_year = 2025

selected_vigencia_range = st.sidebar.slider(
    "Rango de Vigencias para el Análisis",
    min_value=min_year,
    max_value=max_year,
    value=(min_year, max_year),
    key='selected_vigencia_range'
)

# 2. FILTRAR EL DATAFRAME BASE SEGÚN LA VIGENCIA SELECCIONADA
df_filtered_by_year = df_base[
    (df_base['vigencia'] >= selected_vigencia_range[0]) &
    (df_base['vigencia'] <= selected_vigencia_range[1])
]

# 3. FILTROS SECUNDARIOS
st.sidebar.header("2. Filtros Adicionales")

if st.sidebar.button("🧹 Limpiar Filtros Adicionales"):
    st.session_state.selected_departamentos = []
    st.session_state.selected_municipios = []
    st.session_state.selected_fuentes = []
    st.rerun()

deptos_disponibles = sorted(df_filtered_by_year['departamento'].dropna().unique())
selected_departamentos = st.sidebar.multiselect(
    "Departamento(s)", deptos_disponibles, key='selected_departamentos'
)

if selected_departamentos:
    municipios_disponibles = sorted(df_filtered_by_year[df_filtered_by_year['departamento'].isin(selected_departamentos)]['municipio'].dropna().unique())
else:
    municipios_disponibles = sorted(df_filtered_by_year['municipio'].dropna().unique())
selected_municipios = st.sidebar.multiselect(
    "Municipio(s)", municipios_disponibles, key='selected_municipios'
)

fuentes_disponibles = sorted(df_filtered_by_year['fuentefinanciacion'].dropna().unique())
selected_fuentes = st.sidebar.multiselect(
    "Fuente(s) de Financiación", fuentes_disponibles, key='selected_fuentes'
)

# Aplicar filtros adicionales al dataframe ya filtrado por año
dff = df_filtered_by_year.copy()
if selected_departamentos:
    dff = dff[dff['departamento'].isin(selected_departamentos)]
if selected_municipios:
    dff = dff[dff['municipio'].isin(selected_municipios)]
if selected_fuentes:
    dff = dff[dff['fuentefinanciacion'].isin(selected_fuentes)]

# --- DASHBOARD PRINCIPAL ---
st.markdown("<h1 style='text-align: center;'>DASHBOARD DE INVERSIONES PÚBLICAS</h1>", unsafe_allow_html=True)
st.markdown("<p style='text-align: center;'>Análisis interactivo de la ejecución de recursos públicos en Colombia.</p>", unsafe_allow_html=True)
st.markdown("<p style='text-align: center; font-weight: bold;'>EQUIPO DE ANÁLISIS DE DATOS - UTL SENADOR LEÓN FREDY MUÑOZ</p>", unsafe_allow_html=True)

if dff.empty:
    st.warning("⚠️ No se encontraron datos para los filtros seleccionados.")
    st.stop()

# Métricas Generales
with st.container(border=True):
    st.subheader("📈 Métricas Generales (Según Filtros)")
    col1, col2, col3 = st.columns(3)
    total_pagado = dff['valorpagado'].sum()
    num_proyectos = dff['nombreproyecto'].nunique()
    vigencias_str = f"{selected_vigencia_range[0]} - {selected_vigencia_range[1]}"
    col1.metric(label="💰 Valor Total Pagado (COP)", value=format_number(total_pagado))
    col2.metric(label="🏗️ Número de Proyectos", value=f"{num_proyectos:,}")
    col3.metric(label="🗓️ Rango de Vigencia", value=vigencias_str)

# MAPA GEOGRÁFICO
if colombia_geojson:
    with st.container(border=True):
        st.subheader("🗺️ Distribución Geográfica de la Inversión")
        
        df_map = dff.groupby('departamento')['valorpagado'].sum().reset_index()
        df_map['departamento_norm'] = df_map['departamento'].apply(normalize_text)

        # Normalizar nombres en el GeoJSON para el mapeo
        for feature in colombia_geojson['features']:
            if 'properties' in feature and 'NOMBRE_DPT' in feature['properties']:
                feature['properties']['NOMBRE_DPT_NORM'] = normalize_text(feature['properties']['NOMBRE_DPT'])

        fig_map = px.choropleth_mapbox(
            df_map,
            geojson=colombia_geojson,
            featureidkey="properties.NOMBRE_DPT_NORM",
            locations="departamento_norm",
            color="valorpagado",
            color_continuous_scale=CHART_PALETTE,
            mapbox_style="carto-positron",
            zoom=4,
            center={"lat": 4.5709, "lon": -74.2973},
            opacity=0.7,
            labels={'valorpagado': 'Valor Pagado (COP)'},
            hover_name="departamento",
            hover_data={"valorpagado": ":,.0f"}
        )
        fig_map.update_layout(
            margin={"r":0,"t":0,"l":0,"b":0},
            paper_bgcolor='rgba(0,0,0,0)',
            font_color=TEXT_COLOR
        )
        st.plotly_chart(fig_map, use_container_width=True)

# Gráfico de Inversión por Año
with st.container(border=True):
    st.subheader(f"📈 Inversión por Año ({vigencias_str})")
    inversion_anual = dff.groupby('vigencia')['valorpagado'].sum().reset_index()
    inversion_anual['vigencia'] = inversion_anual['vigencia'].astype(str)
    fig_anual = px.bar(
        inversion_anual, x='vigencia', y='valorpagado',
        text=[format_number(v) for v in inversion_anual['valorpagado']],
        color='vigencia', color_discrete_sequence=CHART_PALETTE
    )
    fig_anual.update_layout(xaxis_title="Vigencia", yaxis_title="Valor Pagado", paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', font_color=TEXT_COLOR)
    st.plotly_chart(fig_anual, use_container_width=True)

# Análisis Comparativo Adaptable
with st.container(border=True):
    st.subheader("📊 Análisis Comparativo por Periodos")
    st.markdown("Los periodos a comparar se limitan al **rango de vigencias principal** que seleccionó en la barra lateral.")
    
    vigencias_en_rango = sorted(df_filtered_by_year['vigencia'].dropna().unique())
    
    if len(vigencias_en_rango) < 2:
        st.warning("Seleccione un rango de al menos dos años en la barra lateral para poder comparar periodos.")
    else:
        col_comp1, col_comp2 = st.columns(2)
        with col_comp1:
            periodo1 = st.select_slider(
                "Primer Periodo",
                options=vigencias_en_rango,
                value=(vigencias_en_rango[0], vigencias_en_rango[1])
            )
        with col_comp2:
            periodo2 = st.select_slider(
                "Segundo Periodo",
                options=vigencias_en_rango,
                value=(vigencias_en_rango[-2], vigencias_en_rango[-1])
            )
        
        # Si hay departamentos seleccionados, el cálculo se basa en ellos. Si no, es el total.
        df_comp = df_filtered_by_year
        if selected_departamentos:
            df_comp = df_comp[df_comp['departamento'].isin(selected_departamentos)]
        
        total_p1 = df_comp[(df_comp['vigencia'] >= periodo1[0]) & (df_comp['vigencia'] <= periodo1[1])]['valorpagado'].sum()
        total_p2 = df_comp[(df_comp['vigencia'] >= periodo2[0]) & (df_comp['vigencia'] <= periodo2[1])]['valorpagado'].sum()

        fig_comp = go.Figure(data=[
            go.Bar(name=f'{periodo1[0]}-{periodo1[1]}', x=['Periodo 1'], y=[total_p1], text=format_number(total_p1), textposition='auto', marker_color=SECONDARY_COLOR),
            go.Bar(name=f'{periodo2[0]}-{periodo2[1]}', x=['Periodo 2'], y=[total_p2], text=format_number(total_p2), textposition='auto', marker_color=PRIMARY_COLOR)
        ])
        fig_comp.update_layout(title_text=f'Comparación de Inversión: {format_number(total_p1)} vs {format_number(total_p2)}', yaxis_title='Valor Pagado (COP)', paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', font_color=TEXT_COLOR)
        st.plotly_chart(fig_comp, use_container_width=True)

# Gráficas Detalladas de Top 10
with st.container(border=True):
    st.subheader("📈 Análisis Detallado por Categoría")
    col_a, col_b = st.columns(2)
    
    top_deptos = dff.groupby('departamento')['valorpagado'].sum().nlargest(10).sort_values(ascending=True)
    top_municipios = dff.groupby('municipio')['valorpagado'].sum().nlargest(10).sort_values(ascending=True)
    top_sectores = dff.groupby('sectorproyecto')['valorpagado'].sum().nlargest(10).sort_values(ascending=True)
    
    with col_a:
        with st.expander("Top 10 Departamentos por Inversión", expanded=True):
            fig_deptos = px.bar(top_deptos, y=top_deptos.index, x='valorpagado', orientation='h', text=[format_number(v) for v in top_deptos.values], color=top_deptos.values, color_continuous_scale=CHART_PALETTE)
            fig_deptos.update_traces(hovertemplate='<b>%{y}</b><br>Valor Pagado: %{x:,.0f} COP<extra></extra>', textposition='outside')
            fig_deptos.update_layout(yaxis_title=None, xaxis_title=None, showlegend=False, paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', yaxis=dict(autorange="reversed"), font_color="black")
            st.plotly_chart(fig_deptos, use_container_width=True)

        with st.expander("Top 10 Sectores por Inversión", expanded=True):
            fig_sectores = px.bar(top_sectores, y=top_sectores.index, x='valorpagado', orientation='h', text=[format_number(v) for v in top_sectores.values], color=top_sectores.values, color_continuous_scale=CHART_PALETTE)
            fig_sectores.update_traces(hovertemplate='<b>%{y}</b><br>Valor Pagado: %{x:,.0f} COP<extra></extra>', textposition='outside')
            fig_sectores.update_layout(yaxis_title=None, xaxis_title=None, showlegend=False, paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', yaxis=dict(autorange="reversed"), font_color="black")
            st.plotly_chart(fig_sectores, use_container_width=True)
    
    with col_b:
        with st.expander("Top 10 Municipios por Inversión", expanded=True):
            fig_municipios = px.bar(top_municipios, y=top_municipios.index, x='valorpagado', orientation='h', text=[format_number(v) for v in top_municipios.values], color=top_municipios.values, color_continuous_scale=CHART_PALETTE)
            fig_municipios.update_traces(hovertemplate='<b>%{y}</b><br>Valor Pagado: %{x:,.0f} COP<extra></extra>', textposition='outside')
            fig_municipios.update_layout(yaxis_title=None, xaxis_title=None, showlegend=False, paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', yaxis=dict(autorange="reversed"), font_color="black")
            st.plotly_chart(fig_municipios, use_container_width=True)
        
        proyectos_por_municipio = dff.groupby('municipio')['nombreproyecto'].nunique().nlargest(10).sort_values(ascending=True)
        with st.expander("Top 10 Municipios por # de Proyectos", expanded=True):
            fig_proy_mun = px.bar(proyectos_por_municipio, y=proyectos_por_municipio.index, x=proyectos_por_municipio.values, orientation='h', text=proyectos_por_municipio.values, color=proyectos_por_municipio.values, color_continuous_scale=CHART_PALETTE)
            fig_proy_mun.update_traces(hovertemplate='<b>%{y}</b><br>Número de Proyectos: %{x:,}<extra></extra>', textposition='outside')
            fig_proy_mun.update_layout(yaxis_title=None, xaxis_title=None, showlegend=False, paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', yaxis=dict(autorange="reversed"), font_color="black")
            st.plotly_chart(fig_proy_mun, use_container_width=True)

with st.container(border=True):
    st.subheader("⬇️ Descargar Datos y Reportes")
    
    def convert_df_to_csv(df):
        return df.to_csv(index=False).encode('utf-8')
    
    csv_data = convert_df_to_csv(dff)
    st.download_button(
        label="📥 Descargar Datos Filtrados (CSV)",
        data=csv_data,
        file_name=f"inversiones_filtradas.csv",
        mime="text/csv",
        help="Descarga el conjunto de datos actual con los filtros aplicados."
    )

    if st.button("🖼️ Crear y Descargar Reporte de Gráficos (PNG)"):
        with st.spinner("Generando reporte de gráficos, por favor espera..."):
            fig_reporte = make_subplots(
                rows=3, cols=2,
                subplot_titles=("Top 10 Departamentos por Inversión", "Top 10 Municipios por Inversión",
                                "Top 10 Sectores por Inversión", "Top 10 Municipios por # de Proyectos",
                                "Inversión por Año", ""),
                vertical_spacing=0.15,
                horizontal_spacing=0.1
            )
            fig_reporte.add_trace(go.Bar(x=top_deptos.values, y=top_deptos.index, orientation='h', name='Deptos', text=[format_number(v) for v in top_deptos.values], marker_color=CHART_PALETTE[0]), row=1, col=1)
            fig_reporte.add_trace(go.Bar(x=top_municipios.values, y=top_municipios.index, orientation='h', name='Mpios', text=[format_number(v) for v in top_municipios.values], marker_color=CHART_PALETTE[1]), row=1, col=2)
            fig_reporte.add_trace(go.Bar(x=top_sectores.values, y=top_sectores.index, orientation='h', name='Sectores', text=[format_number(v) for v in top_sectores.values], marker_color=CHART_PALETTE[2]), row=2, col=1)
            fig_reporte.add_trace(go.Bar(x=proyectos_por_municipio.values, y=proyectos_por_municipio.index, orientation='h', name='Proy/Mpio', text=proyectos_por_municipio.values, marker_color=CHART_PALETTE[3]), row=2, col=2)
            
            inversion_anual_reporte = dff.groupby('vigencia')['valorpagado'].sum().reset_index()
            fig_reporte.add_trace(go.Bar(x=inversion_anual_reporte['vigencia'], y=inversion_anual_reporte['valorpagado'], name='Inv. Anual', marker_color=CHART_PALETTE[4]), row=3, col=1)

            titulo_principal = f"Reporte de Inversiones Públicas - Vigencia(s): {selected_vigencia_range[0]} a {selected_vigencia_range[1]}"
            fig_reporte.update_layout(title_text=titulo_principal, height=1400, width=1600, showlegend=False, paper_bgcolor='#FFFFFF', plot_bgcolor='#FFFFFF', font=dict(color=TEXT_COLOR), colorway=CHART_PALETTE)
            fig_reporte.update_yaxes(autorange="reversed")
            fig_reporte.update_traces(textposition='outside')

            img_bytes = fig_reporte.to_image(format="png", scale=2)
            buf = BytesIO(img_bytes)

            st.success("¡Reporte de gráficos generado! Haz clic en el botón de abajo para descargar.")
            st.download_button(
                label="📥 Descargar Imagen PNG",
                data=buf,
                file_name=f"reporte_inversiones_graficos.png",
                mime="image/png"
            )

with st.container(border=True):
    st.subheader("🔍 Explorador de Proyectos (Según Filtros)")
    st.dataframe(dff, use_container_width=True)

st.markdown("---")
st.markdown("<p style='text-align: center; color: #888;'>Dashboard creado por el Equipo UTL - Senador León Fredy Muñoz</p>", unsafe_allow_html=True)
