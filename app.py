from datetime import datetime
import os
import io
import docx
from docx.shared import Inches, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH

psycopg2 = __import__("psycopg2")
pd = __import__("pandas")
st = __import__("streamlit")

# --- CONFIGURACIÓN DE LA PÁGINA ---
st.set_page_config(
    page_title="Medisuport - Sistema Clínico", page_icon="🏥", layout="wide"
)

# Cambie este valor cada vez que modifique la estructura de las tablas.
# Fuerza a Streamlit a descartar la conexión cacheada y a volver a ejecutar
# inicializar_tablas() (que crea/agrega las columnas que falten).
SCHEMA_VERSION = "2026-09-30-v3"

# Orden ÚNICO de columnas del historial (se usa en toda la app):
# 0:fecha, 1:medico, 2:tipo_consulta, 3:ant_pers, 4:ant_fam, 5:habitos,
# 6:motivo, 7:enfermedad, 8:peso, 9:talla, 10:pa, 11:fc, 12:imc,
# 13:diagnostico, 14:tratamiento, 15:examenes
COLUMNAS_HISTORIAL = [
    "fecha_atencion", "medico_atn", "tipo_consulta", "antecedentes_pers",
    "antecedentes_fam", "habitos", "motivo", "enfermedad_actual", "peso",
    "talla", "pa", "fc", "imc", "diagnostico", "tratamiento", "examenes",
]

OPCIONES_PREVISION = ["Particular / Propio de la Clínica", "ISSFA", "IESS", "MSP", "Seguro Privado"]


# --- CONEXIÓN A SUPABASE: SESSION POOLER ---
def init_connection():
    password = os.environ.get("DB_PASSWORD")
    if not password:
        try:
            password = st.secrets["DB_PASSWORD"]
        except (FileNotFoundError, KeyError):
            st.error(
                "Falta configurar DB_PASSWORD. Coloque el archivo secrets.toml "
                "dentro de la carpeta .streamlit del proyecto."
            )
            st.stop()
    return psycopg2.connect(
        host="aws-0-us-west-2.pooler.supabase.co",
        port=6543,
        dbname="postgres",
        user="postgres.vktnksyxgtgphohpjmke",
        password=password,
        sslmode="require",
        connect_timeout=15,
        options="-c search_path=public",
    )


def inicializar_tablas(connection):
    """Crea tablas y añade columnas ausentes conservando los datos existentes."""
    tablas = {
        "pacientes": """
            CREATE TABLE public.pacientes (
                cedula TEXT PRIMARY KEY,
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
        """,
        "disponibilidad": """
            CREATE TABLE public.disponibilidad (
                medico TEXT PRIMARY KEY,
                especialidad TEXT NOT NULL,
                dias TEXT,
                horas TEXT
            )
        """,
        "citas": """
            CREATE TABLE public.citas (
                id BIGSERIAL PRIMARY KEY,
                cedula_paciente TEXT NOT NULL REFERENCES public.pacientes(cedula),
                fecha TEXT NOT NULL,
                hora TEXT NOT NULL,
                medico TEXT NOT NULL,
                especialidad TEXT,
                vencimiento_issfa TEXT,
                estado TEXT DEFAULT 'Agendada',
                observaciones TEXT
            )
        """,
        "historial": """
            CREATE TABLE public.historial (
                id BIGSERIAL PRIMARY KEY,
                cedula_paciente TEXT NOT NULL REFERENCES public.pacientes(cedula),
                fecha_atencion TEXT NOT NULL,
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
                examenes TEXT
            )
        """,
    }
    columnas = {
        "pacientes": "cedula, nombre, sexo, fecha_nacimiento, domicilio, telefono, correo, ocupacion, prevision, origen",
        "disponibilidad": "medico, especialidad, dias, horas",
        "citas": "id, cedula_paciente, fecha, hora, medico, especialidad, vencimiento_issfa, estado, observaciones",
        "historial": "id, cedula_paciente, fecha_atencion, medico_atn, tipo_consulta, antecedentes_pers, antecedentes_fam, habitos, motivo, enfermedad_actual, peso, talla, pa, fc, imc, diagnostico, tratamiento, examenes",
    }
    with connection:
        with connection.cursor() as cur:
            cur.execute("SELECT pg_advisory_xact_lock(7352026)")
            for nombre, ddl in tablas.items():
                cur.execute("SELECT to_regclass(%s)", (f"public.{nombre}",))
                if cur.fetchone()[0] is None:
                    cur.execute(ddl)
                    cur.execute(f"ALTER TABLE public.{nombre} ENABLE ROW LEVEL SECURITY")

                cur.execute(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_schema = %s AND table_name = %s",
                    ("public", nombre),
                )
                existentes = {fila[0] for fila in cur.fetchall()}
                for columna in columnas[nombre].split(", "):
                    if columna not in existentes:
                        tipo = "BIGSERIAL" if columna == "id" else "TEXT"
                        cur.execute(
                            f"ALTER TABLE public.{nombre} "
                            f"ADD COLUMN IF NOT EXISTS {columna} {tipo}"
                        )
                cur.execute(f"SELECT {columnas[nombre]} FROM public.{nombre} LIMIT 0")


