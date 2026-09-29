from datetime import datetime
import os
import io
sqlite3 = __import__("sqlite3")
pd = __import__("pandas")
st = __import__("streamlit")

# --- CONFIGURACIÓN DE TEMA CLARO ---
st.set_page_config(
    page_title="Medisuport - Sistema Clínico", page_icon="🏥", layout="wide"
)

st.markdown("""
    <style>
    .main { background-color: #FFFFFF; color: #000000; }
    .stSidebar { background-color: #F8F9FA; }
    </style>
    """, unsafe_allow_html=True)

# --- BASE DE DATOS Y TABLAS ---
def init_db():
  conn = sqlite3.connect("clinica.db", check_same_thread=False)
  cursor = conn.cursor()
  
  cursor.execute("""
        CREATE TABLE IF NOT EXISTS pacientes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cedula TEXT UNIQUE NOT NULL,
            nombre TEXT NOT NULL,
            telefono TEXT,
            fecha_nacimiento TEXT,
            origen TEXT
        )
    """)
  
  cursor.execute("""
        CREATE TABLE IF NOT EXISTS citas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cedula_paciente TEXT,
            fecha TEXT,
            hora TEXT,
            medico TEXT,
            especialidad TEXT,
            FOREIGN KEY(cedula_paciente) REFERENCES pacientes(cedula)
        )
    """)
    
  cursor.execute("""
        CREATE TABLE IF NOT EXISTS historial (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cedula_paciente TEXT,
            fecha_atencion TEXT,
            medico_atn TEXT,
            tipo_consulta TEXT,
            motivo TEXT,
            diagnostico TEXT,
            receta TEXT,
            FOREIGN KEY(cedula_paciente) REFERENCES pacientes(cedula)
        )
    """)
  
  cursor.execute("PRAGMA table_info(pacientes)")
  p_cols = [col[1] for col in cursor.fetchall()]
  if "origen" not in p_cols:
    cursor.execute("ALTER TABLE pacientes ADD COLUMN origen TEXT")

  cursor.execute("PRAGMA table_info(historial)")
  h_cols = [col[1] for col in cursor.fetchall()]
  if "tipo_consulta" not in h_cols:
    cursor.execute("ALTER TABLE historial ADD COLUMN tipo_consulta TEXT")

  conn.commit()
  conn.close()

init_db()

# --- DICCIONARIO DE MÉDICOS Y ESPECIALIDADES ---
MEDICOS_ESPECIALIDADES = {
    "Alergología": ["Dra. Kanie Collado"],
    "Anestesiología": ["Dr. Norberto Carballosa"],
    "Cardiología": ["Dra. Lisset Alfonso"],
    "Dermatología": ["Dr. Miguel Mederos"],
    "Endocrinología": ["Dr. Frank Medina", "Dr. Miguel Marrero", "Dra. Gabriela Vélez"],
    "Fisiatría": ["Dr. Pavel Mili", "Dr. Yunio Torres"],
    "Gastroenterología": ["Dr. Frank Pérez"],
    "Geriatría": ["Dra. Mildred"],
    "Ginecología": ["Dr. Alejandro Argiz", "Dra. Marilyn Martínez"],
    "Logopedia": ["Dra. Osmarie Barbosa"],
    "Medicina General": ["Dr. Yoandis Pérez", "Dra. Ailicec Arias", "Dra. Osmarie Barbosa"],
    "Medicina Interna": ["Dr. Ovadiz Pérez"],
    "Neumología": ["Dra. Eva Barbosa"],
    "Neurología": ["Dr. Dayron Douglas Calvo"],
    "Nutrición": ["Lcdo. Andrés Hidrobo"],
    "Otorrinolaringología": ["Dr. Fernando Enríquez"],
    "Pediatría": ["Dra. Ailicec Arias", "Dra. María Cristina Torres"],
    "Psicología": ["Lcdo. Jerson Rodríguez"],
    "Psiquiatría": ["Dra. Yulca Rosales"],
    "Reumatología": ["Dr. Dennis Pucha", "Dr. Rafael Echavarría"],
    "Traumatología": ["Dr. Antonio Leal"],
    "Urología": ["Dr. William Fonseca"]
}

