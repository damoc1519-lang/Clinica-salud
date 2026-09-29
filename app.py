import streamlit as st

# --- CONTROL DE ACCESO (CONTRASEÑA) ---
# Puedes cambiar "tu_contraseña_secreta" por la clave que quieras darles a tus colegas
PASSWORD_CORRECTA = "clinica2026"


def verificar_password():
  """Retorna True si el usuario ingresó la contraseña correcta."""

  def password_entered():
    if st.session_state["password"] == PASSWORD_CORRECTA:
      st.session_state["password_correct"] = True
      del st.session_state["password"]  # No guardar la contraseña en memoria
    else:
      st.session_state["password_correct"] = False

  if "password_correct" not in st.session_state:
    # Primera vez que entra, muestra la caja de texto para la clave
    st.text_input(
        "Contraseña de Acceso",
        type="password",
        on_change=password_entered,
        key="password",
    )
    st.warning(
        "Por favor, ingrese la contraseña autorizada para acceder al sistema"
        " de la clínica."
    )
    return False
  elif not st.session_state["password_correct"]:
    # Contraseña incorrecta, vuelve a pedirla
    st.text_input(
        "Contraseña de Acceso",
        type="password",
        on_change=password_entered,
        key="password",
    )
    st.error("😕 Contraseña incorrecta. Intente de nuevo.")
    return False
  else:
    # Contraseña correcta, deja pasar a la app
    return True


# Si la contraseña no es correcta, detiene la ejecución aquí mismo
if not verificar_password():
  st.stop()
from datetime import datetime
import os
import sqlite3
import pandas as pd
import streamlit as st

# --- CONFIGURACIÓN DE TEMA CLARO (FONDO BLANCO) ---
st.set_page_config(
    page_title="Sistema de Gestión - Clínica", page_icon="🏥", layout="wide"
)

# Forzar estilos visuales limpios en blanco
st.markdown("""
    <style>
    .main {
        background-color: #FFFFFF;
        color: #000000;
    }
    .stSidebar {
        background-color: #F8F9FA;
    }
    </style>
    """, unsafe_allow_html=True)


# --- CONFIGURACIÓN DE LA BASE DE DATOS ---
def init_db():
  conn = sqlite3.connect("clinica.db", check_same_thread=False)
  cursor = conn.cursor()
  # Tabla de Pacientes
  cursor.execute("""
        CREATE TABLE IF NOT EXISTS pacientes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cedula TEXT UNIQUE NOT NULL,
            nombre TEXT NOT NULL,
            telefono TEXT,
            fecha_nacimiento TEXT
        )
    """)
  # Tabla de Citas / Agenda
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
  # Tabla de Historial Clínico (Atenciones acumulativas)
  cursor.execute("""
        CREATE TABLE IF NOT EXISTS historial (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cedula_paciente TEXT,
            fecha_atencion TEXT,
            motivo TEXT,
            diagnostico TEXT,
            receta TEXT,
            FOREIGN KEY(cedula_paciente) REFERENCES pacientes(cedula)
        )
    """)
  conn.commit()
  conn.close()


init_db()

# --- INTERFAZ DE USUARIO ---
st.title("🏥 Sistema de Gestión y Agenda Médica - Clínica")

menu = [
    "👤 Registrar / Buscar Paciente",
    "📅 Agenda y Citas",
    "🩺 Consulta Médica (Historial)",
    "📥 Exportar Datos y Respaldo",
]
choice = st.sidebar.selectbox("Menú de Navegación", menu)