@st.cache_resource(show_spinner="Conectando con la base de datos...")
def _conectar(schema_version):
    # schema_version participa en la clave de caché: al cambiarla se vuelve
    # a abrir la conexión y a ejecutar inicializar_tablas().
    connection = init_connection()
    try:
        inicializar_tablas(connection)
    except Exception:
        connection.close()
        raise
    return connection


def get_db_connection():
    connection = _conectar(SCHEMA_VERSION)
    try:
        if connection.closed:
            raise psycopg2.InterfaceError("Conexión cerrada")
        connection.rollback()  # limpia cualquier transacción abortada previa
        with connection.cursor() as c:
            c.execute("SELECT 1")
        connection.rollback()
    except psycopg2.Error:
        # Conexión caída o inservible: se descarta y se vuelve a crear.
        _conectar.clear()
        connection = _conectar(SCHEMA_VERSION)
    return connection


try:
    conn = get_db_connection()
    cursor = conn.cursor()
except psycopg2.Error as e:
    st.error(f"No se pudo conectar o preparar las tablas de Supabase: {e}")
    st.stop()


# --- FUNCIONES DE ACCESO SEGURO A LA BASE DE DATOS ---
def consultar(sql, params=None):
    """Ejecuta un SELECT y devuelve todas las filas. Hace rollback si falla."""
    try:
        cursor.execute(sql, params)
        return cursor.fetchall()
    except psycopg2.Error as err:
        conn.rollback()
        st.error(f"Error de base de datos al consultar: {err}")
        return []


def consultar_uno(sql, params=None):
    filas = consultar(sql, params)
    return filas[0] if filas else None


def ejecutar(operaciones):
    """Ejecuta una o varias sentencias (sql, params) en una sola transacción."""
    if isinstance(operaciones, tuple):
        operaciones = [operaciones]
    try:
        for sql, params in operaciones:
            cursor.execute(sql, params)
        conn.commit()
        return True
    except psycopg2.Error as err:
        conn.rollback()
        st.error(f"Error de base de datos: {err}")
        return False


def obtener_historial(cedula):
    """
    Devuelve las atenciones del paciente (más recientes primero) como tuplas
    en el orden de COLUMNAS_HISTORIAL. Usa SELECT * y mapea por nombre, por lo
    que nunca falla por columnas indefinidas: lo que falte se muestra vacío.
    """
    try:
        cursor.execute("SELECT * FROM historial WHERE cedula_paciente = %s", (cedula,))
        nombres = [d[0] for d in cursor.description]
        filas = [dict(zip(nombres, f)) for f in cursor.fetchall()]
    except psycopg2.Error as err:
        conn.rollback()
        st.error(f"No se pudo cargar el historial clínico: {err}")
        return []
    filas.sort(key=lambda r: (r.get("id") or 0), reverse=True)
    return [
        tuple("" if r.get(c) is None else r.get(c) for c in COLUMNAS_HISTORIAL)
        for r in filas
    ]


# --- CONFIGURACIÓN DE TEMA CLARO ---
st.markdown("""
    <style>
    .main { background-color: #FFFFFF; color: #000000; }
    .stSidebar { background-color: #F8F9FA; }
    </style>
    """, unsafe_allow_html=True)