# --- SISTEMA DE AUTENTICACIÓN POR ROLES ---
USERS = {
    "Abigail Ruiz (Secretaria)": {"pass": "sec2026", "role": "secretaria"},
    "Administrador": {"pass": "admin2026", "role": "admin"},
    # Médicos
    "Dra. Kanie Collado (Alergología)": {"pass": "med123", "role": "medico"},
    "Dr. Norberto Carballosa (Anestesiología)": {"pass": "med123", "role": "medico"},
    "Dra. Lisset Alfonso (Cardiología)": {"pass": "med123", "role": "medico"},
    "Dr. Miguel Mederos (Dermatología)": {"pass": "med123", "role": "medico"},
    "Dr. Frank Medina (Endocrinología)": {"pass": "med123", "role": "medico"},
    "Dr. Miguel Marrero (Endocrinología)": {"pass": "med123", "role": "medico"},
    "Dra. Gabriela Vélez (Endocrinología)": {"pass": "med123", "role": "medico"},
    "Dr. Pavel Mili (Fisiatría)": {"pass": "med123", "role": "medico"},
    "Dr. Yunio Torres (Fisiatría)": {"pass": "med123", "role": "medico"},
    "Dr. Frank Pérez (Gastroenterología)": {"pass": "med123", "role": "medico"},
    "Dra. Mildred (Geriatría)": {"pass": "med123", "role": "medico"},
    "Dr. Alejandro Argiz (Ginecología)": {"pass": "med123", "role": "medico"},
    "Dra. Marilyn Martínez (Ginecología)": {"pass": "med123", "role": "medico"},
    "Dra. Osmarie Barbosa (Logopedia / Med. General)": {"pass": "med123", "role": "medico"},
    "Dr. Yoandis Pérez (Medicina General)": {"pass": "med123", "role": "medico"},
    "Dra. Ailicec Arias (Pediatría / Med. General)": {"pass": "med123", "role": "medico"},
    "Dr. Ovadiz Pérez (Medicina Interna)": {"pass": "med123", "role": "medico"},
    "Dra. Eva Barbosa (Neumología)": {"pass": "med123", "role": "medico"},
    "Dr. Dayron Douglas Calvo (Neurología)": {"pass": "med123", "role": "medico"},
    "Lcdo. Andrés Hidrobo (Nutrición)": {"pass": "med123", "role": "medico"},
    "Dr. Fernando Enríquez (Otorrinolaringología)": {"pass": "med123", "role": "medico"},
    "Dra. María Cristina Torres (Pediatría)": {"pass": "med123", "role": "medico"},
    "Lcdo. Jerson Rodríguez (Psicología)": {"pass": "med123", "role": "medico"},
    "Dra. Yulca Rosales (Psiquiatría)": {"pass": "med123", "role": "medico"},
    "Dr. Dennis Pucha (Reumatología)": {"pass": "med123", "role": "medico"},
    "Dr. Rafael Echavarría (Reumatología)": {"pass": "med123", "role": "medico"},
    "Dr. Antonio Leal (Traumatología)": {"pass": "med123", "role": "medico"},
    "Dr. William Fonseca (Urología)": {"pass": "med123", "role": "medico"}
}

if "logged_in" not in st.session_state:
  st.session_state["logged_in"] = False
  st.session_state["user_name"] = ""
  st.session_state["user_role"] = ""

