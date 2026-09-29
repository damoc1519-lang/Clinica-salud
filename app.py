import psycopg2
import streamlit as st

# --- CONFIGURACIÓN DE CONEXIÓN A SUPABASE ---
# Utiliza st.secrets para mayor seguridad en la nube (Streamlit Cloud)
# O puedes usar la cadena directa si estás probando localmente en Codespaces.


def init_connection():
  return psycopg2.connect(
      "postgresql://postgres:R3ratoncitos@db.vktnksyxgtgphohpjmke.supabase.co:6543/postgres"
  )


# Conexión persistente con caché de Streamlit
@st.resource if hasattr(st, "resource") else st.cache_resource
def get_db_connection():
  return init_connection()


try:
  conn = get_db_connection()
  cursor = conn.cursor()
except Exception as e:
  st.error(f"Error al conectar con la base de datos en la nube: {e}")
  st.stop()

# --- INTERFAZ DE USUARIO (MEDISUPORT) ---
st.title("🏥 Medisuport - Sistema de Gestión Clínica")

# Menú lateral de navegación
menu = st.sidebar.selectbox(
    "Menú de Navegación",
    [
        "Agendamiento de Citas",
        "Registro de Pacientes",
        "Historial Clínico",
        "Disponibilidad Médica",
    ],
)

# ---------------------------------------------------------
# 1. MÓDULO: AGENDAMIENTO DE CITAS
# ---------------------------------------------------------
if menu == "Agendamiento de Citas":
  st.header("📅 Agendamiento de Citas Médicas")

  # Obtener pacientes registrados para el selectbox
  cursor.execute("SELECT cedula, nombre FROM pacientes;")
  pacientes = cursor.fetchall()
  pacientes_dict = {f"{p[1]} (Cédula: {p[0]})": p[0] for p in pacientes}

  if not pacientes_dict:
    st.warning(
        "No hay pacientes registrados. Por favor, registre un paciente primero."
    )
  else:
    selected_paciente_label = st.selectbox(
        "Seleccionar Paciente", list(pacientes_dict.keys())
    )
    cedula_paciente = pacientes_dict[selected_paciente_label]

    # Obtener disponibilidad configurada por la secretaria (si aplica en tu esquema)
    col1, col2, col3 = st.columns(3)
    with col1:
      fecha_cita = st.date_input("Fecha de la Cita")
    with col2:
      hora_cita = st.time_input("Hora de la Cita")
    with col3:
      especialidad = st.selectbox(
          "Especialidad",
          ["Medicina General", "Pediatría", "Ginecología", "Traumatología"],
      )

    if st.button("Confirmar y Agendar Cita"):
      try:
        cursor.execute(
            """
                    INSERT INTO citas (cedula_paciente, fecha, hora, especialidad) 
                    VALUES (%s, %s, %s, %s);
                """,
            (
                cedula_paciente,
                str(fecha_cita),
                str(hora_cita),
                especialidad,
            ),
        )
        conn.commit()
        st.success("¡Cita agendada y guardada en la nube con éxito!")
      except Exception as err:
        conn.rollback()
        st.error(f"Error al agendar la cita: {err}")

  # Mostrar citas existentes
  st.subheader("Citas Registradas Recentemente")
  cursor.execute("""
        c.id, p.nombre, c.fecha, c.hora, c.especialidad 
        FROM citas c 
        JOIN pacientes p ON c.cedula_paciente = p.cedula 
        ORDER BY c.fecha DESC LIMIT 50;
    """)
  # Nota: Ajusta la consulta según el orden de tus columnas creadas
  try:
    cursor.execute("""
            SELECT c.id, p.nombre, c.fecha, c.hora, c.especialidad 
            FROM citas c 
            JOIN pacientes p ON c.cedula_paciente = p.cedula 
            ORDER BY c.id DESC LIMIT 50;
        """)
    citas_data = cursor.fetchall()
    if citas_data:
      for c in citas_data:
        st.write(
            f"🔹 **ID:** {c[0]} | **Paciente:** {c[1]} | **Fecha:** {c[2]} |"
            f" **Hora:** {c[3]} | **Especialidad:** {c[4]}"
        )
    else:
      st.info("No hay citas registradas todavía.")
  except Exception:
    st.info("Configura las tablas en Supabase para visualizar el listado.")