# --- INICIALIZACIÓN DE DATOS INICIALES (DISPONIBILIDAD) ---
def verificar_y_poblar_disponibilidad():
    try:
        cursor.execute("SELECT COUNT(*) FROM disponibilidad")
        if cursor.fetchone()[0] == 0:
            default_data = [
                ("Dra. Kanie Collado", "Alergología", "Lunes y Miércoles", "08:00 - 13:00"),
                ("Dr. Norberto Carballosa", "Anestesiología", "Martes y Jueves", "09:00 - 14:00"),
                ("Dra. Lisset Alfonso", "Cardiología", "Lunes, Miércoles y Viernes", "08:00 - 12:00"),
                ("Dr. Miguel Mederos", "Dermatología", "Martes y Viernes", "13:00 - 18:00"),
                ("Dr. Frank Medina", "Endocrinología", "Martes y Jueves", "08:00 - 12:00"),
                ("Dr. Miguel Marrero", "Endocrinología", "Lunes y Miércoles", "14:00 - 18:00"),
                ("Dra. Gabriela Vélez", "Endocrinología", "Viernes", "08:00 - 13:00"),
                ("Dr. Pavel Mili", "Fisiatría", "Lunes y Jueves", "08:00 - 13:00"),
                ("Dr. Yunio Torres", "Fisiatría", "Martes y Miércoles", "13:00 - 17:00"),
                ("Dr. Frank Pérez", "Gastroenterología", "Lunes a Viernes", "08:00 - 12:00"),
                ("Dra. Mildred", "Geriatría", "Miércoles y Viernes", "09:00 - 14:00"),
                ("Dr. Alejandro Argiz", "Ginecología", "Lunes y Martes", "08:00 - 13:00"),
                ("Dra. Marilyn Martínez", "Ginecología", "Miércoles y Jueves", "13:00 - 18:00"),
                ("Dra. Osmarie Barbosa", "Logopedia / Medicina General", "Lunes a Viernes", "08:00 - 16:00"),
                ("Dr. Yoandis Pérez", "Medicina General", "Lunes a Viernes", "08:00 - 16:00"),
                ("Dra. Ailicec Arias", "Medicina General / Pediatría", "Lunes a Viernes", "08:00 - 16:00"),
                ("Dr. Ovadiz Pérez", "Medicina Interna", "Lunes, Miércoles y Viernes", "08:00 - 13:00"),
                ("Dra. Eva Barbosa", "Neumología", "Martes y Jueves", "09:00 - 14:00"),
                ("Dr. Dayron Douglas Calvo", "Neurología", "Lunes y Miércoles", "09:00 - 13:00"),
                ("Lcdo. Andrés Hidrobo", "Nutrición", "Martes y Jueves", "08:00 - 15:00"),
                ("Dr. Fernando Enríquez", "Otorrinolaringología", "Lunes, Miércoles y Viernes", "13:00 - 17:00"),
                ("Dra. María Cristina Torres", "Pediatría", "Lunes a Viernes", "08:00 - 13:00"),
                ("Lcdo. Jerson Rodríguez", "Psicología", "Lunes a Viernes", "09:00 - 17:00"),
                ("Dra. Yulca Rosales", "Psiquiatría", "Martes y Jueves", "14:00 - 18:00"),
                ("Dr. Dennis Pucha", "Reumatología", "Lunes y Miércoles", "08:00 - 12:00"),
                ("Dr. Rafael Echavarría", "Reumatología", "Martes y Jueves", "13:00 - 17:00"),
                ("Dr. Antonio Leal", "Traumatología", "Lunes a Viernes", "08:00 - 14:00"),
                ("Dr. William Fonseca", "Urología", "Lunes, Miércoles y Viernes", "08:00 - 13:00")
            ]
            for d in default_data:
                cursor.execute("""
                    INSERT INTO disponibilidad (medico, especialidad, dias, horas)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (medico) DO NOTHING
                """, d)
        conn.commit()
    except psycopg2.Error as err:
        conn.rollback()  # Limpia la transacción abortada de inmediato
        st.error(f"No se pudo preparar la disponibilidad de médicos: {err}")
        st.stop()


verificar_y_poblar_disponibilidad()


# --- FUNCIONES AUXILIARES PARA CARGAR DISPONIBILIDAD DESDE DB ---
def obtener_medicos_info():
    try:
        cursor.execute("SELECT medico, especialidad, dias, horas FROM disponibilidad ORDER BY especialidad, medico")
        rows = cursor.fetchall()
        info = {}
        for r in rows:
            info[r[0]] = {"esp": r[1], "dias": r[2] or "", "horas": r[3] or ""}
        return info
    except psycopg2.Error as err:
        conn.rollback()
        st.error(f"No se pudo cargar la disponibilidad de médicos: {err}")
        st.stop()


def obtener_medicos_especialidades():
    medicos_info = obtener_medicos_info()
    esp_dict = {}
    for doc, info in medicos_info.items():
        esp = info["esp"]
        if esp not in esp_dict:
            esp_dict[esp] = []
        esp_dict[esp].append(doc)
    return esp_dict


# --- SISTEMA DE AUTENTICACIÓN POR ROLES ---
def obtener_usuarios():
    medicos_info = obtener_medicos_info()
    users = {
        "Abigail Ruiz (Secretaria)": {"pass": "sec2026", "role": "secretaria"},
        "Administrador": {"pass": "admin2026", "role": "admin"}
    }
    for doc in medicos_info.keys():
        users[f"{doc} ({medicos_info[doc]['esp']})"] = {"pass": "med123", "role": "medico"}
    return users