if not st.session_state["logged_in"]:
  st.title("🏥 Medisuport - Control de Acceso")
  st.write("Seleccione su perfil e ingrese su contraseña para continuar.")
  
  with st.form("login_form"):
    selected_user = st.selectbox("Seleccionar Usuario / Rol", list(USERS.keys()))
    password_input = st.text_input("Contraseña", type="password")
    submit_login = st.form_submit_button("Ingresar al Sistema")
    
    if submit_login:
      if password_input == USERS[selected_user]["pass"]:
        st.session_state["logged_in"] = True
        st.session_state["user_name"] = selected_user
        st.session_state["user_role"] = USERS[selected_user]["role"]
        st.rerun()
      else:
        st.error("Contraseña incorrecta. Intente nuevamente.")
  st.stop()

# --- BARRA LATERAL Y NAVEGACIÓN ---
st.sidebar.title("Medisuport 🏥")
st.sidebar.write(f"👤 **Usuario:** {st.session_state['user_name']}")
if st.sidebar.button("Cerrar Sesión"):
  st.session_state["logged_in"] = False
  st.rerun()

st.sidebar.divider()
role = st.session_state["user_role"]

if role == "secretaria":
  menu = ["👤 Registrar / Buscar Paciente", "📋 Listado de Pacientes", "📅 Agenda y Citas", "📥 Respaldo y Datos"]
elif role == "medico":
  menu = ["📋 Listado de Pacientes", "🩺 Consulta Médica (Historial)", "📅 Ver Agenda de Citas"]
else:  # Admin
  menu = ["👤 Registrar / Buscar Paciente", "📋 Listado de Pacientes", "📅 Agenda y Citas", "🩺 Consulta Médica (Historial)", "📥 Respaldo y Datos"]

choice = st.sidebar.selectbox("Seleccione opción", menu)

# --- MÓDULO: PACIENTES (REGISTRAR) ---
if choice == "👤 Registrar / Buscar Paciente":
  st.subheader("Gestión y Registro de Pacientes - Medisuport")
  with st.form("form_paciente"):
    cedula = st.text_input("Número de Cédula")
    nombre = st.text_input("Nombre Completo del Paciente")
    telefono = st.text_input("Teléfono / Celular")
    f_nac = st.date_input("Fecha de Nacimiento", datetime(1990, 1, 1))
    origen = st.selectbox("Origen del Paciente", ["Propio de la Clínica", "Prestador Externo ISSFA"])
    guardar = st.form_submit_button("Guardar Paciente")
    
    if guardar:
      if cedula and nombre:
        try:
          conn = sqlite3.connect("clinica.db", check_same_thread=False)
          cursor = conn.cursor()
          cursor.execute("INSERT INTO pacientes (cedula, nombre, telefono, fecha_nacimiento, origen) VALUES (?, ?, ?, ?, ?)",
                         (cedula, nombre, telefono, str(f_nac), origen))
          conn.commit()
          conn.close()
          st.success(f"Paciente {nombre} registrado con éxito ({origen}).")
        except sqlite3.IntegrityError:
          st.error("Error: Ya existe un paciente registrado con esta cédula.")
      else:
        st.warning("Complete la cédula y el nombre.")