# --- MÓDULO 1: AGENDA Y CITAS ---
if choice == "📅 Agenda y Citas":
  st.subheader("Gestión de Agenda Virtual")

  conn = sqlite3.connect("clinica.db", check_same_thread=False)
  cursor = conn.cursor()
  cursor.execute("SELECT cedula, nombre FROM pacientes")
  pacientes = cursor.fetchall()
  conn.close()

  pacientes_dict = {f"{p[1]} (Cédula: {p[0]})": p[0] for p in pacientes}

  with st.form("form_cita"):
    st.write("Agendar Nueva Cita")
    if pacientes_dict:
      paciente_seleccionado = st.selectbox(
          "Seleccionar Paciente", list(pacientes_dict.keys())
      )
      cedula_act = pacientes_dict[paciente_seleccionado]
    else:
      st.warning(
          "No hay pacientes registrados. Regístrelos primero en la sección"
          " correspondiente."
      )
      cedula_act = ""

    fecha = st.date_input("Fecha de la Cita", datetime.now())
    hora = st.time_input("Hora de la Cita")
    medico = st.text_input("Médico Tratante")
    especialidad = st.selectbox(
        "Especialidad", ["Dermatología", "Medicina General", "Pediatría"]
    )

    submitted = st.form_submit_button("Agendar Cita")
    if submitted and cedula_act:
      conn = sqlite3.connect("clinica.db", check_same_thread=False)
      cursor = conn.cursor()
      cursor.execute(
          "INSERT INTO citas (cedula_paciente, fecha, hora, medico,"
          " especialidad) VALUES (?, ?, ?, ?, ?)",
          (cedula_act, str(fecha), str(hora), medico, especialidad),
      )
      conn.commit()
      conn.close()
      st.success("¡Cita agendada con éxito!")

  st.divider()
  st.subheader("Citas Registradas")
  conn = sqlite3.connect("clinica.db", check_same_thread=False)
  cursor = conn.cursor()
  cursor.execute("""
        SELECT c.fecha, c.hora, p.nombre, c.medico, c.especialidad 
        FROM citas c JOIN pacientes p ON c.cedula_paciente = p.cedula
    """)
  citas_data = cursor.fetchall()
  conn.close()
  if citas_data:
    st.table(citas_data)
  else:
    st.info("No hay citas registradas.")

# --- MÓDULO 2: PACIENTES ---
elif choice == "👤 Registrar / Buscar Paciente":
  st.subheader("Gestión de Pacientes (Registro Único)")

  with st.form("form_paciente"):
    cedula = st.text_input("Número de Cédula")
    nombre = st.text_input("Nombre Completo del Paciente")
    telefono = st.text_input("Teléfono / Celular")
    f_nac = st.date_input("Fecha de Nacimiento", datetime(1990, 1, 1))

    guardar = st.form_submit_button("Guardar Paciente")
    if guardar:
      if cedula and nombre:
        try:
          conn = sqlite3.connect("clinica.db", check_same_thread=False)
          cursor = conn.cursor()
          cursor.execute(
              "INSERT INTO pacientes (cedula, nombre, telefono,"
              " fecha_nacimiento) VALUES (?, ?, ?, ?)",
              (cedula, nombre, telefono, str(f_nac)),
          )
          conn.commit()
          conn.close()
          st.success(f"Paciente {nombre} registrado correctamente.")
        except sqlite3.IntegrityError:
          st.error("Error: Ya existe un paciente registrado con esta cédula.")
      else:
        st.warning("Por favor complete al menos la cédula y el nombre.")