USERS = obtener_usuarios()

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
    st.session_state["user_name"] = ""
    st.session_state["user_role"] = ""
    st.rerun()

st.sidebar.divider()
role = st.session_state["user_role"]

if role == "secretaria":
    menu = ["Registrar Paciente", "Buscar y Gestionar Pacientes", "Listado de Pacientes", "Disponibilidad de Medicos", "Agendamiento de Citas", "Respaldo y Datos"]
elif role == "medico":
    menu = ["Buscar y Gestionar Pacientes", "Listado de Pacientes", "Disponibilidad de Medicos", "Ver Agenda de Citas", "Consulta Medica (Historial)"]
else:
    menu = ["Registrar Paciente", "Buscar y Gestionar Pacientes", "Listado de Pacientes", "Disponibilidad de Medicos", "Agendamiento de Citas", "Consulta Medica (Historial)", "Respaldo y Datos"]

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
    p_info.add_run(f"{info_p[1]}\n")
    p_info.add_run("• Documento de Identidad: ").bold = True
    p_info.add_run(f"{info_p[0]}\n")
    p_info.add_run("• Sexo: ").bold = True
    p_info.add_run(f"{info_p[2]}    |   ")
    p_info.add_run("Fecha de Nacimiento: ").bold = True
    p_info.add_run(f"{info_p[3]}\n")
    p_info.add_run("• Domicilio: ").bold = True
    p_info.add_run(f"{info_p[4]}\n")
    p_info.add_run("• Teléfono: ").bold = True
    p_info.add_run(f"{info_p[5]}    |   ")
    p_info.add_run("Correo: ").bold = True
    p_info.add_run(f"{info_p[6]}\n")
    p_info.add_run("• Ocupación: ").bold = True
    p_info.add_run(f"{info_p[7]}    |   ")
    p_info.add_run("Sistema de Salud: ").bold = True
    p_info.add_run(f"{info_p[8]}\n")
    p_info.add_run("• Origen de Registro: ").bold = True
    p_info.add_run(f"{info_p[9] if len(info_p) > 9 else 'N/A'}\n")
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
            # Índices según COLUMNAS_HISTORIAL
            p_atn = doc.add_paragraph()
            p_atn.add_run(f"Atención #{len(historial_p) - idx + 1} - Fecha: {h[0]} [Código: {h[2]}]\n").bold = True
            p_atn.add_run(f"Médico Tratante: {h[1]}\n").italic = True

            p_atn.add_run("  - Motivo de Consulta: ").bold = True
            p_atn.add_run(f"{h[6]}\n")
            p_atn.add_run("  - Enfermedad Actual / Anamnesis: ").bold = True
            p_atn.add_run(f"{h[7]}\n")
            p_atn.add_run("  - Antecedentes Personales: ").bold = True
            p_atn.add_run(f"{h[3]} | Familiares: {h[4]} | Hábitos: {h[5] if h[5] else 'No especificado'}\n")
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
            f_nac = st.date_input("Fecha de Nacimiento", value=datetime(1990, 1, 1), min_value=datetime(1900, 1, 1), max_value=datetime.now())
            telefono = st.text_input("Teléfono / Celular")
        with col2:
            correo = st.text_input("Correo Electrónico")
            domicilio = st.text_input("Domicilio / Dirección")
            ocupacion = st.text_input("Ocupación")
            prevision = st.selectbox("Sistema de Salud / Previsión", OPCIONES_PREVISION)
            origen = st.selectbox("Origen de Registro", ["Propio de la Clínica", "Prestador Externo ISSFA"])

        guardar = st.form_submit_button("Guardar Ficha del Paciente")

        if guardar:
            if cedula.strip() and nombre.strip():
                try:
                    cursor.execute("""
                        INSERT INTO pacientes (cedula, nombre, sexo, fecha_nacimiento, domicilio, telefono, correo, ocupacion, prevision, origen)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """, (cedula.strip(), nombre.strip(), sexo, str(f_nac), domicilio, telefono, correo, ocupacion, prevision, origen))
                    conn.commit()
                    st.success(f"¡Paciente {nombre} registrado con éxito en la nube!")
                except psycopg2.errors.UniqueViolation:
                    conn.rollback()
                    st.error("Ya existe un paciente registrado con este número de documento.")
                except psycopg2.Error as err:
                    conn.rollback()
                    st.error(f"No se pudo registrar el paciente: {err}")
            else:
                st.warning("Complete al menos el número de documento y el nombre completo.")