# --- MÓDULO: LISTADO Y CONTROL DE PACIENTES CON C1 / SUB ---
elif choice == "📋 Listado de Pacientes":
  st.subheader("📋 Base de Datos y Conteo de Visitas de Pacientes - Medisuport")
  
  conn = sqlite3.connect("clinica.db", check_same_thread=False)
  cursor = conn.cursor()
  cursor.execute("SELECT id, cedula, nombre, telefono, fecha_nacimiento, origen FROM pacientes")
  pacientes_raw = cursor.fetchall()
  conn.close()

  if pacientes_raw:
    data_tabla = []
    conn = sqlite3.connect("clinica.db", check_same_thread=False)
    cursor = conn.cursor()

    for p in pacientes_raw:
      p_id, cedula, nombre, telefono, f_nac, origen = p
      cursor.execute("SELECT COUNT(*) FROM historial WHERE cedula_paciente = ?", (cedula,))
      total_visitas = cursor.fetchone()[0]
      
      codigo_actual = "C1" if total_visitas == 0 else "SUB"

      data_tabla.append({
          "Cédula": cedula,
          "Nombre del Paciente": nombre,
          "Teléfono": telefono,
          "Fecha Nacimiento": f_nac,
          "Origen": origen if origen else "Propio de la Clínica",
          "Total Visitas": total_visitas,
          "Código Asignado": codigo_actual
      })
    
    conn.close()
    df_p = pd.DataFrame(data_tabla)

    st.dataframe(df_p, use_container_width=True)
    
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
      df_p.to_excel(writer, sheet_name='Reporte_Pacientes', index=False)
    excel_pacientes = output.getvalue()

    st.download_button(
        label="📥 Descargar Listado de Pacientes con Códigos en Excel (.xlsx)",
        data=excel_pacientes,
        file_name=f"medisuport_listado_pacientes_{datetime.now().strftime('%Y-%m-%d')}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

    st.divider()
    
    if role in ["secretaria", "admin"]:
      with st.expander("🗑️ Eliminar Paciente (Corrección por Error)"):
        st.warning("⚠️ Atención: Al eliminar un paciente, también se borrarán sus citas e historial clínico asociado.")
        pacientes_del = {f"{row['Nombre del Paciente']} (Cédula: {row['Cédula']})": row['Cédula'] for _, row in df_p.iterrows()}
        
        selected_to_delete = st.selectbox("Seleccione el paciente a eliminar", list(pacientes_del.keys()))
        cedula_a_borrar = pacientes_del[selected_to_delete]
        
        confirmacion = st.text_input("Escriba 'ELIMINAR' para confirmar la acción")
        if st.button("Borrar Registro de Paciente", type="primary"):
          if confirmacion == "ELIMINAR":
            conn = sqlite3.connect("clinica.db", check_same_thread=False)
            cursor = conn.cursor()
            cursor.execute("DELETE FROM historial WHERE cedula_paciente = ?", (cedula_a_borrar,))
            cursor.execute("DELETE FROM citas WHERE cedula_paciente = ?", (cedula_a_borrar,))
            cursor.execute("DELETE FROM pacientes WHERE cedula = ?", (cedula_a_borrar,))
            conn.commit()
            conn.close()
            st.success(f"El paciente con cédula {cedula_a_borrar} ha sido eliminado del sistema.")
            st.rerun()
          else:
            st.error("Debe escribir 'ELIMINAR' exactamente para confirmar.")
  else:
    st.info("No hay pacientes registrados en el sistema.")

# --- MÓDULO: AGENDA Y CITAS CON VERIFICACIÓN DE OCUPADO Y LLAVES DINÁMICAS ---
elif choice in ["📅 Agenda y Citas", "📅 Ver Agenda de Citas"]:
  st.subheader("Agenda Médica Virtual - Medisuport")
  
  if role in ["secretaria", "admin"]:
    conn = sqlite3.connect("clinica.db", check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute("SELECT cedula, nombre FROM pacientes")
    pacientes = cursor.fetchall()
    conn.close()
    pacientes_dict = {f"{p[1]} (Cédula: {p[0]})": p[0] for p in pacientes}

    # Contenedor fuera del formulario para permitir actualización dinámica de médicos según la especialidad
    st.write("Agendar Nueva Cita (Verificación automática de disponibilidad)")
    if pacientes_dict:
      paciente_sel = st.selectbox("Seleccionar Paciente", list(pacientes_dict.keys()), key="select_paciente_cita")
      cedula_act = pacientes_dict[paciente_sel]
    else:
      st.warning("Debe registrar pacientes primero.")
      cedula_act = ""

    # Selección de Especialidad con key para refrescar automáticamente los médicos
    especialidad_sel = st.selectbox("Especialidad Médica", list(MEDICOS_ESPECIALIDADES.keys()), key="select_especialidad_cita")
    medicos_disponibles = MEDICOS_ESPECIALIDADES[especialidad_sel]
    medico_sel = st.selectbox("Médico Tratante", medicos_disponibles, key="select_medico_cita")

    with st.form("form_cita_real"):
      col1, col2 = st.columns(2)
      with col1:
        fecha_cita = st.date_input("Fecha de la Cita", datetime.now())
      with col2:
        hora_cita = st.time_input("Hora de la Cita")

      submitted = st.form_submit_button("Agendar Cita")
      
      if submitted and cedula_act:
        str_fecha = str(fecha_cita)
        str_hora = str(hora_cita)
        
        # VERIFICAR SI EL MÉDICO YA TIENE OCUPADO ESE HORARIO
        conn = sqlite3.connect("clinica.db", check_same_thread=False)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT COUNT(*) FROM citas 
            WHERE medico = ? AND fecha = ? AND hora = ?
        """, (medico_sel, str_fecha, str_hora))
        conf_count = cursor.fetchone()[0]
        conn.close()

        if conf_count > 0:
          st.error(f"❌ **Horario No Disponible:** El/La Dr(a). {medico_sel} ya tiene una cita agendada para el día **{str_fecha}** a las **{str_hora}**. Por favor seleccione otra hora o médico.")
        else:
          conn = sqlite3.connect("clinica.db", check_same_thread=False)
          cursor = conn.cursor()
          cursor.execute("""
              INSERT INTO citas (cedula_paciente, fecha, hora, medico, especialidad) 
              VALUES (?, ?, ?, ?, ?)
          """, (cedula_act, str_fecha, str_hora, medico_sel, especialidad_sel))
          conn.commit()
          conn.close()
          st.success(f"✅ ¡Cita agendada con éxito para el Dr(a). {medico_sel} el {str_fecha} a las {str_hora}!")
    st.divider()

  st.subheader("Listado de Citas Registradas")
  conn = sqlite3.connect("clinica.db", check_same_thread=False)
  cursor = conn.cursor()
  if role == "medico":
    nombre_sesion = st.session_state['user_name']
    cursor.execute("""
        SELECT c.fecha, c.hora, p.nombre, c.medico, c.especialidad 
        FROM citas c JOIN pacientes p ON c.cedula_paciente = p.cedula 
        WHERE c.medico LIKE ?
    """, (f"%{nombre_sesion.split(' ')[1]}%",))
  else:
    cursor.execute("""
        SELECT c.fecha, c.hora, p.nombre, c.medico, c.especialidad 
        FROM citas c JOIN pacientes p ON c.cedula_paciente = p.cedula
    """)
  citas_data = cursor.fetchall()
  conn.close()
  
  if citas_data:
    df_citas_view = pd.DataFrame(citas_data, columns=["Fecha", "Hora", "Paciente", "Médico", "Especialidad"])
    st.dataframe(df_citas_view, use_container_width=True)
  else:
    st.info("No hay citas registradas en el sistema.")

# --- MÓDULO: CONSULTA MÉDICA E HISTORIAL ---
elif choice == "🩺 Consulta Médica (Historial)":
  st.subheader("Atención Médica y Evolución - Medisuport")
  conn = sqlite3.connect("clinica.db", check_same_thread=False)
  cursor = conn.cursor()
  cursor.execute("SELECT cedula, nombre FROM pacientes")
  pacientes = cursor.fetchall()
  conn.close()
  pacientes_dict = {f"{p[1]} (Cédula: {p[0]})": p[0] for p in pacientes}

  if pacientes_dict:
    paciente_sel = st.selectbox("Seleccione Paciente a Atender", list(pacientes_dict.keys()))
    cedula_paciente = pacientes_dict[paciente_sel]

    conn = sqlite3.connect("clinica.db", check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM pacientes WHERE cedula = ?", (cedula_paciente,))
    p_info = cursor.fetchone()
    
    cursor.execute("SELECT COUNT(*) FROM historial WHERE cedula_paciente = ?", (cedula_paciente,))
    conteo_atenciones = cursor.fetchone()[0]
    conn.close()

    tipo_consulta_auto = "C1" if conteo_atenciones == 0 else "SUB"

    st.info(f"**Paciente:** {p_info[2]} | **Cédula:** {p_info[1]} | **Origen:** {p_info[5] if len(p_info) > 5 and p_info[5] else 'No especificado'}")
    st.warning(f"📊 **Historial de visitas:** Ha asistido {conteo_atenciones} vez/veces previa(s). **Código Asignado para esta Consulta:** `{tipo_consulta_auto}` ({'Primera Vez' if tipo_consulta_auto == 'C1' else 'Subsecuente'})")

    with st.form("form_atencion"):
      st.write("Evolución, Diagnóstico y Receta")
      motivo = st.text_area("Motivo de Consulta")
      diagnostico = st.text_area("Diagnóstico Clínico")
      receta = st.text_area("Tratamiento / Receta Médica")
      finalizar = st.form_submit_button("Guardar Atención Médica")

      if finalizar:
        conn = sqlite3.connect("clinica.db", check_same_thread=False)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO historial (cedula_paciente, fecha_atencion, medico_atn, tipo_consulta, motivo, diagnostico, receta) 
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (cedula_paciente, datetime.now().strftime("%Y-%m-%d %H:%M"), st.session_state['user_name'], tipo_consulta_auto, motivo, diagnostico, receta))
        conn.commit()
        conn.close()
        st.success(f"¡Atención guardada correctamente con código {tipo_consulta_auto}!")
        st.rerun()

    st.divider()
    st.subheader("Historial de Consultas Anteriores")
    conn = sqlite3.connect("clinica.db", check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute("SELECT fecha_atencion, medico_atn, tipo_consulta, motivo, diagnostico, receta FROM historial WHERE cedula_paciente = ? ORDER BY id DESC", (cedula_paciente,))
    historicos = cursor.fetchall()
    conn.close()

    if historicos:
      for h in historicos:
        with st.expander(f"Fecha: {h[0]} | Código: {h[2]} | Médico: {h[1]}"):
          st.write(f"**Motivo:** {h[3]}")
          st.write(f"**Diagnóstico:** {h[4]}")
          st.write(f"**Receta:** {h[5]}")
    else:
      st.info("No hay registros previos para este paciente. Esta consulta se registrará como C1.")
  else:
    st.warning("No hay pacientes registrados.")

# --- MÓDULO: RESPALDO Y DATOS ---
elif choice in ["📥 Respaldo y Datos"]:
  st.subheader("Respaldo y Reportes en Excel - Medisuport")
  st.write("Genera y descarga un archivo de Excel (`.xlsx`) con toda la información general de la clínica.")

  if st.button("Generar Reporte Excel Completo"):
    conn = sqlite3.connect("clinica.db", check_same_thread=False)
    df_pacientes = pd.read_sql_query("SELECT * FROM pacientes", conn)
    df_citas = pd.read_sql_query("SELECT * FROM citas", conn)
    df_historial = pd.read_sql_query("SELECT * FROM historial", conn)
    conn.close()

    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
      df_pacientes.to_excel(writer, sheet_name='Pacientes', index=False)
      df_citas.to_excel(writer, sheet_name='Citas', index=False)
      df_historial.to_excel(writer, sheet_name='Historial', index=False)
    
    excel_data = output.getvalue()

    st.success("¡Reporte generado con éxito!")
    st.download_button(
        label="📥 Descargar Reporte Completo Medisuport (.xlsx)",
        data=excel_data,
        file_name=f"medisuport_respaldo_completo_{datetime.now().strftime('%Y-%m-%d')}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