# ---------------------------------------------------------
# 2. MÓDULO: REGISTRO DE PACIENTES
# ---------------------------------------------------------
elif menu == "Registro de Pacientes":
  st.header("👤 Registro de Nuevos Pacientes")

  with st.form("form_paciente"):
    cedula = st.text_input("Número de Cédula")
    nombre = st.text_input("Nombre Completo")
    telefono = st.text_input("Teléfono de Contacto")
    submitted = st.form_submit_button("Guardar Paciente")

    if submitted:
      if cedula and nombre:
        try:
          cursor.execute(
              """
                        INSERT INTO pacientes (cedula, nombre, telefono) 
                        VALUES (%s, %s, %s)
                        ON CONFLICT (cedula) DO UPDATE 
                        SET nombre = EXCLUDED.nombre, telefono = EXCLUDED.telefono;
                    """,
              (cedula, nombre, telefono),
          )
          conn.commit()
          st.success(
              f"Paciente {nombre} guardado correctamente en la nube de Supabase."
          )
        except Exception as err:
          conn.rollback()
          st.error(f"Error al guardar el paciente: {err}")
      else:
        st.warning("Por favor, ingresa al menos la cédula y el nombre.")

# ---------------------------------------------------------
# 3. MÓDULO: HISTORIAL CLÍNICO
# ---------------------------------------------------------
elif menu == "Historial Clínico":
  st.header("📋 Historial Clínico de Atenciones")

  cursor.execute("SELECT cedula, nombre FROM pacientes;")
  pacientes = cursor.fetchall()
  pacientes_dict = {f"{p[1]} ({p[0]})": p[0] for p in pacientes}

  if pacientes_dict:
    selected_p = st.selectbox("Seleccionar Paciente", list(pacientes_dict.keys()))
    cedula_sel = pacientes_dict[selected_p]

    with st.form("form_historial"):
      fecha_atencion = st.date_input("Fecha de Atención")
      motivo = st.text_area("Motivo de Consulta")
      diagnostico = st.text_area("Diagnóstico")
      receta = st.text_area("Receta / Tratamiento")
      guardar_hist = st.form_submit_button("Registrar Atención")

      if guardar_hist:
        try:
          cursor.execute(
              """
                        INSERT INTO historial (cedula_paciente, fecha_atencion, motivo, diagnostico, receta)
                        VALUES (%s, %s, %s, %s, %s);
                    """,
              (
                  cedula_sel,
                  str(fecha_atencion),
                  motivo,
                  diagnostico,
                  receta,
              ),
          )
          conn.commit()
          st.success("Historial médico actualizado exitosamente en la nube.")
        except Exception as err:
          conn.rollback()
          st.error(f"Error al registrar historial: {err}")

    # Mostrar historial previo del paciente
    st.subheader("Atenciones Previas")
    cursor.execute(
        """
            SELECT fecha_atencion, motivo, diagnostico, receta 
            FROM historial WHERE cedula_paciente = %s 
            ORDER BY id DESC;
        """,
        (cedula_sel,),
    )
    historicos = cursor.fetchall()
    if historicos:
      for h in historicos:
        with st.expander(f"Atención del: {h[0]} - Motivo: {h[1]}"):
          st.write(f"**Diagnóstico:** {h[2]}")
          st.write(f"**Receta:** {h[3]}")
    else:
      st.info("Este paciente no registra atenciones anteriores.")
  else:
    st.warning("No hay pacientes disponibles para consultar historiales.")

# ---------------------------------------------------------
# 4. MÓDULO: DISPONIBILIDAD MÉDICA
# ---------------------------------------------------------
elif menu == "Disponibilidad Médica":
  st.header("⏱️ Gestión de Disponibilidad Médica")
  st.info(
      "Módulo habilitado para que la secretaría administre horarios y turnos"
      " disponibles."
  )
  # Aquí puedes integrar la lógica de disponibilidad que venías estructurando en tu base de datos.