# --- MÓDULO 2: BUSCAR Y GESTIONAR PACIENTES ---
elif choice == "Buscar y Gestionar Pacientes":
    st.subheader("🔍 Ficha Clínica y Búsqueda de Pacientes")
    pacientes_db = consultar("SELECT cedula, nombre FROM pacientes ORDER BY nombre")

    if pacientes_db:
        opciones_busqueda = {f"{p[1]} (Doc: {p[0]})": p[0] for p in pacientes_db}
        paciente_elegido = st.selectbox("Seleccione Paciente", list(opciones_busqueda.keys()))
        cedula_buscar = opciones_busqueda[paciente_elegido]

        if st.button("Consultar Ficha Completa"):
            st.session_state["ficha_abierta"] = cedula_buscar

        # La ficha se mantiene visible aunque la página se recargue (p. ej. al descargar el Word)
        if st.session_state.get("ficha_abierta") == cedula_buscar:
            info_p = consultar_uno("SELECT cedula, nombre, sexo, fecha_nacimiento, domicilio, telefono, correo, ocupacion, prevision, origen FROM pacientes WHERE cedula = %s", (cedula_buscar,))
            historial_p = obtener_historial(cedula_buscar)
            visitas = len(historial_p)
            codigo_estado = "C1" if visitas == 0 else "SUB"

            if info_p:
                st.success("¡Ficha de Paciente Encontrada!")
                st.write(f"**Nombre:** {info_p[1]} | **Sexo:** {info_p[2]} | **F. Nacimiento:** {info_p[3]}")
                st.write(f"**Documento:** {info_p[0]} | **Teléfono:** {info_p[5]} | **Correo:** {info_p[6]}")
                st.write(f"**Domicilio:** {info_p[4]} | **Ocupación:** {info_p[7]} | **Sistema de Salud:** {info_p[8]}")
                st.info(f"📊 **Total de Atenciones Previas:** {visitas} | **Código Actual:** `{codigo_estado}`")

                word_bytes = generar_documento_word(info_p, visitas, codigo_estado, historial_p)

                st.download_button(
                    label="📥 Descargar Historia Clínica en Formato Word (.docx)",
                    data=word_bytes,
                    file_name=f"Historia_Clinica_{info_p[0]}.docx",
                    mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                )

                if historial_p:
                    st.write("### 📂 Historial de Atenciones Clínicas Anteriores")
                    for h in historial_p:
                        with st.expander(f"Atención del {h[0]} | Código: {h[2]} | Médico: {h[1]}"):
                            st.write(f"**Motivo de Consulta:** {h[6]}")
                            st.write(f"**Enfermedad Actual / Anamnesis:** {h[7]}")
                            st.write(f"**Antecedentes Personales:** {h[3]} | **Familiares:** {h[4]} | **Hábitos:** {h[5] if h[5] else 'No especificado'}")
                            st.write(f"**Signos Vitales y Antropometría:** Peso: {h[8]} kg | Talla: {h[9]} cm | PA: {h[10]} | FC: {h[11]} lpm | IMC: {h[12]}")
                            st.write(f"**Diagnóstico:** {h[13]}")
                            st.write(f"**Tratamiento y Receta:** {h[14]}")
                            st.write(f"**Resultados de Exámenes:** {h[15]}")
                else:
                    st.warning("Este paciente no cuenta con consultas previas registradas (Le corresponde código C1).")

        st.divider()

        # Módulo para editar datos del paciente
        with st.expander("✏️ Editar Datos del Paciente"):
            p_edit = consultar_uno("SELECT nombre, sexo, domicilio, telefono, correo, ocupacion, prevision FROM pacientes WHERE cedula = %s", (cedula_buscar,))
            if p_edit:
                with st.form("form_editar_paciente"):
                    nuevo_nombre = st.text_input("Nombre Completo", value=p_edit[0] or "")
                    nuevo_domicilio = st.text_input("Domicilio", value=p_edit[2] if p_edit[2] else "")
                    nuevo_telefono = st.text_input("Teléfono", value=p_edit[3] if p_edit[3] else "")
                    nuevo_correo = st.text_input("Correo", value=p_edit[4] if p_edit[4] else "")
                    nueva_ocupacion = st.text_input("Ocupación", value=p_edit[5] if p_edit[5] else "")
                    idx_prev = OPCIONES_PREVISION.index(p_edit[6]) if p_edit[6] in OPCIONES_PREVISION else 0
                    nueva_prevision = st.selectbox("Sistema de Salud", OPCIONES_PREVISION, index=idx_prev)

                    if st.form_submit_button("Guardar Cambios del Paciente"):
                        ok = ejecutar(("""
                            UPDATE pacientes
                            SET nombre = %s, domicilio = %s, telefono = %s, correo = %s, ocupacion = %s, prevision = %s
                            WHERE cedula = %s
                        """, (nuevo_nombre, nuevo_domicilio, nuevo_telefono, nuevo_correo, nueva_ocupacion, nueva_prevision, cedula_buscar)))
                        if ok:
                            st.success("¡Datos del paciente actualizados correctamente!")
                            st.rerun()

        if role in ["secretaria", "admin"]:
            with st.expander("🗑️ Zona de Peligro: Borrar Paciente"):
                if st.button("Eliminar Definitivamente a este Paciente", type="primary"):
                    ok = ejecutar([
                        ("DELETE FROM historial WHERE cedula_paciente = %s", (cedula_buscar,)),
                        ("DELETE FROM citas WHERE cedula_paciente = %s", (cedula_buscar,)),
                        ("DELETE FROM pacientes WHERE cedula = %s", (cedula_buscar,)),
                    ])
                    if ok:
                        st.session_state.pop("ficha_abierta", None)
                        st.success("Paciente eliminado correctamente.")
                        st.rerun()
    else:
        st.info("No hay pacientes registrados en el sistema.")

