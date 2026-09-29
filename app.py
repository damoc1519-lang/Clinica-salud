from datetime import datetime
import os
import io
import docx
from docx.shared import Inches, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
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

# --- BASE DE DATOS Y TABLAS AMPLIADAS ---
def init_db():
    conn = sqlite3.connect("clinica.db", check_same_thread=False)
    cursor = conn.cursor()
  
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS pacientes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cedula TEXT UNIQUE NOT NULL,
            nombre TEXT NOT NULL,
            sexo TEXT,
            fecha_nacimiento TEXT,
            domicilio TEXT,
            telefono TEXT,
            correo TEXT,
            ocupacion TEXT,
            prevision TEXT,
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
            vencimiento_issfa TEXT,
            estado TEXT,
            observaciones TEXT,
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
            antecedentes_pers TEXT,
            antecedentes_fam TEXT,
            habitos TEXT,
            motivo TEXT,
            enfermedad_actual TEXT,
            peso TEXT,
            talla TEXT,
            pa TEXT,
            fc TEXT,
            imc TEXT,
            diagnostico TEXT,
            tratamiento TEXT,
            examenes TEXT,
            FOREIGN KEY(cedula_paciente) REFERENCES pacientes(cedula)
        )
    """)
  
    cursor.execute("PRAGMA table_info(citas)")
    c_cols = [col[1] for col in cursor.fetchall()]
    for col_name, col_type in [("vencimiento_issfa", "TEXT"), ("estado", "TEXT"), ("observaciones", "TEXT")]:
        if col_name not in c_cols:
            cursor.execute(f"ALTER TABLE citas ADD COLUMN {col_name} {col_type}")

    cursor.execute("PRAGMA table_info(pacientes)")
    p_cols = [col[1] for col in cursor.fetchall()]
    for col_name, col_type in [("sexo", "TEXT"), ("domicilio", "TEXT"), ("correo", "TEXT"), ("ocupacion", "TEXT"), ("prevision", "TEXT"), ("origen", "TEXT")]:
        if col_name not in p_cols:
            cursor.execute(f"ALTER TABLE pacientes ADD COLUMN {col_name} {col_type}")

    cursor.execute("PRAGMA table_info(historial)")
    h_cols = [col[1] for col in cursor.fetchall()]
    for col_name, col_type in [("tipo_consulta", "TEXT"), ("antecedentes_pers", "TEXT"), ("antecedentes_fam", "TEXT"), ("habitos", "TEXT"), ("motivo", "TEXT"), ("enfermedad_actual", "TEXT"), ("peso", "TEXT"), ("talla", "TEXT"), ("pa", "TEXT"), ("fc", "TEXT"), ("imc", "TEXT"), ("diagnostico", "TEXT"), ("tratamiento", "TEXT"), ("examenes", "TEXT")]:
        if col_name not in h_cols:
            cursor.execute(f"ALTER TABLE historial ADD COLUMN {col_name} {col_type}")

    conn.commit()
    conn.close()

init_db()

# --- DICCIONARIO DE MÉDICOS, ESPECIALIDADES Y HORARIOS INSTITUCIONALES ---
MEDICOS_INFO = {
    "Dra. Kanie Collado": {"esp": "Alergología", "dias": "Lunes y Miércoles", "horas": "08:00 - 13:00"},
    "Dr. Norberto Carballosa": {"esp": "Anestesiología", "dias": "Martes y Jueves", "horas": "09:00 - 14:00"},
    "Dra. Lisset Alfonso": {"esp": "Cardiología", "dias": "Lunes, Miércoles y Viernes", "horas": "08:00 - 12:00"},
    "Dr. Miguel Mederos": {"esp": "Dermatología", "dias": "Martes y Viernes", "horas": "13:00 - 18:00"},
    "Dr. Frank Medina": {"esp": "Endocrinología", "dias": "Martes y Jueves", "horas": "08:00 - 12:00"},
    "Dr. Miguel Marrero": {"esp": "Endocrinología", "dias": "Lunes y Miércoles", "horas": "14:00 - 18:00"},
    "Dra. Gabriela Vélez": {"esp": "Endocrinología", "dias": "Viernes", "horas": "08:00 - 13:00"},
    "Dr. Pavel Mili": {"esp": "Fisiatría", "dias": "Lunes y Jueves", "horas": "08:00 - 13:00"},
    "Dr. Yunio Torres": {"esp": "Fisiatría", "dias": "Martes y Miércoles", "horas": "13:00 - 17:00"},
    "Dr. Frank Pérez": {"esp": "Gastroenterología", "dias": "Lunes a Viernes", "horas": "08:00 - 12:00"},
    "Dra. Mildred": {"esp": "Geriatría", "dias": "Miércoles y Viernes", "horas": "09:00 - 14:00"},
    "Dr. Alejandro Argiz": {"esp": "Ginecología", "dias": "Lunes y Martes", "horas": "08:00 - 13:00"},
    "Dra. Marilyn Martínez": {"esp": "Ginecología", "dias": "Miércoles y Jueves", "horas": "13:00 - 18:00"},
    "Dra. Osmarie Barbosa": {"esp": "Logopedia / Medicina General", "dias": "Lunes a Viernes", "horas": "08:00 - 16:00"},
    "Dr. Yoandis Pérez": {"esp": "Medicina General", "dias": "Lunes a Viernes", "horas": "08:00 - 16:00"},
    "Dra. Ailicec Arias": {"esp": "Medicina General / Pediatría", "dias": "Lunes a Viernes", "horas": "08:00 - 16:00"},
    "Dr. Ovadiz Pérez": {"esp": "Medicina Interna", "dias": "Lunes, Miércoles y Viernes", "horas": "08:00 - 13:00"},
    "Dra. Eva Barbosa": {"esp": "Neumología", "dias": "Martes y Jueves", "horas": "09:00 - 14:00"},
    "Dr. Dayron Douglas Calvo": {"esp": "Neurología", "dias": "Lunes y Miércoles", "horas": "09:00 - 13:00"},
    "Lcdo. Andrés Hidrobo": {"esp": "Nutrición", "dias": "Martes y Jueves", "horas": "08:00 - 15:00"},
    "Dr. Fernando Enríquez": {"esp": "Otorrinolaringología", "dias": "Lunes, Miércoles y Viernes", "horas": "13:00 - 17:00"},
    "Dra. María Cristina Torres": {"esp": "Pediatría", "dias": "Lunes a Viernes", "horas": "08:00 - 13:00"},
    "Lcdo. Jerson Rodríguez": {"esp": "Psicología", "dias": "Lunes a Viernes", "horas": "09:00 - 17:00"},
    "Dra. Yulca Rosales": {"esp": "Psiquiatría", "dias": "Martes y Jueves", "horas": "14:00 - 18:00"},
    "Dr. Dennis Pucha": {"esp": "Reumatología", "dias": "Lunes y Miércoles", "horas": "08:00 - 12:00"},
    "Dr. Rafael Echavarría": {"esp": "Reumatología", "dias": "Martes y Jueves", "horas": "13:00 - 17:00"},
    "Dr. Antonio Leal": {"esp": "Traumatología", "dias": "Lunes a Viernes", "horas": "08:00 - 14:00"},
    "Dr. William Fonseca": {"esp": "Urología", "dias": "Lunes, Miércoles y Viernes", "horas": "08:00 - 13:00"}
}

MEDICOS_ESPECIALIDADES = {}
for doc, info in MEDICOS_INFO.items():
    esp = info["esp"]
    if esp not in MEDICOS_ESPECIALIDADES:
        MEDICOS_ESPECIALIDADES[esp] = []
    MEDICOS_ESPECIALIDADES[esp].append(doc)

USERS = {
    "Abigail Ruiz (Secretaria)": {"pass": "sec2026", "role": "secretaria"},
    "Administrador": {"pass": "admin2026", "role": "admin"}
}
for doc in MEDICOS_INFO.keys():
    USERS[f"{doc} ({MEDICOS_INFO[doc]['esp']})"] = {"pass": "med123", "role": "medico"}

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
    menu = ["Registrar Paciente", "Buscar y Gestionar Pacientes", "Listado de Pacientes", "Disponibilidad de Medicos", "Agenda y Citas", "Respaldo y Datos"]
elif role == "medico":
    menu = ["Buscar y Gestionar Pacientes", "Listado de Pacientes", "Disponibilidad de Medicos", "Ver Agenda de Citas", "Consulta Medica (Historial)"]
else:
    menu = ["Registrar Paciente", "Buscar y Gestionar Pacientes", "Listado de Pacientes", "Disponibilidad de Medicos", "Agenda y Citas", "Consulta Medica (Historial)", "Respaldo y Datos"]

choice = st.sidebar.selectbox("Seleccione opción", menu)

# --- FUNCIÓN AUXILIAR PARA GENERAR WORD FORMATEADO ---
def generar_documento_word(info_p, visitas, codigo_estado, historial_p):
    doc = docx.Document()
    for section in doc.sections:
        section.top_margin = Inches(1)
        section.bottom_margin = Inches(1)
        section.left_margin = Inches(1)
        section.right_margin = Inches(1)

    p_head = doc.add_paragraph()
    p_head.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run_head = p_head.add_run("SISTEMA MÉDICO CLÍNICO - MEDISUPORT\nEXPEDIENTE DE HISTORIA CLÍNICA")
    run_head.font.name = 'Arial'
    run_head.font.size = Pt(14)
    run_head.font.bold = True
    run_head.font.color.rgb = RGBColor(0, 51, 102)

    doc.add_paragraph("-------------------------------------------------------------------------------------------------------------")

    p_datos_title = doc.add_paragraph()
    run_dt = p_datos_title.add_run("1. DATOS DE IDENTIFICACIÓN Y FILIACIÓN")
    run_dt.font.bold = True
    run_dt.font.size = Pt(12)
    run_dt.font.color.rgb = RGBColor(0, 51, 102)

    p_info = doc.add_paragraph()
    p_info.add_run("• Nombre Completo: ").bold = True
    p_info.add_run(f"{info_p[2]}\n")
    p_info.add_run("• Documento de Identidad: ").bold = True
    p_info.add_run(f"{info_p[1]}\n")
    p_info.add_run("• Sexo: ").bold = True
    p_info.add_run(f"{info_p[3]}    |   ")
    p_info.add_run("Fecha de Nacimiento: ").bold = True
    p_info.add_run(f"{info_p[4]}\n")
    p_info.add_run("• Domicilio: ").bold = True
    p_info.add_run(f"{info_p[5]}\n")
    p_info.add_run("• Teléfono: ").bold = True
    p_info.add_run(f"{info_p[6]}    |   ")
    p_info.add_run("Correo: ").bold = True
    p_info.add_run(f"{info_p[7]}\n")
    p_info.add_run("• Ocupación: ").bold = True
    p_info.add_run(f"{info_p[8]}    |   ")
    p_info.add_run("Sistema de Salud: ").bold = True
    p_info.add_run(f"{info_p[9]}\n")
    p_info.add_run("• Origen de Registro: ").bold = True
    p_info.add_run(f"{info_p[10] if len(info_p) > 10 else 'N/A'}\n")
    p_info.add_run("• Resumen de Visitas: ").bold = True
    p_info.add_run(f"Total de Atenciones: {visitas}  (Clasificación Actual: {codigo_estado})\n")

    doc.add_paragraph("-------------------------------------------------------------------------------------------------------------")

    p_hist_title = doc.add_paragraph()
    run_ht = p_hist_title.add_run("2. EVOLUCIÓN Y REGISTRO DE ATENCIONES MÉDICAS")
    run_ht.font.bold = True
    run_ht.font.size = Pt(12)
    run_ht.font.color.rgb = RGBColor(0, 51, 102)

    if historial_p:
        for idx, h in enumerate(historial_p, 1):
            p_atn = doc.add_paragraph()
            p_atn.add_run(f"Atención #{len(historial_p) - idx + 1} - Fecha: {h[0]} [Código: {h[2]}]\n").bold = True
            p_atn.add_run(f"Médico Tratante: {h[1]}\n").italic = True
            
            p_atn.add_run("  - Motivo de Consulta: ").bold = True
            p_atn.add_run(f"{h[6]}\n")
            p_atn.add_run("  - Enfermedad Actual / Anamnesis: ").bold = True
            p_atn.add_run(f"{h[7]}\n")
            p_atn.add_run("  - Antecedentes Personales: ").bold = True
            p_atn.add_run(f"{h[3]} | Familiares: {h[4]} | Hábitos: {h[5]}\n")
            p_atn.add_run("  - Signos Vitales y Antropometría: ").bold = True
            p_atn.add_run(f"Peso: {h[8]} kg | Talla: {h[9]} cm | PA: {h[10]} | FC: {h[11]} lpm | IMC: {h[12]}\n")
            p_atn.add_run("  - Diagnóstico: ").bold = True
            p_atn.add_run(f"{h[13]}\n")
            p_atn.add_run("  - Tratamiento / Receta: ").bold = True
            p_atn.add_run(f"{h[14]}\n")
            p_atn.add_run("  - Exámenes Complementarios: ").bold = True
            p_atn.add_run(f"{h[15]}\n")
            
            doc.add_paragraph(".............................................................................................................................")
    else:
        doc.add_paragraph("El paciente no registra atenciones médicas previas en el sistema.")

    file_stream = io.BytesIO()
    doc.save(file_stream)
    file_stream.seek(0)
    return file_stream.getvalue()

# --- MÓDULO 1: REGISTRAR PACIENTE ---
if choice == "Registrar Paciente":
    st.subheader("➕ Registro de Nuevo Paciente - Medisuport")
    with st.form("form_paciente"):
        st.write("### Datos de Identificación y Contacto")
        col1, col2 = st.columns(2)
        with col1:
            cedula = st.text_input("Número de Documento / Cédula / Pasaporte")
            nombre = st.text_input("Nombre Completo")
            sexo = st.selectbox("Sexo", ["Masculino", "Femenino", "Otro"])
            f_nac = st.date_input("Fecha de Nacimiento", datetime(1990, 1, 1))
            telefono = st.text_input("Teléfono / Celular")
        with col2:
            correo = st.text_input("Correo Electrónico")
            domicilio = st.text_input("Domicilio / Dirección")
            ocupacion = st.text_input("Ocupación")
            prevision = st.selectbox("Sistema de Salud / Previsión", ["Particular / Propio de la Clínica", "ISSFA", "IESS", "MSP", "Seguro Privado"])
            origen = st.selectbox("Origen de Registro", ["Propio de la Clínica", "Prestador Externo ISSFA"])

        guardar = st.form_submit_button("Guardar Ficha del Paciente")
        
        if guardar:
            if cedula and nombre:
                try:
                    conn = sqlite3.connect("clinica.db", check_same_thread=False)
                    cursor = conn.cursor()
                    cursor.execute("""
                        INSERT INTO pacientes (cedula, nombre, sexo, fecha_nacimiento, domicilio, telefono, correo, ocupacion, prevision, origen) 
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (cedula, nombre, sexo, str(f_nac), domicilio, telefono, correo, ocupacion, prevision, origen))
                    conn.commit()
                    conn.close()
                    st.success(f"¡Paciente {nombre} registrado con éxito!")
                except sqlite3.IntegrityError:
                    st.error("Error: Ya existe un paciente registrado con este número de documento.")
            else:
                st.warning("Complete al menos el número de documento y el nombre completo.")