# --- MÓDULO 3: CONSULTA MÉDICA E HISTORIAL ---
elif choice == "🩺 Consulta Médica (Historial)":
  st.subheader("Atención Médica e Historial Clínico Acumulativo")

  conn = sqlite3.connect("clinica.db", check_same_thread=False)
  cursor = conn.cursor()
  cursor.execute("SELECT cedula, nombre FROM pacientes")
  pacientes = cursor.fetchall()
  conn.close()

  pacientes_dict = {f"{p[1]} (Cédula: {p[0]})": p[0] for p in pacientes}

  if pacientes_dict:
    paciente_sel = st.selectbox(
        "Seleccione al Paciente a Atender", list(pacientes_dict.keys())
    )
    cedula_paciente = pacientes_dict[paciente_sel]

    conn = sqlite3.connect("clinica.db", check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT * FROM pacientes WHERE cedula = ?", (cedula_paciente,)
    )
    p_info = cursor.fetchone()

    st.info(
        f"**Expediente del Paciente:** {p_info[2]} | **Cédula:**"
        f" {p_info[1]} | **Teléfono:** {p_info[3]}"
    )

    with st.form("form_atencion"):
      st.write("Nueva Atención / Evolución Médica")
      motivo = st.text_area("Motivo de la Consulta")
      diagnostico = st.text_area("Diagnóstico")
      receta = st.text_area("Tratamiento / Receta")

      finalizar = st.form_submit_button("Guardar Atención en el Historial")
      if finalizar:
        cursor.execute(
            "INSERT INTO historial (cedula_paciente, fecha_atencion, motivo,"
            " diagnostico, receta) VALUES (?, ?, ?, ?, ?)",
            (
                cedula_paciente,
                datetime.now().strftime("%Y-%m-%d %H:%M"),
                motivo,
                diagnostico,
                receta,
            ),
        )
        conn.commit()
        st.success("¡Atención médica registrada y añadida al historial único!")

    conn.close()

    st.divider()
    st.subheader("Historial de Atenciones Anteriores")
    conn = sqlite3.connect("clinica.db", check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT fecha_atencion, motivo, diagnostico, receta FROM historial WHERE"
        " cedula_paciente = ? ORDER BY id DESC",
        (cedula_paciente,),
    )
    historicos = cursor.fetchall()
    conn.close()

    if historicos:
      for h in historicos:
        with st.expander(f"Consulta del: {h[0]}"):
          st.write(f"**Motivo:** {h[1]}")
          st.write(f"**Diagnóstico:** {h[2]}")
          st.write(f"**Tratamiento/Receta:** {h[3]}")
    else:
      st.info("Este paciente aún no tiene atenciones registradas.")
  else:
    st.warning("No hay pacientes registrados en el sistema.")

# --- MÓDULO 4: EXPORTAR DATOS Y RESPALDO ---
elif choice == "📥 Exportar Datos y Respaldo":
  st.subheader("Descarga de Respaldos y Archivos Excel")
  st.write(
      "Aquí puedes descargar una copia de seguridad completa de la base de"
      " datos o exportar tablas individuales en formato CSV/Excel."
  )

  # BOTÓN DE RESPALDO TOTAL DE LA BASE DE DATOS (.db)
  if os.path.exists("clinica.db"):
    with open("clinica.db", "rb") as file:
      st.download_button(
          label="📥 Descargar Base de Datos Completa (.db)",
          data=file,
          file_name=f"clinica_respaldo_{datetime.now().strftime('%Y-%m-%d')}.db",
          mime="application/octet-stream",
          help=(
              "Descarga un respaldo exacto de todo el sistema para guardarlo"
              " en tu computadora."
          ),
      )

  st.divider()

  conn = sqlite3.connect("clinica.db", check_same_thread=False)
  df_pacientes = pd.read_sql_query("SELECT * FROM pacientes", conn)
  df_citas = pd.read_sql_query("SELECT * FROM citas", conn)
  df_historial = pd.read_sql_query("SELECT * FROM historial", conn)
  conn.close()

  st.markdown("### 1. Lista de Pacientes")
  if not df_pacientes.empty:
    st.dataframe(df_pacientes)
    csv_pacientes = df_pacientes.to_csv(index=False).encode("utf-8")
    st.download_button(
        label="📥 Descargar Pacientes en CSV",
        data=csv_pacientes,
        file_name="pacientes_clinica.csv",
        mime="text/csv",
    )
  else:
    st.info("No hay datos de pacientes para descargar.")

  st.markdown("### 2. Agenda de Citas")
  if not df_citas.empty:
    st.dataframe(df_citas)
    csv_citas = df_citas.to_csv(index=False).encode("utf-8")
    st.download_button(
        label="📥 Descargar Citas en CSV",
        data=csv_citas,
        file_name="citas_clinica.csv",
        mime="text/csv",
    )
  else:
    st.info("No hay citas registradas para descargar.")

  st.markdown("### 3. Historial Clínico Completo")
  if not df_historial.empty:
    st.dataframe(df_historial)
    csv_historial = df_historial.to_csv(index=False).encode("utf-8")
    st.download_button(
        label="📥 Descargar Historial Clínico en CSV",
        data=csv_historial,
        file_name="historial_clinica.csv",
        mime="text/csv",
    )
  else:
    st.info("No hay historiales médicos registrados para descargar.")