# --- MÓDULO 3: LISTADO GENERAL DE PACIENTES ---
elif choice == "Listado de Pacientes":
    st.subheader("📋 Base de Datos General de Pacientes")
    filas_p = consultar("SELECT cedula, nombre, sexo, telefono, correo, prevision, origen FROM pacientes ORDER BY nombre")
    df_p = pd.DataFrame(filas_p, columns=["cedula", "nombre", "sexo", "telefono", "correo", "prevision", "origen"])

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

# --- MÓDULO GESTIÓN DE DISPONIBILIDAD ---
elif choice == "Disponibilidad de Medicos":
    st.subheader("📅 Gestión de Disponibilidad y Horarios de Médicos")
    st.write("Visualice y actualice los días y horas de atención según el día a día institucional.")

    MEDICOS_INFO = obtener_medicos_info()
    MEDICOS_ESPECIALIDADES = obtener_medicos_especialidades()

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

    if role in ["secretaria", "admin"] and MEDICOS_INFO:
        st.divider()
        st.write("### 🛠️ Actualizar Disponibilidad Diaria del Médico")
        with st.form("form_editar_disponibilidad"):
            medico_a_editar = st.selectbox("Seleccionar Médico", list(MEDICOS_INFO.keys()))
            info_actual = MEDICOS_INFO[medico_a_editar]

            nuevo_dia = st.text_input("Días de Atención", value=info_actual["dias"])
            nuevo_horario = st.text_input("Horario", value=info_actual["horas"])

            actualizar_disp = st.form_submit_button("Guardar Cambios de Disponibilidad")

            if actualizar_disp:
                ok = ejecutar(("""
                    UPDATE disponibilidad
                    SET dias = %s, horas = %s
                    WHERE medico = %s
                """, (nuevo_dia, nuevo_horario, medico_a_editar)))
                if ok:
                    st.success(f"✅ ¡Disponibilidad actualizada con éxito para {medico_a_editar}!")
                    st.rerun()