# --- MÓDULO 2: BUSCAR Y GESTIONAR PACIENTES ---
elif choice == "Buscar y Gestionar Pacientes":
    st.subheader("🔍 Ficha Clínica y Búsqueda de Pacientes")
    conn = sqlite3.connect("clinica.db", check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute("SELECT cedula, nombre FROM pacientes")
    pacientes_db = cursor.fetchall()
    conn.close()

    if pacientes_db:
        opciones_busqueda = {f"{p[1]} (Doc: {p[0]})": p[0] for p in pacientes_db}
        paciente_elegido = st.selectbox("Seleccione Paciente", list(opciones_busqueda.keys()))
        cedula_buscar = opciones_busqueda[paciente_elegido]

        if st.button("Consultar Ficha Completa"):
            conn = sqlite3.connect("clinica.db", check_same_thread=False)
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM pacientes WHERE cedula = ?", (cedula_buscar,))
            info_p = cursor.fetchone()

            cursor.execute("SELECT COUNT(*) FROM historial WHERE cedula_paciente = ?", (cedula_buscar,))
            visitas = cursor.fetchone()[0]
            codigo_estado = "C1" if visitas == 0 else "SUB"

            cursor.execute("""
                SELECT fecha_atencion, medico_atn, tipo_consulta, antecedentes_pers, antecedentes_fam, habitos, 
                       motivo, enfermedad_actual, peso, talla, pa, fc, imc, diagnostico, tratamiento, examenes 
                FROM historial WHERE cedula_paciente = ? ORDER BY id DESC
            """, (cedula_buscar,))
            historial_p = cursor.fetchall()
            conn.close()

            if info_p:
                st.success("¡Ficha de Paciente Encontrada!")
                st.write(f"**Nombre:** {info_p[2]} | **Sexo:** {info_p[3]} | **F. Nacimiento:** {info_p[4]}")
                st.write(f"**Documento:** {info_p[1]} | **Teléfono:** {info_p[6]} | **Correo:** {info_p[7]}")
                st.write(f"**Domicilio:** {info_p[5]} | **Ocupación:** {info_p[8]} | **Sistema de Salud:** {info_p[9]}")
                st.info(f"📊 **Total de Atenciones Previas:** {visitas} | **Código Actual:** `{codigo_estado}`")

                word_bytes = generar_documento_word(info_p, visitas, codigo_estado, historial_p)

                st.download_button(
                    label="📥 Descargar Historia Clínica en Formato Word (.docx)",
                    data=word_bytes,
                    file_name=f"Historia_Clinica_{info_p[1]}.docx",
                    mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                )

                if historial_p:
                    st.write("### 📂 Historial de Atenciones Clínicas Anteriores")
                    for h in historial_p:
                        with st.expander(f"Atención del {h[0]} | Código: {h[2]} | Médico: {h[1]}"):
                            st.write(f"**Motivo de Consulta:** {h[6]}")
                            st.write(f"**Enfermedad Actual / Anamnesis:** {h[7]}")
                            st.write(f"**Antecedentes Personales:** {h[3]} | **Familiares:** {h[4]} | **Hábitos:** {h[5]}")
                            st.write(f"**Signos Vitales y Antropometría:** Peso: {h[8]} kg | Talla: {h[9]} cm | PA: {h[10]} | FC: {h[11]} lpm | IMC: {h[12]}")
                            st.write(f"**Diagnóstico:** {h[13]}")
                            st.write(f"**Tratamiento y Receta:** {h[14]}")
                            st.write(f"**Resultados de Exámenes:** {h[15]}")
                else:
                    st.warning("Este paciente no cuenta con consultas previas registradas (Le corresponde código C1).")

        st.divider()
        if role in ["secretaria", "admin"]:
            with st.expander("🗑️ Zona de Peligro: Borrar Paciente por Error"):
                if st.button("Eliminar Definitivamente a este Paciente", type="primary"):
                    conn = sqlite3.connect("clinica.db", check_same_thread=False)
                    cursor = conn.cursor()
                    cursor.execute("DELETE FROM historial WHERE cedula_paciente = ?", (cedula_buscar,))
                    cursor.execute("DELETE FROM citas WHERE cedula_paciente = ?", (cedula_buscar,))
                    cursor.execute("DELETE FROM pacientes WHERE cedula = ?", (cedula_buscar,))
                    conn.commit()
                    conn.close()
                    st.success("Paciente eliminado correctamente.")
                    st.rerun()
    else:
        st.info("No hay pacientes registrados en el sistema.")

# --- MÓDULO 3: LISTADO GENERAL DE PACIENTES ---
elif choice == "Listado de Pacientes":
    st.subheader("📋 Base de Datos General de Pacientes")
    conn = sqlite3.connect("clinica.db", check_same_thread=False)
    df_p = pd.read_sql_query("SELECT cedula, nombre, sexo, telefono, correo, prevision, origen FROM pacientes", conn)
    conn.close()

    if not df_p.empty:
        st.dataframe(df_p, use_container_width=True)
        
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df_p.to_excel(writer, sheet_name='Pacientes', index=False)
        excel_data = output.getvalue()

        st.download_button(
            label="📥 Descargar Listado de Pacientes en Excel (.xlsx)",
            data=excel_data,
            file_name=f"medisuport_pacientes_{datetime.now().strftime('%Y-%m-%d')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
    else:
        st.info("No hay pacientes registrados.")

# --- NUEVO MÓDULO: DISPONIBILIDAD DE MÉDICOS ---
elif choice == "Disponibilidad de Medicos":
    st.subheader("📅 Consulta de Disponibilidad y Horarios de Médicos")
    st.write("Seleccione una especialidad o revise la disponibilidad institucional por días de la semana y horarios.")
  
    esp_filtro = st.selectbox("Filtrar por Especialidad", ["Todas"] + list(MEDICOS_ESPECIALIDADES.keys()))
  
    data_dispo = []
    for doc, info in MEDICOS_INFO.items():
        if esp_filtro == "Todas" or info["esp"] == esp_filtro:
            data_dispo.append({
                "Médico": doc,
                "Especialidad": info["esp"],
                "Días de Atención": info["dias"],
                "Horario": info["horas"]
            })
  
    df_dispo = pd.DataFrame(data_dispo)
    st.dataframe(df_dispo, use_container_width=True)

# --- MÓDULO 4: AGENDA Y CITAS ---
elif choice in ["Agenda y Citas", "Ver Agenda de Citas"]:
    st.subheader("📅 Agenda Médica Virtual e Institucional")
  
    if role in ["secretaria", "admin"]:
        conn = sqlite3.connect("clinica.db", check_same_thread=False)
        cursor = conn.cursor()
        cursor.execute("SELECT cedula, nombre, origen FROM pacientes")
        pacientes = cursor.fetchall()
        conn.close()
        pacientes_dict = {f"{p[1]} (Doc: {p[0]} - {p[2]})": p[0] for p in pacientes}

        st.write("### Agendar Nueva Cita (Verificación de Disponibilidad y Código ISSFA)")
        if pacientes_dict:
            paciente_sel = st.selectbox("Seleccionar Paciente", list(pacientes_dict.keys()), key="select_paciente_cita")
            cedula_act = pacientes_dict[paciente_sel]
        else:
            st.warning("Debe registrar pacientes primero.")
            cedula_act = ""

        especialidad_sel = st.selectbox("Especialidad Médica", list(MEDICOS_ESPECIALIDADES.keys()), key="select_especialidad_cita")
        medicos_disponibles = MEDICOS_ESPECIALIDADES[especialidad_sel]
    
        medico_sel = st.selectbox("Médico Tratante", medicos_disponibles, key="select_medico_cita")
        info_med = MEDICOS_INFO[medico_sel]
        st.info(f"💡 **Disponibilidad configurada para {medico_sel}:** {info_med['dias']} en horario de {info_med['horas']}.")

        with st.form("form_cita_real"):
            col1, col2 = st.columns(2)
            with col1:
                fecha_cita = st.date_input("Fecha de la Cita", datetime.now())
                vencimiento_issfa = st.date_input("Fecha de Vencimiento del Código ISSFA", datetime.now())
            with col2:
                hora_cita = st.time_input("Hora de la Cita")
                observaciones = st.text_input("Observaciones / Notas iniciales")

            submitted = st.form_submit_button("Agendar Cita")
      
            if submitted and cedula_act:
                str_fecha = str(fecha_cita)
                str_hora = str(hora_cita)
                str_venc = str(vencimiento_issfa)
        
                conn = sqlite3.connect("clinica.db", check_same_thread=False)
                cursor = conn.cursor()
                cursor.execute("SELECT COUNT(*) FROM citas WHERE medico = ? AND fecha = ? AND hora = ?", (medico_sel, str_fecha, str_hora))
                conf_count = cursor.fetchone()[0]
                conn.close()

                if conf_count > 0:
                    st.error(f"❌ El/La Dr(a). {medico_sel} ya tiene una cita agendada a esa hora y fecha exactas.")
                else:
                    conn = sqlite3.connect("clinica.db", check_same_thread=False)
                    cursor = conn.cursor()
                    cursor.execute("""
                        INSERT INTO citas (cedula_paciente, fecha, hora, medico, especialidad, vencimiento_issfa, estado, observaciones) 
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """, (cedula_act, str_fecha, str_hora, medico_sel, especialidad_sel, str_venc, "Agendada", observaciones))
                    conn.commit()
                    conn.close()
                    st.success(f"✅ ¡Cita agendada con éxito para el Dr(a). {medico_sel} el {str_fecha} a las {str_hora}!")
        st.divider()

    st.subheader("📋 Listado y Gestión de Citas (Reagendamientos y Estado)")
    conn = sqlite3.connect("clinica.db", check_same_thread=False)
    cursor = conn.cursor()

    if role == "medico":
        nombre_sesion = st.session_state['user_name']
        doctor_limpio = nombre_sesion.split(" (")[0]
        cursor.execute("""
            SELECT c.id, c.fecha, c.hora, p.nombre, c.medico, c.especialidad, c.vencimiento_issfa, c.estado, c.observaciones 
            FROM citas c JOIN pacientes p ON c.cedula_paciente = p.cedula 
            WHERE c.medico = ?
        """, (doctor_limpio,))
        st.info(f"Mostrando únicamente las citas asignadas a **{doctor_limpio}**.")
    else:
        cursor.execute("""
            SELECT c.id, c.fecha, c.hora, p.nombre, c.medico, c.especialidad, c.vencimiento_issfa, c.estado, c.observaciones 
            FROM citas c JOIN pacientes p ON c.cedula_paciente = p.cedula
        """)

    citas_data = cursor.fetchall()
    conn.close()
  
    if citas_data:
        df_citas_view = pd.DataFrame(citas_data, columns=["ID", "Fecha", "Hora", "Paciente", "Médico", "Especialidad", "Vencimiento ISSFA", "Estado", "Observaciones"])
        st.dataframe(df_citas_view.drop(columns=["ID"]), use_container_width=True)

        if role in ["secretaria", "admin"]:
            st.divider()
            with st.expander("🛠️ Reagendar, Modificar o Cancelar una Cita (Espacio para Inasistencias de Doctores)"):
                citas_dict = {f"Cita ID: {c[0]} | Paciente: {c[3]} | Fecha: {c[1]} {c[2]} | Dr(a). {c[4]}": c[0] for c in citas_data}
                cita_sel_mod = st.selectbox("Seleccione la cita a gestionar", list(citas_dict.keys()))
                id_cita_sel = citas_dict[cita_sel_mod]

                conn = sqlite3.connect("clinica.db", check_same_thread=False)
                cursor = conn.cursor()
                cursor.execute("SELECT fecha, hora, medico, especialidad, vencimiento_issfa, observaciones FROM citas WHERE id = ?", (id_cita_sel,))
                c_actual = cursor.fetchone()
                conn.close()

                if c_actual:
                    st.write(f"**Cita Actual:** {c_actual[0]} a las {c_actual[1]} con {c_actual[2]} ({c_actual[3]})")
          
                    with st.form("form_reagendar_cita"):
                        st.write("### Módulo de Reagendamiento (Cambio de fecha/hora por inasistencia del médico)")
                        nueva_fecha = st.date_input("Nueva Fecha de la Cita", datetime.strptime(c_actual[0], "%Y-%m-%d").date())
                        nueva_hora = st.time_input("Nueva Hora de la Cita", datetime.strptime(c_actual[1], "%H:%M:%S").time() if len(c_actual[1]) > 5 else datetime.strptime(c_actual[1], "%H:%M").time())
                        nuevo_venc = st.date_input("Actualizar Vencimiento Código ISSFA", datetime.strptime(c_actual[4], "%Y-%m-%d").date() if c_actual[4] else datetime.now())
                        motivo_reagenda = st.text_input("Motivo de Reagendamiento (Ej. Doctor no disponible, cambio de turno)", value=c_actual[5] if c_actual[5] else "")
            
                        if st.form_submit_button("Guardar Reagendamiento"):
                            conn = sqlite3.connect("clinica.db", check_same_thread=False)
                            cursor = conn.cursor()
                            cursor.execute("""
                                UPDATE citas 
                                SET fecha = ?, hora = ?, vencimiento_issfa = ?, estado = ?, observaciones = ? 
                                WHERE id = ?
                            """, (str(nueva_fecha), str(nueva_hora), str(nuevo_venc), "Reagendada", motivo_reagenda, id_cita_sel))
                            conn.commit()
                            conn.close()
                            st.success("¡Cita reagendada con éxito y registrada en el sistema!")
                            st.rerun()

                    if st.button("🗑️ Cancelar esta Cita por Completo", type="primary"):
                        conn = sqlite3.connect("clinica.db", check_same_thread=False)
                        cursor = conn.cursor()
                        cursor.execute("DELETE FROM citas WHERE id = ?", (id_cita_sel,))
                        conn.commit()
                        conn.close()
                        st.success("Cita eliminada.")
                        st.rerun()
    else:
        st.info("No hay citas registradas.")

# --- MÓDULO 5: CONSULTA MÉDICA E HISTORIAL ---
elif choice in ["Consulta Medica (Historial)", "Consulta Médica (Historial)"]:
    st.subheader("🩺 Atención Médica y Registro Clínico - Medisuport")
    conn = sqlite3.connect("clinica.db", check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute("SELECT cedula, nombre FROM pacientes")
    pacientes = cursor.fetchall()
    conn.close()
    pacientes_dict = {f"{p[1]} (Doc: {p[0]})": p[0] for p in pacientes}

    if pacientes_dict:
        paciente_sel = st.selectbox("Seleccione Paciente en Consulta", list(pacientes_dict.keys()))
        cedula_paciente = pacientes_dict[paciente_sel]

        conn = sqlite3.connect("clinica.db", check_same_thread=False)
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM pacientes WHERE cedula = ?", (cedula_paciente,))
        p_info = cursor.fetchone()
    
        cursor.execute("SELECT COUNT(*) FROM historial WHERE cedula_paciente = ?", (cedula_paciente,))
        conteo_atenciones = cursor.fetchone()[0]
        conn.close()

        tipo_consulta_auto = "C1" if conteo_atenciones == 0 else "SUB"

        st.info(f"**Paciente:** {p_info[2]} | **Doc:** {p_info[1]} | **Sistema de Salud / Previsión:** {p_info[9] if p_info[9] else 'No especificado'}")
        st.warning(f"📊 **Historial de visitas:** Ha asistido {conteo_atenciones} vez/veces previa(s). **Código Asignado para esta Consulta:** `{tipo_consulta_auto}` ({'Primera Vez' if tipo_consulta_auto == 'C1' else 'Subsecuente'})")

        with st.form("form_atencion_completa"):
            st.write("### 1. Antecedentes Clínicos")
            col1, col2 = st.columns(2)
            with col1:
                antecedentes_pers = st.text_area("Antecedentes Personales (Alergias, Crónicas, Cirugías)")
                antecedentes_fam = st.text_area("Antecedentes Heredo-Familiares")
            with col2:
                habitos = st.text_area("Hábitos de Vida (Tabaco, Alcohol, Actividad física)")

            st.write("### 2. Registro de Atención Actual")
            motivo = st.text_area("Motivo de Consulta")
            enfermedad_actual = st.text_area("Enfermedad Actual / Anamnesis (Síntomas y evolución)")

            st.write("### 3. Examen Físico y Signos Vitales")
            c1, c2, c3, c4, c5 = st.columns(5)
            with c1:
                peso = st.text_input("Peso (kg)")
            with c2:
                talla = st.text_input("Talla (cm)")
            with c3:
                pa = st.text_input("Presión Arterial (PA)")
            with c4:
                fc = st.text_input("Frecuencia Cardíaca (FC)")
            with c5:
                imc = st.text_input("Índice Masa Corporal (IMC)")

            st.write("### 4. Conclusión e Indicaciones")
            diagnostico = st.text_area("Diagnóstico o Impresión Diagnóstica")
            tratamiento = st.text_area("Indicaciones y Plan de Tratamiento (Receta, medicamentos)")
            examenes = st.text_area("Resultados de Exámenes / Laboratorios / Imágenes")

            finalizar = st.form_submit_button("Guardar Evolución y Cierre de Consulta")

            if finalizar:
                conn = sqlite3.connect("clinica.db", check_same_thread=False)
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO historial (
                        cedula_paciente, fecha_atencion, medico_atn, tipo_consulta, 
                        antecedentes_pers, antecedentes_fam, habitos, motivo, enfermedad_actual, 
                        peso, talla, pa, fc, imc, diagnostico, tratamiento, examenes
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    cedula_paciente, datetime.now().strftime("%Y-%m-%d %H:%M"), st.session_state['user_name'], tipo_consulta_auto,
                    antecedentes_pers, antecedentes_fam, habitos, motivo, enfermedad_actual,
                    peso, talla, pa, fc, imc, diagnostico, tratamiento, examenes
                ))
                conn.commit()
                conn.close()
                st.success(f"¡Atención clínica guardada con éxito bajo el código `{tipo_consulta_auto}`!")
                st.rerun()

        st.divider()
        st.subheader("📂 Historial de Consultas Anteriores del Paciente")
        conn = sqlite3.connect("clinica.db", check_same_thread=False)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT fecha_atencion, medico_atn, tipo_consulta, motivo, enfermedad_actual, 
                   antecedentes_pers, antecedentes_fam, habitos, peso, talla, pa, fc, imc, diagnostico, tratamiento, examenes 
            FROM historial WHERE cedula_paciente = ? ORDER BY id DESC
        """, (cedula_paciente,))
        historicos = cursor.fetchall()
        conn.close()

        if historicos:
            for h in historicos:
                with st.expander(f"Fecha: {h[0]} | Código: {h[2]} | Médico: {h[1]}"):
                    st.write(f"**Motivo:** {h[3]}")
                    st.write(f"**Enfermedad Actual:** {h[4]}")
                    st.write(f"**Antecedentes Personales:** {h[5]} | **Familiares:** {h[6]} | **Hábitos:** {h[7]}")
                    st.write(f"**Signos Vitales:** Peso: {h[8]}kg | Talla: {h[9]}cm | PA: {h[10]} | FC: {h[11]} | IMC: {h[12]}")
                    st.write(f"**Diagnóstico:** {h[13]}")
                    st.write(f"**Tratamiento:** {h[14]}")
                    st.write(f"**Exámenes:** {h[15]}")
        else:
            st.info("No hay registros previos para este paciente. Esta consulta se registrará como C1.")
    else:
        st.warning("No hay pacientes registrados.")

# --- MÓDULO 6: RESPALDO Y DATOS ---
elif choice == "Respaldo y Datos":
    st.subheader("📥 Respaldo y Reportes en Excel - Medisuport")
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
