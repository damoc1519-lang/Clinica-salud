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
  
  # Tabla de pacientes con origen y campos necesarios
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
    
  # Historial con soporte para código de consulta (C1 o SUB)
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
  
  # Verificación de seguridad para bases de datos existentes
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

# --- SISTEMA DE AUTENTICACIÓN POR ROLES ---
USERS = {
    "Secretaria (Recepción)": {"pass": "sec2026", "role": "secretaria"},
    "Dr. Pérez (Medicina General)": {"pass": "med123", "role": "medico"},
    "Dra. Gómez (Pediatría)": {"pass": "med456", "role": "medico"},
    "Administrador": {"pass": "admin2026", "role": "admin"}
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
  menu = ["👤 Registrar / Buscar Paciente", "📅 Agenda y Citas", "📥 Respaldo y Datos"]
elif role == "medico":
  menu = ["🩺 Consulta Médica (Historial)", "📅 Ver Agenda de Citas"]
else:  # Admin
  menu = ["👤 Registrar / Buscar Paciente", "📅 Agenda y Citas", "🩺 Consulta Médica (Historial)", "📥 Respaldo y Datos"]

choice = st.sidebar.selectbox("Seleccione opción", menu)

# --- MÓDULO: PACIENTES ---
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

  st.divider()
  st.subheader("Directorio de Pacientes Registrados")
  conn = sqlite3.connect("clinica.db", check_same_thread=False)
  df_p = pd.read_sql_query("SELECT cedula, nombre, telefono, fecha_nacimiento, origen FROM pacientes", conn)
  conn.close()
  if not df_p.empty:
    st.dataframe(df_p, use_container_width=True)
  else:
    st.info("No hay pacientes registrados aún.")

# --- MÓDULO: AGENDA Y CITAS ---
elif choice in ["📅 Agenda y Citas", "📅 Ver Agenda de Citas"]:
  st.subheader("Agenda Médica Virtual - Medisuport")
  
  if role in ["secretaria", "admin"]:
    conn = sqlite3.connect("clinica.db", check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute("SELECT cedula, nombre FROM pacientes")
    pacientes = cursor.fetchall()
    conn.close()
    pacientes_dict = {f"{p[1]} (Cédula: {p[0]})": p[0] for p in pacientes}

    with st.form("form_cita"):
      st.write("Agendar Nueva Cita")
      if pacientes_dict:
        paciente_sel = st.selectbox("Seleccionar Paciente", list(pacientes_dict.keys()))
        cedula_act = pacientes_dict[paciente_sel]
      else:
        st.warning("Debe registrar pacientes primero.")
        cedula_act = ""

      fecha = st.date_input("Fecha de la Cita", datetime.now())
      hora = st.time_input("Hora de la Cita")
      medico = st.selectbox("Médico Asignado", ["Dr. Pérez (Medicina General)", "Dra. Gómez (Pediatría)"])
      especialidad = st.selectbox("Especialidad", ["Medicina General", "Pediatría"])

      submitted = st.form_submit_button("Agendar Cita")
      if submitted and cedula_act:
        conn = sqlite3.connect("clinica.db", check_same_thread=False)
        cursor = conn.cursor()
        cursor.execute("INSERT INTO citas (cedula_paciente, fecha, hora, medico, especialidad) VALUES (?, ?, ?, ?, ?)",
                       (cedula_act, str(fecha), str(hora), medico, especialidad))
        conn.commit()
        conn.close()
        st.success("¡Cita agendada correctamente!")
    st.divider()

  st.subheader("Citas Registradas")
  conn = sqlite3.connect("clinica.db", check_same_thread=False)
  cursor = conn.cursor()
  if role == "medico":
    cursor.execute("SELECT c.fecha, c.hora, p.nombre, c.medico, c.especialidad FROM citas c JOIN pacientes p ON c.cedula_paciente = p.cedula WHERE c.medico LIKE ?", (f"%{st.session_state['user_name'].split(' ')[1]}%",))
  else:
    cursor.execute("SELECT c.fecha, c.hora, p.nombre, c.medico, c.especialidad FROM citas c JOIN pacientes p ON c.cedula_paciente = p.cedula")
  citas_data = cursor.fetchall()
  conn.close()
  if citas_data:
    st.table(citas_data)
  else:
    st.info("No hay citas registradas.")

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

    # Contar cuantas atenciones previas tiene en el historial
    conn = sqlite3.connect("clinica.db", check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM pacientes WHERE cedula = ?", (cedula_paciente,))
    p_info = cursor.fetchone()
    
    cursor.execute("SELECT COUNT(*) FROM historial WHERE cedula_paciente = ?", (cedula_paciente,))
    conteo_atenciones = cursor.fetchone()[0]
    conn.close()

    # Lógica automática del código de consulta: C1 si es la primera, SUB si ya ha asistido
    if conteo_atenciones == 0:
      tipo_consulta_auto = "C1 (Primera Vez)"
    else:
      tipo_consulta_auto = "SUB (Subsecuente / Control)"

    st.info(f"**Paciente:** {p_info[2]} | **Cédula:** {p_info[1]} | **Origen:** {p_info[4] if len(p_info) > 4 and p_info[4] else 'No especificado'}")
    st.warning(f"📊 **Historial de visitas:** Ha asistido {conteo_atenciones} vez/veces previa(s) a la clínica. **Código de Consulta Asignado:** `{tipo_consulta_auto}`")

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
      st.info("No hay registros previos para este paciente. Esta será su primera consulta (C1).")
  else:
    st.warning("No hay pacientes registrados.")

# --- MÓDULO: RESPALDO Y DATOS ---
elif choice in ["📥 Respaldo y Datos"]:
  st.subheader("Respaldo y Reportes en Excel - Medisuport")
  st.write("Genera y descarga un archivo de Excel (`.xlsx`) con toda la información de la clínica.")

  if st.button("Generar Reporte Excel"):
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
        label="📥 Descargar Reporte Medisuport (.xlsx)",
        data=excel_data,
        file_name=f"medisuport_reporte_{datetime.now().strftime('%Y-%m-%d')}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