# --- MÓDULO 4: AGENDAMIENTO DE CITAS ---
elif choice in ["Agendamiento de Citas", "Ver Agenda de Citas"]:
    st.subheader("📅 Agendamiento de Citas Médicas e Institucionales")

    MEDICOS_INFO = obtener_medicos_info()
    MEDICOS_ESPECIALIDADES = obtener_medicos_especialidades()

    if role in ["secretaria", "admin"]:
        pacientes = consultar("SELECT cedula, nombre, origen FROM pacientes ORDER BY nombre")
        pacientes_dict = {f"{p[1]} (Doc: {p[0]} - {p[2]})": p[0] for p in pacientes}

        st.write("### Agendar Nueva Cita (Verificación de Disponibilidad y Código ISSFA)")
        if pacientes_dict:
            paciente_sel = st.selectbox("Seleccionar Paciente", list(pacientes_dict.keys()), key="select_paciente_cita")
            cedula_act = pacientes_dict[paciente_sel]
        else:
            st.warning("Debe registrar pacientes primero.")
            cedula_act = ""

        if MEDICOS_ESPECIALIDADES:
            especialidad_sel = st.selectbox("Especialidad Médica", list(MEDICOS_ESPECIALIDADES.keys()), key="select_especialidad_cita")
            medicos_disponibles = MEDICOS_ESPECIALIDADES[especialidad_sel]

            medico_sel = st.selectbox("Médico Tratante", medicos_disponibles, key="select_medico_cita")
            info_med = MEDICOS_INFO[medico_sel]
            st.info(f"💡 **Disponibilidad actual en el sistema para {medico_sel}:** {info_med['dias']} en horario de {info_med['horas']}.")

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

                    fila_conf = consultar_uno("SELECT COUNT(*) FROM citas WHERE medico = %s AND fecha = %s AND hora = %s", (medico_sel, str_fecha, str_hora))
                    conf_count = fila_conf[0] if fila_conf else 0

                    if conf_count > 0:
                        st.error(f"❌ El/La Dr(a). {medico_sel} ya tiene una cita agendada a esa hora y fecha exactas.")
                    else:
                        ok = ejecutar(("""
                            INSERT INTO citas (cedula_paciente, fecha, hora, medico, especialidad, vencimiento_issfa, estado, observaciones)
                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                        """, (cedula_act, str_fecha, str_hora, medico_sel, especialidad_sel, str_venc, "Agendada", observaciones)))
                        if ok:
                            st.success(f"✅ ¡Cita agendada con éxito para el Dr(a). {medico_sel} el {str_fecha} a las {str_hora}!")
        else:
            st.warning("No hay médicos configurados en la disponibilidad.")
        st.divider()

    st.subheader("📋 Listado y Gestión de Citas (Reagendamientos y Estado)")
    if role == "medico":
        nombre_sesion = st.session_state['user_name']
        doctor_limpio = nombre_sesion.split(" (")[0]
        citas_data = consultar("""
            SELECT c.id, c.fecha, c.hora, p.nombre, c.medico, c.especialidad, c.vencimiento_issfa, c.estado, c.observaciones
            FROM citas c JOIN pacientes p ON c.cedula_paciente = p.cedula
            WHERE c.medico = %s
            ORDER BY c.fecha, c.hora
        """, (doctor_limpio,))
        st.info(f"Mostrando únicamente las citas asignadas a **{doctor_limpio}**.")
    else:
        citas_data = consultar("""
            SELECT c.id, c.fecha, c.hora, p.nombre, c.medico, c.especialidad, c.vencimiento_issfa, c.estado, c.observaciones
            FROM citas c JOIN pacientes p ON c.cedula_paciente = p.cedula
            ORDER BY c.fecha, c.hora
        """)

    if citas_data:
        df_citas_view = pd.DataFrame(citas_data, columns=["ID", "Fecha", "Hora", "Paciente", "Médico", "Especialidad", "Vencimiento ISSFA", "Estado", "Observaciones"])
        st.dataframe(df_citas_view.drop(columns=["ID"]), use_container_width=True)

        if role in ["secretaria", "admin"]:
            st.divider()
            with st.expander("🛠️ Reagendar, Modificar o Cancelar una Cita"):
                citas_dict = {f"Cita ID: {c[0]} | Paciente: {c[3]} | Fecha: {c[1]} {c[2]} | Dr(a). {c[4]}": c[0] for c in citas_data}
                cita_sel_mod = st.selectbox("Seleccione la cita a gestionar", list(citas_dict.keys()))
                id_cita_sel = citas_dict[cita_sel_mod]

                c_actual = consultar_uno("SELECT fecha, hora, medico, especialidad, vencimiento_issfa, observaciones FROM citas WHERE id = %s", (id_cita_sel,))

                if c_actual:
                    st.write(f"**Cita Actual:** {c_actual[0]} a las {c_actual[1]} con {c_actual[2]} ({c_actual[3]})")

                    try:
                        fecha_def = datetime.strptime(c_actual[0], "%Y-%m-%d").date()
                    except (TypeError, ValueError):
                        fecha_def = datetime.now().date()
                    try:
                        hora_txt = c_actual[1].split(".")[0]
                        hora_def = datetime.strptime(hora_txt, "%H:%M:%S").time() if len(hora_txt) > 5 else datetime.strptime(hora_txt, "%H:%M").time()
                    except (TypeError, ValueError, AttributeError):
                        hora_def = datetime.now().time().replace(second=0, microsecond=0)
                    try:
                        venc_def = datetime.strptime(c_actual[4], "%Y-%m-%d").date() if c_actual[4] else datetime.now().date()
                    except (TypeError, ValueError):
                        venc_def = datetime.now().date()

                    with st.form("form_reagendar_cita"):
                        st.write("### Módulo de Reagendamiento")
                        nueva_fecha = st.date_input("Nueva Fecha de la Cita", fecha_def)
                        nueva_hora = st.time_input("Nueva Hora de la Cita", hora_def)
                        nuevo_venc = st.date_input("Actualizar Vencimiento Código ISSFA", venc_def)
                        motivo_reagenda = st.text_input("Motivo de Reagendamiento", value=c_actual[5] if c_actual[5] else "")

                        if st.form_submit_button("Guardar Reagendamiento"):
                            ok = ejecutar(("""
                                UPDATE citas
                                SET fecha = %s, hora = %s, vencimiento_issfa = %s, estado = %s, observaciones = %s
                                WHERE id = %s
                            """, (str(nueva_fecha), str(nueva_hora), str(nuevo_venc), "Reagendada", motivo_reagenda, id_cita_sel)))
                            if ok:
                                st.success("¡Cita reagendada con éxito!")
                                st.rerun()

                    if st.button("🗑️ Cancelar esta Cita por Completo", type="primary"):
                        if ejecutar(("DELETE FROM citas WHERE id = %s", (id_cita_sel,))):
                            st.success("Cita eliminada.")
                            st.rerun()
    else:
        st.info("No hay citas registradas.")

