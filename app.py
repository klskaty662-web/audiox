import streamlit as st
import pandas as pd
import folium
from streamlit_folium import st_folium
import numpy as np
import os
import io
import openpyxl

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
    st.warning("⚠️ No hay ningún archivo cargado actualmente.")
    
    # --- BOTÓN PARA DESCARGAR PLANTILLA OFICIAL ---
    def generar_plantilla_base():
        output = io.BytesIO()
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Tiendas"
        
        # Columnas estándar requeridas
        columnas = ['CR Tienda', 'Tienda', 'Plaza', 'Asesor', 'lat', 'long']
        for col_idx, col_name in enumerate(columnas, start=1):
            ws.cell(row=1, column=col_idx, value=col_name)
            
        # Ejemplo de fila de muestra
        ejemplo = ['5058A', 'Ejemplo Torreón TRC', 'La Laguna', 'Auditor', 25.5423, -103.4068]
        for col_idx, val in enumerate(ejemplo, start=1):
            ws.cell(row=2, column=col_idx, value=val)
            
        wb.save(output)
        return output.getvalue()

    st.download_button(
        label="📥 Descargar Plantilla Oficial en Blanco (Excel)",
        data=generar_plantilla_base(),
        file_name="Plantilla_Oficial_OXXO.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    st.divider()

    uploaded_file = st.file_uploader("Sube tu archivo Excel mensual o tu plantilla rellenada:", type=['xlsx'])
    if uploaded_file is not None:
        xls = pd.ExcelFile(uploaded_file)
        sheet_names = xls.sheet_names
        selected_sheet = st.selectbox("Selecciona la hoja a procesar:", sheet_names)
        
        df_cargado = pd.read_excel(uploaded_file, sheet_name=selected_sheet)
        
        # --- LIMPIEZA Y NORMALIZACIÓN FLEXIBLE DE COLUMNAS ---
        renombres = {}
        for col in df_cargado.columns:
            col_lower = str(col).strip().lower()
            if 'lat' in col_lower:
                renombres[col] = 'lat'
            elif 'lon' in col_lower or 'long' in col_lower:
                renombres[col] = 'long'
            elif 'cr' in col_lower:
                renombres[col] = 'CR Tienda'
            elif 'tienda' in col_lower or 'sucursal' in col_lower:
                renombres[col] = 'Tienda'
            elif 'plaza' in col_lower:
                renombres[col] = 'Plaza'
            elif 'asesor' in col_lower:
                renombres[col] = 'Asesor'
                
        df_cargado = df_cargado.rename(columns=renombres)
        df_cargado.to_parquet(ARCHIVADO_EXCEL)
        st.success(f"¡Archivo cargado y guardado con éxito! ({len(df_cargado)} tiendas procesadas).")
        st.rerun()

if df is not None:
    if 'lat' not in df.columns or 'long' not in df.columns:
        df['lat'] = None
        df['long'] = None

    df_valid = df.dropna(subset=['lat', 'long']).copy()
    df_valid = df_valid[(df_valid['lat'] != 0) & (df_valid['long'] != 0)]
    
    st.divider()
    
    df_plan_guardado = None
    if os.path.exists(ARCHIVADO_PLAN):
        try:
            df_plan_guardado = pd.read_parquet(ARCHIVADO_PLAN)
        except Exception:
            df_plan_guardado = None

    # --- PESTAÑAS PRINCIPALES ---
    tab_mapa, tab_planificador, tab_pendientes = st.tabs([
        "🗺️ Mapa General", 
        "📅 Planificador y Secuencia de Rutas", 
        "📋 Listado de Tiendas Pendientes"
    ])
    
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

    with tab_pendientes:
        st.subheader("📋 Listado General de Tiendas Pendientes / No Evaluadas")
        st.markdown("Aquí puedes consultar las tiendas pendientes y descargar un archivo compatible para cargarlo posteriormente y crear un nuevo itinerario.")

        if df_plan_guardado is not None:
            pendientes_globales = df_plan_guardado[df_plan_guardado['Estado_Dia'] == 'No Evaluada']
            if len(pendientes_globales) > 0:
                st.warning(f"Se encontraron **{len(pendientes_globales)}** tienda(s) pendiente(s) en total.")
                st.dataframe(
                    pendientes_globales[['Grupo_Dia', 'Orden_Visita', 'CR Tienda', 'Tienda', 'Plaza', 'Asesor', 'distancia_base_km']]
                    .rename(columns={'Grupo_Dia': 'Día Programado', 'Orden_Visita': 'N° Visita', 'distancia_base_km': 'Distancia a Base (km)'})
                )
                
                output = io.BytesIO()
                with pd.ExcelWriter(output, engine='openpyxl') as writer:
                    pendientes_globales.drop(columns=['Grupo_Dia', 'Orden_Visita', 'Evaluada', 'Estado_Dia', 'distancia_base_km'], errors='ignore').to_excel(writer, index=False, sheet_name='Pendientes')
                processed_data = output.getvalue()

                st.download_button(
                    label="📥 Descargar Excel de Tiendas Pendientes (Compatible para nuevo itinerario)",
                    data=processed_data,
                    file_name="tiendas_pendientes_para_nuevo_itinerario.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )
            else:
                st.success("¡Excelente trabajo! No hay tiendas pendientes por evaluar o aún no se ha cerrado ningún día.")
        else:
            st.info("Aún no hay un plan de rutas generado. Ve a la pestaña de planificador para crearlo.")

    with tab_planificador:
        st.subheader("⚙️ Configuración del Plan de Rutas")

        if df_plan_guardado is None:
            c1, c2, c3 = st.columns(3)
            with c1:
                tiendas_por_dia = st.number_input("Tiendas por día (referencia base):", min_value=1, max_value=25, value=6, step=1)
            with c2:
                num_dias = st.number_input("¿Para cuántos días quieres programar?", min_value=1, max_value=30, value=5, step=1)
            with c3:
                tipo_prioridad = st.radio("Preferencia desde tu base:", ["📍 Empezar por Tiendas Cercanas a tu base", "🚗 Empezar por Tiendas Lejanas a tu base"])

            if st.button("🚀 Generar y Guardar Plan de Rutas"):
                if "Cercanas" in tipo_prioridad:
                    df_pool = df_valid.sort_values(by='distancia_base_km', ascending=True).copy()
                else:
                    df_pool = df_valid.sort_values(by='distancia_base_km', ascending=False).copy()
                    
                total_tiendas_disponibles = len(df_pool)

                if total_tiendas_disponibles > 0:
                    lista_final_dias = []
                    pool = df_pool.copy()

                    def ordenar_ruta_dia(grupo_df):
                        if len(grupo_df) <= 1:
                            grupo_df['Orden_Visita'] = 1
                            grupo_df['Evaluada'] = False
                            grupo_df['Estado_Dia'] = 'Pendiente'
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
                        df_ordenado['Evaluada'] = False
                        df_ordenado['Estado_Dia'] = 'Pendiente'
                        return df_ordenado

                    for dia in range(1, int(num_dias) + 1):
                        if len(pool) == 0:
                            break
                        ancla = pool.iloc[0]
                        pool['dist_a_ancla'] = np.sqrt((pool['lat'] - ancla['lat'])**2 + (pool['long'] - ancla['long'])**2)
                        pool = pool.sort_values(by='dist_a_ancla', ascending=True)
                        
                        if dia == int(num_dias):
                            t_totales = len(pool)
                        else:
                            dias_restantes = int(num_dias) - dia + 1
                            t_totales = max(1, int(np.ceil(len(pool) / dias_restantes)))
                        
                        grupo_crudo = pool.head(t_totales).copy()
                        
                        # --- SE REMOVIÓ EL LÍMITE DE 35 KM QUE FORZABA MÁXIMO 5 TIENDAS ---
                        
                        grupo_ordenado = ordenar_ruta_dia(grupo_crudo)
                        grupo_ordenado['Grupo_Dia'] = dia
                        
                        lista_final_dias.append(grupo_ordenado)
                        pool = pool.iloc[t_totales:].copy()

                    df_seleccionadas = pd.concat(lista_final_dias).copy().reset_index(drop=True)
                    df_seleccionadas.to_parquet(ARCHIVADO_PLAN)
                    st.success("¡Plan de rutas generado y guardado exitosamente!")
                    st.rerun()
                else:
                    st.warning("No hay suficientes tiendas con coordenadas para procesar.")
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

            def generar_excel_formato_jefa(df_plan):
                output_jefa = io.BytesIO()
                wb = openpyxl.Workbook()
                ws = wb.active
                ws.title = "Plan Auditorías"
                
                dias_unicos = sorted(df_plan['Grupo_Dia'].unique())
                
                ws.cell(row=4, column=2, value="N°")
                
                col_idx = 4
                for dia_num in dias_unicos:
                    ws.cell(row=4, column=col_idx, value=f"Día {dia_num}")
                    col_idx += 2
                    
                for num_visita in range(1, 16):
                    ws.cell(row=5 + num_visita, column=2, value=num_visita)
                    
                for i, dia_num in enumerate(dias_unicos):
                    grupo = df_plan[df_plan['Grupo_Dia'] == dia_num].sort_values(by='Orden_Visita')
                    col_cr = 4 + i * 2
                    col_nombre = col_cr + 1
                    
                    for _, row_tienda in grupo.iterrows():
                        orden = int(row_tienda['Orden_Visita'])
                        fila_destino = 5 + orden
                        cr_val = str(row_tienda.get('CR Tienda', ''))
                        tienda_val = str(row_tienda.get('Tienda', 'OXXO'))
                        
                        ws.cell(row=fila_destino, column=col_cr, value=cr_val)
                        ws.cell(row=fila_destino, column=col_nombre, value=tienda_val)
                        
                wb.save(output_jefa)
                return output_jefa.getvalue()

            excel_para_jefa = generar_excel_formato_jefa(df_plan_guardado)
            st.download_button(
                label="📊 Descargar Plan en Formato Plantilla (Día 1, Día 2...)",
                data=excel_para_jefa,
                file_name="Plan_Auditorias_Dias_Correlativos.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )

            st.divider()
            st.subheader("🎯 Control de Auditoría Diaria (Checklist y Cierre)")
            
            dias_unicos = sorted(df_plan_guardado['Grupo_Dia'].unique())
            dia_seleccionado = st.selectbox("Elige el día de auditoría a consultar:", dias_unicos, format_func=lambda x: f"Día {x}")

            mask_dia = df_plan_guardado['Grupo_Dia'] == dia_seleccionado
            grupo_activo = df_plan_guardado[mask_dia].sort_values(by='Orden_Visita')

            st.markdown(f"### 📋 Lista de Verificación - Día {dia_seleccionado}")
            st.info("Marca las casillas de las tiendas que **sí se evaluaron** durante la jornada. Al terminar, haz clic en 'Cerrar Día' para enlistar las no evaluadas en la pestaña superior de pendientes.")

            with st.form(key=f"form_dia_{dia_seleccionado}"):
                actualizaciones_estado = []
                
                for idx, row in grupo_activo.iterrows():
                    check_val = bool(row.get('Evaluada', False))
                    cr_tienda = str(row.get('CR Tienda', idx))
                    marcada = st.checkbox(
                        f"Visita #{row['Orden_Visita']} | Tienda: {row.get('Tienda', 'OXXO')} (CR: {cr_tienda}) - A {row['distancia_base_km']:.1f} km de base",
                        value=check_val,
                        key=f"chk_cr_{cr_tienda}_dia_{dia_seleccionado}"
                    )
                    actualizaciones_estado.append({'index': row.name, 'Evaluada': marcada})
                
                btn_cerrar_dia = st.form_submit_button(label="🔒 Cerrar Día y Apartar No Evaluadas")
                
                if btn_cerrar_dia:
                    for item in actualizaciones_estado:
                        i = item['index']
                        val = item['Evaluada']
                        df_plan_guardado.loc[i, 'Evaluada'] = val
                        df_plan_guardado.loc[i, 'Estado_Dia'] = 'Evaluada' if val else 'No Evaluada'
                    
                    df_plan_guardado.to_parquet(ARCHIVADO_PLAN)
                    st.success(f"¡Día {dia_seleccionado} cerrado correctamente! Revisa la pestaña de 'Listado de Tiendas Pendientes'.")
                    st.rerun()

            no_evaluadas = grupo_activo[grupo_activo['Estado_Dia'] == 'No Evaluada']
            evaluadas = grupo_activo[grupo_activo['Estado_Dia'] == 'Evaluada']

            st.divider()
            col_ev, col_no_ev = st.columns(2)
            
            with col_ev:
                st.markdown(f"#### ✅ Tiendas Evaluadas del Día {dia_seleccionado} ({len(evaluadas)})")
                if len(evaluadas) > 0:
                    st.dataframe(evaluadas[['Orden_Visita', 'CR Tienda', 'Tienda', 'Plaza']])
                else:
                    st.caption("Aún no hay tiendas marcadas como evaluadas para este día.")

            with col_no_ev:
                st.markdown(f"#### ⚠️ Pendientes en este Día ({len(no_evaluadas)})")
                if len(no_evaluadas) > 0:
                    st.dataframe(no_evaluadas[['Orden_Visita', 'CR Tienda', 'Tienda', 'Plaza', 'distancia_base_km']])
                else:
                    st.success("¡Sin pendientes en este día o pendiente de cerrar jornada!")

            st.divider()
            if len(grupo_activo) > 0:
                coords_lista = [f"{r['lat']},{r['long']}" for _, r in grupo_activo.iterrows()]
                gmaps_url = f"https://www.google.com/maps/dir/" + "/".join(coords_lista)
                st.markdown(f"🔗 [🧭 Abrir ruta completa de este día en Google Maps (Navegación secuencial)]({gmaps_url})", unsafe_allow_html=True)

            st.subheader(f"🗺️ Mapa Detallado del Día {dia_seleccionado}")
            m_dia = folium.Map(location=[grupo_activo['lat'].mean(), grupo_activo['long'].mean()], zoom_start=13)
            
            folium.Marker(
                [MI_UBICACION_BASE[0], MI_UBICACION_BASE[1]],
                popup="<b>🏠 Tu Base Fija</b>",
                tooltip="Tu Base Fija",
                icon=folium.Icon(color="green", icon="home", prefix="fa")
            ).add_to(m_dia)

            puntos_linea = [[row['lat'], row['long']] for _, row in grupo_activo.iterrows()]
            if len(puntos_linea) > 1:
                folium.PolyLine(puntos_linea, color="blue", weight=3, opacity=0.8).add_to(m_dia)

            for idx, row in grupo_activo.iterrows():
                orden = row['Orden_Visita']
                evaluada_txt = "✅ Evaluada" if row['Estado_Dia'] == 'Evaluada' else "⏳ Pendiente"
                color_icono = "green" if row['Estado_Dia'] == 'Evaluada' else "red"
                popup_txt = f"<b>Parada #{orden}</b><br>{row.get('Tienda', 'OXXO')}<br>Estado: {evaluada_txt}"
                
                folium.Marker(
                    [row['lat'], row['long']],
                    popup=popup_txt,
                    tooltip=f"#{orden}: {row.get('Tienda', 'OXXO')} ({evaluada_txt})",
                    icon=folium.Icon(color=color_icono, icon="info-sign")
                ).add_to(m_dia)

            st_folium(m_dia, width=1100, height=500, key=f"mapa_dia_{dia_seleccionado}")

            csv_plan = df_plan_guardado.to_csv(index=False).encode('utf-8')
            st.download_button(
                label=f"📥 Descargar Plan Completo con Estado de Auditorías",
                data=csv_plan,
                file_name=f"rutas_base_oxxo_evaluaciones.csv",
                mime="text/csv",
            )
