import streamlit as st
import pandas as pd
import folium
from streamlit_folium import st_folium
import numpy as np
import os

st.set_page_config(page_title="Auditorías OXXO - Rutas y Secuencia", layout="wide")

ARCHIVADO_EXCEL = "datos_guardados_oxxo.parquet"
ARCHIVADO_PLAN = "plan_generado_oxxo.parquet"

st.title("📍 Planificador Inteligente de Auditorías OXXO (La Laguna)")
st.markdown("Agrupa tus tiendas por vecindad, calcula la **secuencia de visita (1, 2, 3...)** y **guarda tu plan de rutas** para que no se borre al cambiar de día o recargar.")

# --- UBICACIÓN BASE FIJA ESTABLECIDA ---
MI_UBICACION_BASE = (25.502065, -103.413063)

st.sidebar.header("🏠 Tu Ubicación Base Fija")
st.sidebar.success("Coordenadas fijas:\nLat: 25.502065\nLon: -103.413063")

st.sidebar.divider()
st.sidebar.header("🔄 Gestión de Documento")
if st.sidebar.button("🗑️ Borrar documento y cargar nuevo Excel"):
    if os.path.exists(ARCHIVADO_EXCEL):
        os.remove(ARCHIVADO_EXCEL)
    if os.path.exists(ARCHIVADO_PLAN):
        os.remove(ARCHIVADO_PLAN)
    st.session_state.clear()
    st.rerun()

df = None

if os.path.exists(ARCHIVADO_EXCEL):
    try:
        df = pd.read_parquet(ARCHIVADO_EXCEL)
        st.info("ℹ️ **Se han cargado los datos guardados previamente.** Tu lista de tiendas está guardada. Usa el botón lateral solo si deseas cambiar de archivo Excel.")
    except Exception:
        df = None

if df is None:
    uploaded_file = st.file_uploader("Sube tu archivo Excel mensual (ej. Tiendas Laguna P11.xlsx)", type=['xlsx'])
    if uploaded_file is not None:
        xls = pd.ExcelFile(uploaded_file)
        sheet_names = xls.sheet_names
        selected_sheet = st.selectbox("Selecciona la hoja a procesar:", sheet_names)
        
        df_cargado = pd.read_excel(uploaded_file, sheet_name=selected_sheet)
        df_cargado.to_parquet(ARCHIVADO_EXCEL)
        st.success(f"¡Archivo cargado y guardado con éxito! ({len(df_cargado)} tiendas).")
        st.rerun()