# --- MÓDULO 5: CONSULTA MÉDICA E HISTORIAL ---
elif choice in ["Consulta Medica (Historial)", "Consulta Médica (Historial)"]:
    st.subheader("🩺 Atención Médica y Registro Clínico - Medisuport")
    pacientes = consultar("SELECT cedula, nombre FROM pacientes ORDER BY nombre")
    pacientes_dict = {f"{p[1]} (Doc: {p[0]})": p[0] for p in pacientes}

    if pacientes_dict:
        paciente_sel = st.selectbox("Seleccione Paciente en Consulta", list(pacientes_dict.keys()))
        cedula_paciente = pacientes_dict[paciente_sel]

        p_info = consultar_uno("SELECT cedula, nombre, sexo, fecha_nacimiento, domicilio, telefono, correo, ocupacion, prevision, origen FROM pacientes WHERE cedula = %s", (cedula_paciente,))
        historicos = obtener_historial(cedula_paciente)
        conteo_atenciones = len(historicos)

        tipo_consulta_auto = "C1" if conteo_atenciones == 0 else "SUB"

        if p_info:
            st.info(f"**Paciente:** {p_info[1]} | **Doc:** {p_info[0]} | **Sistema de Salud / Previsión:** {p_info[8] if p_info[8] else 'No especificado'}")
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
                ok = ejecutar(("""
                    INSERT INTO historial (
                        cedula_paciente, fecha_atencion, medico_atn, tipo_consulta,
                        antecedentes_pers, antecedentes_fam, habitos, motivo, enfermedad_actual,
                        peso, talla, pa, fc, imc, diagnostico, tratamiento, examenes
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """, (
                    cedula_paciente, datetime.now().strftime("%Y-%m-%d %H:%M"), st.session_state['user_name'], tipo_consulta_auto,
                    antecedentes_pers, antecedentes_fam, habitos, motivo, enfermedad_actual,
                    peso, talla, pa, fc, imc, diagnostico, tratamiento, examenes
                )))
                if ok:
                    st.success(f"¡Atención clínica guardada con éxito en la nube bajo el código `{tipo_consulta_auto}`!")
                    st.rerun()

        st.divider()
        st.subheader("📂 Historial de Consultas Anteriores del Paciente")

        if historicos:
            for h in historicos:
                with st.expander(f"Fecha: {h[0]} | Código: {h[2]} | Médico: {h[1]}"):
                    st.write(f"**Motivo:** {h[6]}")
                    st.write(f"**Enfermedad Actual:** {h[7]}")
                    st.write(f"**Antecedentes Personales:** {h[3]} | **Familiares:** {h[4]} | **Hábitos:** {h[5] if h[5] else 'No especificado'}")
                    st.write(f"**Signos Vitales:** Peso: {h[8]}kg | Talla: {h[9]}cm | PA: {h[10]} | FC: {h[11]} | IMC: {h[12]}")
                    st.write(f"**Diagnóstico:** {h[13]}")
                    st.write(f"**Tratamiento:** {h[14]}")
                    st.write(f"**Exámenes:** {h[15]}")
        else:
            st.info("No hay registros previos para este paciente.")
    else:
        st.warning("No hay pacientes registrados.")

# --- MÓDULO 6: RESPALDO Y DATOS ---
elif choice == "Respaldo y Datos":
    st.subheader("📥 Respaldo y Reportes en Excel - Medisuport")
    st.write("Genera y descarga un archivo de Excel (`.xlsx`) con toda la información general de la clínica desde la nube.")

    if st.button("Generar Reporte Excel Completo"):
        try:
            df_pacientes = pd.read_sql_query("SELECT * FROM pacientes", conn)
            df_citas = pd.read_sql_query("SELECT * FROM citas", conn)
            df_historial = pd.read_sql_query("SELECT * FROM historial", conn)
            conn.rollback()  # cierra la transacción de lectura

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
        except Exception as err:
            conn.rollback()
            st.error(f"No se pudo generar el respaldo: {err}")