if df is not None:
    if 'lat' not in df.columns or 'long' not in df.columns:
        df['lat'] = None
        df['long'] = None

    df_valid = df.dropna(subset=['lat', 'long']).copy()
    df_valid = df_valid[(df_valid['lat'] != 0) & (df_valid['long'] != 0)]
    
    st.divider()
    
    tab_mapa, tab_planificador = st.tabs(["🗺️ Mapa General", "📅 Planificador y Secuencia de Rutas"])
    
    def calcular_distancia_base(row):
        lat1, lon1 = np.radians(MI_UBICACION_BASE[0]), np.radians(MI_UBICACION_BASE[1])
        lat2, lon2 = np.radians(row['lat']), np.radians(row['long'])
        dlat = lat2 - lat1
        dlon = lon2 - lon1
        a = np.sin(dlat / 2.0)**2 + np.cos(lat1) * np.cos(lat2) * np.sin(dlon / 2.0)**2
        return 6367 * (2 * np.arcsin(np.sqrt(a)))

    df_valid['distancia_base_km'] = df_valid.apply(calcular_distancia_base, axis=1)

    with tab_mapa:
        st.subheader("Ubicación General de Tiendas y tu Base")
        m_gen = folium.Map(location=[MI_UBICACION_BASE[0], MI_UBICACION_BASE[1]], zoom_start=12)
        
        folium.Marker(
            [MI_UBICACION_BASE[0], MI_UBICACION_BASE[1]],
            popup="<b>🏠 Mi Ubicación Base Fija</b>",
            tooltip="Mi Ubicación Base",
            icon=folium.Icon(color="green", icon="home", prefix="fa")
        ).add_to(m_gen)

        for idx, row in df_valid.iterrows():
            folium.Marker(
                [row['lat'], row['long']],
                popup=f"<b>{row.get('Tienda', 'OXXO')}</b><br>Distancia a tu base: {row['distancia_base_km']:.1f} km",
                tooltip=row.get('Tienda', 'OXXO'),
                icon=folium.Icon(color="red", icon="shopping-cart", prefix="fa")
            ).add_to(m_gen)
        st_folium(m_gen, width=1100, height=450, key="mapa_general")

    with tab_planificador:
        st.subheader("⚙️ Configuración del Plan de Rutas")
        
        # Comprobar si ya existe un plan guardado previamente
        df_plan_guardado = None
        if os.path.exists(ARCHIVADO_PLAN):
            try:
                df_plan_guardado = pd.read_parquet(ARCHIVADO_PLAN)
            except Exception:
                df_plan_guardado = None

        if df_plan_guardado is None:
            c1, c2, c3 = st.columns(3)
            with c1:
                tiendas_por_dia = st.number_input("Tiendas por día:", min_value=1, max_value=25, value=6, step=1)
            with c2:
                num_dias = st.number_input("¿Para cuántos días quieres programar?", min_value=1, max_value=30, value=5, step=1)
            with c3:
                tipo_prioridad = st.radio("Preferencia desde tu base:", ["📍 Empezar por Tiendas Cercanas a tu base", "🚗 Empezar por Tiendas Lejanas a tu base"])

            if st.button("🚀 Generar y Guardar Plan de Rutas"):
                if "Cercanas" in tipo_prioridad:
                    df_pool = df_valid.sort_values(by='distancia_base_km', ascending=True).copy()
                else:
                    df_pool = df_valid.sort_values(by='distancia_base_km', ascending=False).copy()
                    
                total_tiendas_necesarias = int(tiendas_por_dia * num_dias)

                if len(df_pool) >= total_tiendas_necesarias:
                    lista_final_dias = []
                    pool = df_pool.copy()

                    def ordenar_ruta_dia(grupo_df):
                        if len(grupo_df) <= 1:
                            grupo_df['Orden_Visita'] = 1
                            return grupo_df
                        pendientes = grupo_df.copy().reset_index(drop=True)
                        ordenados = []
                        actual = pendientes.iloc[0]
                        ordenados.append(actual)
                        pendientes = pendientes.drop(0).reset_index(drop=True)
                        
                        while len(pendientes) > 0:
                            pendientes['dist'] = np.sqrt((pendientes['lat'] - actual['lat'])**2 + (pendientes['long'] - actual['long'])**2)
                            idx_cercana = pendientes['dist'].idxmin()
                            actual = pendientes.loc[idx_cercana]
                            ordenados.append(actual)
                            pendientes = pendientes.drop(idx_cercana).reset_index(drop=True)
                            
                        df_ordenado = pd.DataFrame(ordenados)
                        df_ordenado['Orden_Visita'] = range(1, len(df_ordenado) + 1)
                        return df_ordenado

                    for dia in range(1, int(num_dias) + 1):
                        if len(pool) == 0:
                            break
                        ancla = pool.iloc[0]
                        pool['dist_a_ancla'] = np.sqrt((pool['lat'] - ancla['lat'])**2 + (pool['long'] - ancla['long'])**2)
                        pool = pool.sort_values(by='dist_a_ancla', ascending=True)
                        
                        t_totales = min(int(tiendas_por_dia), len(pool))
                        grupo_crudo = pool.head(t_totales).copy()
                        
                        grupo_ordenado = ordenar_ruta_dia(grupo_crudo)
                        grupo_ordenado['Grupo_Dia'] = dia
                        
                        lista_final_dias.append(grupo_ordenado)
                        pool = pool.iloc[t_totales:].copy()

                    df_seleccionadas = pd.concat(lista_final_dias).copy()
                    df_seleccionadas.to_parquet(ARCHIVADO_PLAN)
                    st.success("¡Plan de rutas generado y guardado exitosamente!")
                    st.rerun()
                else:
                    st.warning("No hay suficientes tiendas con coordenadas para cubrir esa cantidad de días y tiendas por día.")
        else:
            col_info, col_btn = st.columns([3, 1])
            with col_info:
                dias_totales = df_plan_guardado['Grupo_Dia'].max()
                tiendas_totales = len(df_plan_guardado)
                st.success(f"🔒 **Plan Guardado Activo:** {tiendas_totales} tiendas programadas para **{dias_totales} días**. Este plan no se borrará al recargar.")
            with col_btn:
                if st.button("🔄 Borrar Filtro / Generar Nuevo Plan"):
                    if os.path.exists(ARCHIVADO_PLAN):
                        os.remove(ARCHIVADO_PLAN)
                    st.rerun()

            st.divider()
            st.subheader("🎯 Selecciona un Día para ver su Ruta Óptima y Secuencia")
            
            dias_unicos = sorted(df_plan_guardado['Grupo_Dia'].unique())
            dia_seleccionado = st.selectbox("Elige el día de auditoría a consultar:", dias_unicos, format_func=lambda x: f"Día {x}")

            grupo_activo = df_plan_guardado[df_plan_guardado['Grupo_Dia'] == dia_seleccionado].sort_values(by='Orden_Visita')

            st.markdown(f"### 📋 Secuencia de Visita para el Día {dia_seleccionado}")
            st.dataframe(grupo_activo[['Orden_Visita', 'CR Tienda', 'Tienda', 'Plaza', 'Asesor', 'distancia_base_km', 'lat', 'long']].rename(columns={'Orden_Visita': 'N° de Visita', 'distancia_base_km': 'Distancia a tu Base (km)'}))

            if len(grupo_activo) > 0:
                coords_lista = []
                for _, r in grupo_activo.iterrows():
                    coords_lista.append(f"{r['lat']},{r['long']}")
                gmaps_url = f"https://www.google.com/maps/dir/" + "/".join(coords_lista)
                st.markdown(f"🔗 [🧭 Abrir ruta completa de este día en Google Maps (Navegación secuencial)]({gmaps_url})", unsafe_allow_html=True)

            st.divider()
            st.subheader(f"🗺️ Mapa Detallado del Día {dia_seleccionado} (Secuencia desde tu Base)")

            m_dia = folium.Map(location=[grupo_activo['lat'].mean(), grupo_activo['long'].mean()], zoom_start=13)
            
            folium.Marker(
                [MI_UBICACION_BASE[0], MI_UBICACION_BASE[1]],
                popup="<b>🏠 Tu Base Fija</b>",
                tooltip="Tu Base Fija",
                icon=folium.Icon(color="green", icon="home", prefix="fa")
            ).add_to(m_dia)

            puntos_linea = []
            for idx, row in grupo_activo.iterrows():
                puntos_linea.append([row['lat'], row['long']])
                
            if len(puntos_linea) > 1:
                folium.PolyLine(puntos_linea, color="blue", weight=3, opacity=0.8).add_to(m_dia)

            for idx, row in grupo_activo.iterrows():
                orden = row['Orden_Visita']
                popup_txt = f"<b>Parada #{orden}</b><br>{row.get('Tienda', 'OXXO')}<br>A {row['distancia_base_km']:.1f} km de tu base"
                folium.Marker(
                    [row['lat'], row['long']],
                    popup=popup_txt,
                    tooltip=f"#{orden}: {row.get('Tienda', 'OXXO')}",
                    icon=folium.Icon(color="red", icon="info-sign")
                ).add_to(m_dia)

            st_folium(m_dia, width=1100, height=500, key=f"mapa_dia_{dia_seleccionado}")

            csv_plan = df_plan_guardado.to_csv(index=False).encode('utf-8')
            st.download_button(
                label=f"📥 Descargar Plan Completo con Referencia Base",
                data=csv_plan,
                file_name=f"rutas_base_oxxo_guardadas.csv",
                mime="text/csv",
            )
