"""Medisuport v2 — interfaz Streamlit."""
from datetime import date, datetime, time, timedelta
from calendar import monthrange
from pathlib import Path
import io, json, logging, traceback, re, unicodedata, base64
import pandas as pd
import streamlit as st
from psycopg2.errors import ExclusionViolation, UniqueViolation

from core import Database, AppError, TZ, WEEKDAYS, STATUSES, now, local_datetime, proper_name, normalize_doc
from exports import word_history, clinical_excel, clinical_pdf, certificate_pdf, certificate_word, billing_statement_pdf, excel
from legacy import preview as legacy_preview, import_legacy, issues as legacy_issues

st.set_page_config(page_title="Medisuport", page_icon="🏥", layout="wide")
logging.basicConfig(level=logging.INFO)
st.markdown("""
<style>
:root{
  --med-primary:#0f4c5c;
  --med-primary-2:#147d92;
  --med-accent:#22a699;
  --med-bg:#f3f7fa;
  --med-surface:#ffffff;
  --med-text:#17313a;
  --med-muted:#506670;
  --med-border:#dce7ec;
}
.stApp{
  background:
    radial-gradient(circle at 92% 4%,rgba(34,166,153,.10),transparent 24rem),
    linear-gradient(180deg,#f8fbfc 0%,var(--med-bg) 100%);
  color:var(--med-text);
}
.block-container{padding-top:1.65rem;padding-bottom:3rem;max-width:1480px}
h1,h2,h3{color:var(--med-primary);letter-spacing:-.025em}
h1{font-weight:800!important;margin-bottom:.3rem!important}
h2,h3{font-weight:750!important}
p,.stCaption{color:var(--med-muted)}
[data-testid="stSidebar"]{
  background:linear-gradient(180deg,#0b3c49 0%,#0f5968 100%);
  border-right:1px solid rgba(255,255,255,.10);
}
[data-testid="stSidebar"] *{color:#f4fbfc!important}
[data-testid="stSidebar"] [data-baseweb="radio"] label{
  border-radius:10px;padding:.38rem .55rem;margin:.08rem 0;
}
[data-testid="stSidebar"] [data-baseweb="radio"] label:hover{background:rgba(255,255,255,.10)}
[data-testid="stSidebar"] hr{border-color:rgba(255,255,255,.18)}
[data-testid="stSidebar"] button{
  background:rgba(255,255,255,.10)!important;
  border-color:rgba(255,255,255,.28)!important;
}
[data-testid="stForm"],[data-testid="stMainBlockContainer"] div[data-testid="stExpander"]{
  background:rgba(255,255,255,.94);
  border:1px solid var(--med-border)!important;
  border-radius:16px!important;
  box-shadow:0 8px 28px rgba(15,76,92,.07);
}
[data-testid="stForm"]{padding:1.2rem 1.25rem .55rem}
[data-testid="stMetric"]{
  background:linear-gradient(145deg,#ffffff,#f4fbfb);
  border:1px solid var(--med-border);
  border-left:5px solid var(--med-accent);
  border-radius:15px;
  padding:14px 16px;
  box-shadow:0 7px 22px rgba(15,76,92,.07);
}
[data-testid="stMetricLabel"]{color:var(--med-muted)}
[data-testid="stMetricValue"]{color:var(--med-primary);font-weight:800}
.stButton>button,.stDownloadButton>button,[data-testid="stFormSubmitButton"]>button{
  border-radius:10px!important;
  min-height:2.55rem;
  font-weight:700!important;
  border:1px solid #bad1d8!important;
  transition:transform .12s ease,box-shadow .12s ease,background .12s ease;
}
.stButton>button:hover,.stDownloadButton>button:hover,[data-testid="stFormSubmitButton"]>button:hover{
  border-color:var(--med-primary-2)!important;
  color:var(--med-primary)!important;
  transform:translateY(-1px);
  box-shadow:0 6px 16px rgba(15,76,92,.13);
}
button[kind="primary"]{
  background:linear-gradient(135deg,var(--med-primary),var(--med-primary-2))!important;
  color:white!important;border:none!important;
  box-shadow:0 6px 16px rgba(15,76,92,.20);
}
button[kind="primary"]:hover{color:white!important;box-shadow:0 8px 20px rgba(15,76,92,.28)}
.stButton>button:disabled,.stDownloadButton>button:disabled,[data-testid="stFormSubmitButton"]>button:disabled{
  background:#e3ebee!important;color:#60747c!important;border-color:#cbd9de!important;
  opacity:1!important;box-shadow:none!important;transform:none!important;
}
[data-testid="stSidebar"] div[data-testid="stExpander"]{
  background:rgba(255,255,255,.07)!important;
  border:1px solid rgba(255,255,255,.22)!important;
  box-shadow:none!important;
}
[data-testid="stSidebar"] div[data-testid="stExpander"] summary,
[data-testid="stSidebar"] div[data-testid="stExpander"] summary *{color:#f4fbfc!important}
/* Los formularios dentro del menú lateral usan una tarjeta oscura. Los
   campos conservan fondo claro y texto oscuro para que siempre sean legibles. */
[data-testid="stSidebar"] [data-testid="stForm"]{
  background:rgba(255,255,255,.07)!important;
  border:1px solid rgba(255,255,255,.20)!important;
  box-shadow:none!important;
}
[data-testid="stSidebar"] [data-baseweb="input"] input,
[data-testid="stSidebar"] [data-baseweb="textarea"] textarea{
  color:#17313a!important;
  -webkit-text-fill-color:#17313a!important;
}
[data-testid="stSidebar"] [data-baseweb="input"] input::placeholder,
[data-testid="stSidebar"] [data-baseweb="textarea"] textarea::placeholder{
  color:#71878f!important;
  -webkit-text-fill-color:#71878f!important;
}
.stTabs [data-baseweb="tab-list"]{
  gap:.35rem;background:#e9f1f4;padding:.35rem;border-radius:12px;
}
.stTabs [data-baseweb="tab"]{
  height:2.7rem;border-radius:9px;padding:0 1rem;color:#45616b;font-weight:650;
}
.stTabs [aria-selected="true"]{
  background:white!important;color:var(--med-primary)!important;
  box-shadow:0 3px 10px rgba(15,76,92,.10);
}
.stTabs [data-baseweb="tab-highlight"]{display:none}
div[data-baseweb="input"]>div,div[data-baseweb="select"]>div,textarea{
  border-radius:10px!important;border-color:#cbdde3!important;background:#fbfdfe!important;
}
div[data-baseweb="input"]>div:focus-within,div[data-baseweb="select"]>div:focus-within,textarea:focus{
  border-color:var(--med-primary-2)!important;
  box-shadow:0 0 0 3px rgba(20,125,146,.12)!important;
}
[data-testid="stDataFrame"]{
  border:1px solid var(--med-border);border-radius:13px;overflow:hidden;
  box-shadow:0 5px 18px rgba(15,76,92,.05);
}
[data-testid="stAlert"]{border-radius:12px;border-width:1px}
.small-note{color:var(--med-muted);font-size:.88rem}
@media (max-width:768px){.block-container{padding-top:1rem}.stTabs [data-baseweb="tab"]{padding:0 .6rem}}
</style>""", unsafe_allow_html=True)

@st.cache_resource(show_spinner="Conectando con Supabase…")
def database():
    db=Database(); db.initialize(); return db

def fail(exc):
    if isinstance(exc, AppError): st.error(str(exc))
    elif isinstance(exc, (UniqueViolation,ExclusionViolation)): st.error("El dato ya existe o el horario se cruza con otro registro. Actualice y vuelva a intentar.")
    else:
        logging.exception("Error inesperado")
        st.error("Ocurrió un error inesperado. El detalle quedó registrado en la terminal.")

def run(action, success=None, rerun=True):
    try:
        result=action()
        if success:
            if rerun: st.session_state.flash_success=success
            else: st.success(success)
        if rerun: st.rerun()
        return result if result is not None else True
    except Exception as exc:
        fail(exc)
        return False

try: db=database()
except Exception as exc:
    fail(exc); st.stop()

def login_screen():
    st.title("🏥 Medisuport")
    st.caption("Sistema de gestión clínica")
    if not db.ready():
        st.info("Primera configuración: cree la cuenta administradora. Esta pantalla desaparece después del registro.")
        with st.form("bootstrap"):
            name=st.text_input("Nombre completo")
            username=st.text_input("Usuario")
            password=st.text_input("Contraseña nueva",type="password",help="Mínimo 12 caracteres")
            repeat=st.text_input("Repita la contraseña",type="password")
            if st.form_submit_button("Crear administrador",type="primary"):
                if password!=repeat: st.error("Las contraseñas no coinciden.")
                else: run(lambda: db.bootstrap(username,name,password),"Administrador creado. Ingrese con su cuenta.")
        return
    with st.form("login"):
        username=st.text_input("Usuario")
        password=st.text_input("Contraseña",type="password")
        if st.form_submit_button("Ingresar",type="primary"):
            user=run(lambda:db.login(username,password),rerun=False)
            if user:
                st.session_state.user=user; st.session_state.page="Inicio"; st.rerun()

if "user" not in st.session_state:
    login_screen(); st.stop()
try:
    user=db.session_user(st.session_state.user['id'],st.session_state.user['auth_version'])
    st.session_state.user.update(user)
except Exception as exc:
    st.session_state.pop('user',None); fail(exc); st.stop()
UID=user['id']; ROLE=user['role']; DOCTOR=user['doctor_id']
brand=db.branding(UID)
st.markdown(f"""<style>
:root{{--med-primary:{brand['primary']};--med-primary-2:{brand['secondary']};--med-accent:{brand['secondary']};--med-bg:{brand['background']};--med-surface:{brand['surface']};--med-text:{brand['text']};--med-muted:{brand['muted']};--med-border:{brand['border']};}}
[data-testid="stAppViewContainer"],.stApp{{background:{brand['background']}!important;color:{brand['text']}!important}}
[data-testid="stMainBlockContainer"],main{{color:{brand['text']}!important}}
h1,h2,h3,h4,h5,h6{{color:{brand['primary']}!important}}
p,label,.stMarkdown,.stCaption,[data-testid="stWidgetLabel"]{{color:{brand['text']}!important}}
.stCaption,[data-testid="stCaptionContainer"]{{color:{brand['muted']}!important}}
[data-testid="stSidebar"]{{background:linear-gradient(180deg,{brand['primary']} 0%,{brand['secondary']} 140%)!important}}
[data-testid="stSidebar"] *{{color:{brand['sidebar_text']}!important}}
[data-testid="stForm"],[data-testid="stMetric"],[data-testid="stExpander"],div[data-testid="stVerticalBlockBorderWrapper"]{{background:{brand['surface']}!important;border-color:{brand['border']}!important;color:{brand['text']}!important}}
div[data-baseweb="input"]>div,div[data-baseweb="select"]>div,div[data-baseweb="textarea"]>div,textarea,input{{background:{brand['input']}!important;color:{brand['text']}!important;border-color:{brand['border']}!important;-webkit-text-fill-color:{brand['text']}!important}}
[data-baseweb="popover"],[role="listbox"],[role="option"]{{background:{brand['surface']}!important;color:{brand['text']}!important}}
.stTabs [data-baseweb="tab-list"]{{background:{brand['border']}!important}}
.stTabs [aria-selected="true"]{{background:{brand['surface']}!important;color:{brand['primary']}!important}}
.stButton>button,.stDownloadButton>button{{background:{brand['surface']}!important;color:{brand['primary']}!important;border-color:{brand['border']}!important}}
button[kind="primary"]{{background:linear-gradient(135deg,{brand['primary']},{brand['secondary']})!important;color:#FFFFFF!important}}
[data-testid="stDataFrame"],iframe{{border-color:{brand['border']}!important;background:{brand['surface']}!important}}
</style>""",unsafe_allow_html=True)

if user['must_change']:
    st.title("Cambie su contraseña temporal")
    with st.form("forced_password"):
        current=st.text_input("Contraseña temporal",type="password")
        new=st.text_input("Contraseña nueva",type="password")
        repeat=st.text_input("Repita la contraseña",type="password")
        if st.form_submit_button("Cambiar contraseña",type="primary"):
            if new!=repeat: st.error("Las contraseñas no coinciden.")
            else:
                ok=run(lambda:db.change_password(UID,current,new),"Contraseña actualizada. Ingrese nuevamente.",False)
                if ok:
                    st.session_state.pop('user',None); st.rerun()
    st.stop()

pages={
 'admin':['Inicio','Pacientes','Convenios','Agenda','Mis citas','Facturación y caja','Historia clínica','Certificados médicos','Médicos y horarios','Usuarios','Reportes y respaldo','Administración'],
 'secretaria':['Inicio','Pacientes','Convenios','Agenda','Facturación y caja','Médicos y horarios','Reportes'],
 'medico':['Inicio','Mis citas','Historia clínica','Certificados médicos','Mi información profesional','Pacientes']
}[ROLE]
# Los cambios de página solicitados por una acción se aplican al comienzo del
# siguiente ciclo, antes de crear el widget de navegación.
if 'next_page' in st.session_state:
    st.session_state.page=st.session_state.pop('next_page')
try:
    if brand.get('logo'): st.sidebar.image(base64.b64decode(brand['logo']),width=125)
    elif (Path(__file__).parent/'assets/clinic_logo.png').exists(): st.sidebar.image(str(Path(__file__).parent/'assets/clinic_logo.png'),width=125)
except Exception: pass
st.sidebar.title(brand['name'])
st.sidebar.caption("Gestión clínica segura")
st.sidebar.write(f"**{user['name']}**")
st.sidebar.caption({'admin':'Administrador','secretaria':'Secretaría','medico':'Médico'}[ROLE])
page=st.sidebar.radio("Menú",pages,key="page")
if st.sidebar.button("Cerrar sesión"):
    st.session_state.clear(); st.rerun()
with st.sidebar.expander("Cambiar mi contraseña"):
    with st.form("own_password"):
        old=st.text_input("Actual",type="password")
        new=st.text_input("Nueva",type="password")
        if st.form_submit_button("Actualizar"):
            changed=run(lambda:db.change_password(UID,old,new),"Contraseña actualizada; ingrese nuevamente.",False)
            if changed:
                st.session_state.clear(); st.rerun()
if ROLE=='medico':
    profile=next((d for d in db.doctors(UID,all_rows=True) if d['id']==DOCTOR),None)
    with st.sidebar.expander("Mi información profesional"):
        with st.form("my_professional_profile"):
            professional_id=st.text_input("Documento",value=(profile or {}).get('professional_id') or '')
            registration=st.text_input("Número de registro profesional",value=(profile or {}).get('registration') or '')
            if st.form_submit_button("Guardar mis datos"):
                run(lambda:db.update_my_professional(UID,professional_id,registration),"Información profesional actualizada.")
if st.session_state.get('flash_success'):
    message=st.session_state.pop('flash_success'); st.success(f"✅ {message}"); st.toast(message,icon='✅')

def professional_profile_page():
    st.title("Mi información profesional")
    st.caption("Estos datos aparecerán en certificados médicos, historias clínicas y documentos descargables.")
    profile=db.my_professional(UID)
    st.info(f"Profesional: {proper_name(profile['name'])} · Especialidades: {', '.join(profile['specialties'])}")
    with st.form("professional_profile_main"):
        professional_id=st.text_input("Documento de identificación *",value=profile.get('professional_id') or '',placeholder="Ej.: 1712345678")
        registration=st.text_input("Número de registro profesional *",value=profile.get('registration') or '',placeholder="Ej.: MSP-12345")
        if st.form_submit_button("Guardar información profesional",type="primary"):
            run(lambda:db.update_my_professional(UID,professional_id,registration),"Información profesional guardada correctamente.")

def doctors(active=True): return db.doctors(UID,all_rows=not active)
def doctor_map(active=True): return {proper_name(d['name']):d for d in doctors(active)}
def patient_picker(key,active=True):
    query=st.text_input("Buscar por nombre, documento o teléfono",key=key+"_q")
    rows=db.patients(UID,query,archived=not active)
    if not rows: st.info("No hay pacientes que coincidan."); return None
    labels={f"{proper_name(p['name'])} · {p['document']}":p for p in rows}
    return labels[st.selectbox("Paciente",labels,key=key+"_p")]
def fmt_dt(v): return v.astimezone(TZ).strftime('%d/%m/%Y %H:%M') if v else ''
def appointment_table(rows):
    return pd.DataFrame([{'Hora':fmt_dt(r['start_at']),'Paciente':proper_name(r['patient']),'Documento':r['document'],'Teléfono':r['phone'],'Convenio':r.get('agreement') or 'Particular','Médico':proper_name(r['doctor']),'Especialidad':r['specialty'],'Estado':r['status']} for r in rows])

def dashboard():
    st.title("Agenda de hoy")
    rows=db.appointments(UID,now().date(),now().date())
    total=len(rows); attended=sum(r['status']=='Atendida' for r in rows); waiting=sum(r['status'] in ('Llegó','En atención') for r in rows)
    c1,c2,c3=st.columns(3); c1.metric("Citas",total); c2.metric("Esperando / en atención",waiting); c3.metric("Atendidas",attended)
    if rows: st.dataframe(appointment_table(rows),hide_index=True,use_container_width=True)
    else: st.info("No hay citas para hoy.")
    if ROLE=='medico':
        st.caption("Para abrir una consulta, la recepción debe marcar primero que el paciente llegó.")

def patient_form(existing=None):
    e=dict(existing or {})
    if not (e.get('apellido1') and e.get('nombre1')) and e.get('name'):
        parts=proper_name(e['name']).split()
        e['apellido1']=e.get('apellido1') or (parts[0] if parts else '')
        e['apellido2']=e.get('apellido2') or (parts[1] if len(parts)>=4 else '')
        e['nombre1']=e.get('nombre1') or (parts[2] if len(parts)>=3 else (parts[1] if len(parts)==2 else ''))
        e['nombre2']=e.get('nombre2') or (' '.join(parts[3:]) if len(parts)>=4 else '')
    # La pestaña "Buscar y editar" y la pestaña "Registrar" se renderizan
    # al mismo tiempo. Cada formulario necesita una clave distinta.
    form_key=f"patient_form_{e.get('id', 'new')}"
    with st.form(form_key):
        a,b=st.columns(2)
        with a:
            document=st.text_input("Documento *",value=e.get('document',''),disabled=bool(existing))
            st.caption("Nombres separados para que el formato ISSFA no tenga que adivinarlos.")
            apellido1=st.text_input("Primer apellido *",value=e.get('apellido1') or '')
            apellido2=st.text_input("Segundo apellido",value=e.get('apellido2') or '')
            nombre1=st.text_input("Primer nombre *",value=e.get('nombre1') or '')
            nombre2=st.text_input("Segundo nombre",value=e.get('nombre2') or '')
            sex=st.selectbox("Sexo",['','Femenino','Masculino','Otro'],index=['','Femenino','Masculino','Otro'].index(e.get('sex') or '') if (e.get('sex') or '') in ['','Femenino','Masculino','Otro'] else 0)
            birth=st.date_input("Fecha de nacimiento",value=e.get('birth_date'),min_value=date(1900,1,1),
                                max_value=now().date(),format='DD/MM/YYYY',key=f"birth_{e.get('id', 'new')}",
                                help="Puede escribirla (DD/MM/AAAA) o elegirla en el calendario. Déjela vacía si no se conoce.")
            phone=st.text_input("Teléfono",value=e.get('phone') or '')
        with b:
            email=st.text_input("Correo",value=e.get('email') or '')
            address=st.text_input("Dirección",value=e.get('address') or '')
            occupation=st.text_input("Ocupación",value=e.get('occupation') or '')
            coverages=['Particular']+[a['name'] for a in db.agreements(UID,True)]
            coverage=st.selectbox("Cobertura",coverages,index=coverages.index(e.get('coverage')) if e.get('coverage') in coverages else 0)
            origins=['Propio de la Clínica','Convenio institucional']
            origin=st.selectbox("Origen",origins,index=origins.index(e.get('origin')) if e.get('origin') in origins else 0)
        if st.form_submit_button("Guardar ficha",type="primary"):
            data={'document':document,'apellido1':apellido1,'apellido2':apellido2,'nombre1':nombre1,'nombre2':nombre2,
                  'name':' '.join(x for x in (apellido1,apellido2,nombre1,nombre2) if x),'sex':sex,'birth_date':birth,'phone':phone,'email':email,
                  'address':address,'occupation':occupation,'coverage':coverage,'origin':origin}
            run(lambda:db.save_patient(UID,data,e.get('id'),e.get('version')),"Ficha guardada.")

def patients_page():
    st.title("Pacientes")
    if ROLE in ('admin','secretaria'):
        tab1,tab2,tab3=st.tabs(['Buscar y editar','Registrar','Archivados'])
    else: tab1,tab2,tab3=st.container(),None,None
    with tab1:
        p=patient_picker('patient_edit')
        if p:
            st.caption(f"Registro actualizado: {p['updated_at'].astimezone(TZ).strftime('%d/%m/%Y %H:%M')}")
            if ROLE in ('admin','secretaria'):
                patient_form(p)
                with st.expander("Archivar paciente"):
                    reason=st.text_area("Motivo",key='archive_reason')
                    if st.button("Archivar",type="primary"): run(lambda:db.archive_patient(UID,p['id'],reason),"Paciente archivado.")
                if ROLE=='admin':
                    with st.expander("Eliminar paciente definitivamente"):
                        st.error("Se eliminarán también sus citas, historias clínicas y certificados.")
                        if st.button("Eliminar paciente",key=f"delete_active_patient_{p['id']}"):
                            run(lambda:db.delete_patient(UID,p['id']),"Paciente eliminado definitivamente.")
            else:
                st.write({k:p.get(k) for k in ['document','name','sex','birth_date','phone','email','address','occupation','coverage','origin']})
    if tab2:
        with tab2: patient_form()
    if tab3:
        with tab3:
            q=st.text_input("Buscar archivados")
            archived=[p for p in db.patients(UID,q,archived=True) if not p['active']]
            if archived:
                labels={f"{proper_name(p['name'])} · {p['document']}":p for p in archived}; p=labels[st.selectbox("Archivado",labels)]
                st.warning(f"Motivo: {p['archive_reason'] or 'No registrado'}")
                reason=st.text_input("Motivo de reactivación")
                if st.button("Reactivar"): run(lambda:db.archive_patient(UID,p['id'],reason,True),"Paciente reactivado.")
                if ROLE=='admin':
                    with st.expander("Eliminar paciente definitivamente"):
                        st.error("Se eliminarán también sus citas, historias clínicas y certificados.")
                        if st.button("Eliminar definitivamente",key=f"delete_patient_{p['id']}"):
                            run(lambda:db.delete_patient(UID,p['id']),"Paciente eliminado definitivamente.")
            else: st.info("No hay pacientes archivados.")

IMPORT_COLUMNS={'cedula','nombres_completos','sexo','fecha_nacimiento','telefono','correo','direccion','ocupacion','numero_afiliado'}
IMPORT_ALIASES={
    'cedula':['cedula','cédula','documento','identificacion','identificación','dni','documento_identidad','numero_documento'],
    'nombres_completos':['nombres_completos','nombre_completo','paciente','apellidos_nombres','nombres_y_apellidos','nombre_y_apellido','apellidos_y_nombres','apellidos_nombres'],
    'apellidos':['apellidos','apellido','apellidos_completos'],
    'nombres':['nombres','nombre','nombres_completos'],
    'apellido1':['apellido1','primer_apellido','apellido_paterno','apellido_paterno_1'],
    'apellido2':['apellido2','segundo_apellido','apellido_materno','apellido_materno_2'],
    'nombre1':['nombre1','primer_nombre'],
    'nombre2':['nombre2','segundo_nombre'],
    'sexo':['sexo','genero','género'],
    'fecha_nacimiento':['fecha_nacimiento','fecha_de_nacimiento','nacimiento','fecha_nac','fec_nacimiento'],
    'telefono':['telefono','teléfono','celular','movil','móvil','telefono_celular'],
    'correo':['correo','email','e_mail','correo_electronico','correo_electrónico'],
    'direccion':['direccion','dirección','domicilio'],
    'ocupacion':['ocupacion','ocupación','profesion','profesión'],
    'numero_afiliado':['numero_afiliado','número_afiliado','afiliado','numero_afiliacion','número_afiliación','codigo_afiliado','codigo_afiliacion']
}
def normalized_header(value):
    text=unicodedata.normalize('NFKD',str(value or '')).encode('ascii','ignore').decode().lower().strip()
    return re.sub(r'[^a-z0-9]+','_',text).strip('_')
def _find_import_sheet(uploaded):
    try:
        book=pd.ExcelFile(uploaded)
    except Exception as exc:
        raise AppError(f'No se pudo abrir el archivo Excel: {exc}')
    names=book.sheet_names
    if 'Pacientes' in names: return 'Pacientes', book, 0
    candidates=[]
    for sheet in names:
        try:
            sample=pd.read_excel(book,sheet_name=sheet,header=None,nrows=15,dtype=str)
        except Exception:
            continue
        for header_row,values in sample.iterrows():
            headers={normalized_header(c) for c in values.tolist() if str(c).strip() and str(c).lower()!='nan'}
            has_doc=bool(headers & {normalized_header(x) for x in IMPORT_ALIASES['cedula']})
            has_name=bool(headers & ({normalized_header(x) for x in IMPORT_ALIASES['nombres_completos']}|{normalized_header(x) for x in IMPORT_ALIASES['apellidos']}|{normalized_header(x) for x in IMPORT_ALIASES['apellido1']}))
            if has_doc and has_name:
                candidates.append((sheet,int(header_row))); break
    if len(candidates)==1: return candidates[0][0], book, candidates[0][1]
    if len(candidates)>1:
        # Preferir una hoja cuyo nombre sugiera afiliados/pacientes/beneficiarios.
        preferred=[x for x in candidates if any(k in normalized_header(x[0]) for k in ('paciente','afiliado','beneficiario','usuario','nomina','nomina'))]
        return (preferred or candidates)[0][0], book, (preferred or candidates)[0][1]
    raise AppError('No encontré una hoja de pacientes. Hojas disponibles: '+', '.join(names)+'. Descargue la plantilla oficial o use una hoja que contenga documento/cédula y nombres.')

def _resolve_columns(columns):
    normalized={normalized_header(c):c for c in columns}
    resolved={}
    for target,aliases in IMPORT_ALIASES.items():
        for alias in aliases:
            key=normalized_header(alias)
            if key in normalized:
                resolved[target]=normalized[key]; break
    if 'nombres_completos' not in resolved and not ('apellidos' in resolved and 'nombres' in resolved) and not ('apellido1' in resolved and 'nombre1' in resolved):
        raise AppError('No pude identificar los nombres. Se necesita nombres completos, apellidos + nombres, o primer apellido + primer nombre.')
    if 'cedula' not in resolved:
        raise AppError('No pude identificar la cédula/documento del archivo.')
    return resolved

def patient_import_preview(uploaded,agreement_name):
    sheet,book,header_row=_find_import_sheet(uploaded)
    frame=pd.read_excel(book,sheet_name=sheet,header=header_row,dtype=str)
    resolved=_resolve_columns(frame.columns)
    frame=frame.fillna('')
    rows=[]; seen=set()
    sex_map={'f':'Femenino','femenino':'Femenino','mujer':'Femenino','m':'Masculino','masculino':'Masculino','hombre':'Masculino','otro':'Otro'}
    def val(source,key): return str(source[resolved[key]]).strip() if key in resolved else ''
    for _,source in frame.iterrows():
        if not any(str(x).strip() for x in source): continue
        raw_date=val(source,'fecha_nacimiento'); birth=None
        if raw_date:
            parsed=pd.to_datetime(raw_date,dayfirst=True,errors='coerce')
            birth=None if pd.isna(parsed) else parsed.date()
        document=re.sub(r'\.0$','',val(source,'cedula'))
        if 'apellidos' in resolved and 'nombres' in resolved and 'nombres_completos' not in resolved:
            ap=proper_name(val(source,'apellidos')).split()
            no=proper_name(val(source,'nombres')).split()
            apellido1=val(source,'apellido1') or (ap[0] if ap else '')
            apellido2=val(source,'apellido2') or (' '.join(ap[1:]) if len(ap)>1 else '')
            nombre1=val(source,'nombre1') or (no[0] if no else '')
            nombre2=val(source,'nombre2') or (' '.join(no[1:]) if len(no)>1 else '')
            full_name=' '.join(x for x in (apellido1,apellido2,nombre1,nombre2) if x)
        elif 'nombres_completos' in resolved:
            full_name=val(source,'nombres_completos')
            parts=proper_name(full_name).split()
            apellido1=val(source,'apellido1') or (parts[0] if parts else '')
            apellido2=val(source,'apellido2') or (parts[1] if len(parts)>=4 else '')
            nombre1=val(source,'nombre1') or (parts[2] if len(parts)>=3 else (parts[1] if len(parts)==2 else ''))
            nombre2=val(source,'nombre2') or (' '.join(parts[3:]) if len(parts)>=4 else '')
        else:
            apellido1,apellido2,nombre1,nombre2=[val(source,k) for k in ('apellido1','apellido2','nombre1','nombre2')]
            full_name=' '.join(x for x in (apellido1,apellido2,nombre1,nombre2) if x)
        row={'document':document,'name':full_name,'apellido1':apellido1,'apellido2':apellido2,'nombre1':nombre1,'nombre2':nombre2,
             'sex':sex_map.get(normalized_header(val(source,'sexo')),val(source,'sexo')),
             'birth_date':birth,'phone':re.sub(r'\.0$','',val(source,'telefono')),'email':val(source,'correo'),'address':val(source,'direccion'),
             'occupation':val(source,'ocupacion'),'coverage':agreement_name,'origin':'Convenio institucional','member_number':re.sub(r'\.0$','',val(source,'numero_afiliado'))}
        try:
            from core import validate_patient
            validate_patient(row)
            if document in seen: raise AppError('Documento repetido dentro del archivo.')
            seen.add(document); status='Listo'
        except Exception as exc: status=str(exc)
        rows.append((row,status))
    return rows,sheet

def agreements_page():
    st.title("Convenios e importación")
    st.caption("Registre cualquier institución y cargue sus pacientes con la plantilla oficial de Excel.")
    rows=db.agreements(UID)
    if rows:
        st.dataframe(pd.DataFrame([{'Convenio':proper_name(a['name']),'Código':a['code'] or '', 'Pacientes activos':a['patient_count'],
                                   'Exige fecha de validación':'Sí' if a['requires_validation_date'] else 'No','Vigente':'Sí' if a['active'] else 'No'} for a in rows]),hide_index=True,use_container_width=True)
    if ROLE=='admin':
        agreement_query=st.text_input("Buscar convenio",key='agreement_query')
        filtered=[a for a in rows if agreement_query.lower() in a['name'].lower()]
        labels={'Nuevo convenio':None}|{proper_name(a['name']):a for a in filtered}; selected=labels[st.selectbox("Crear o editar",labels,key='agreement_edit')]
        with st.form('agreement_form'):
            a,b=st.columns(2)
            with a:
                name=st.text_input("Nombre del convenio *",value=selected['name'] if selected else '')
                code=st.text_input("Código interno",value=selected['code'] or '' if selected else '')
                tax_id=st.text_input("RUC / identificación",value=selected['tax_id'] or '' if selected else '')
                contact=st.text_input("Persona de contacto",value=selected['contact_name'] or '' if selected else '')
            with b:
                phone=st.text_input("Teléfono",value=selected['phone'] or '' if selected else '')
                email=st.text_input("Correo",value=selected['email'] or '' if selected else '')
                requires=st.checkbox("Exige fecha de validación para cada cita",value=selected['requires_validation_date'] if selected else False)
                active=st.checkbox("Convenio activo",value=selected['active'] if selected else True)
            notes=st.text_area("Observaciones",value=selected['notes'] or '' if selected else '')
            if st.form_submit_button("Guardar convenio",type='primary'):
                data={'name':name,'code':code,'tax_id':tax_id,'contact_name':contact,'phone':phone,'email':email,'notes':notes,
                      'requires_validation_date':requires,'active':active,'start_date':selected.get('start_date') if selected else None,'end_date':selected.get('end_date') if selected else None}
                run(lambda:db.save_agreement(UID,data,selected['id'] if selected else None,selected['version'] if selected else None),"Convenio guardado.")
        if selected:
            confirm_agreement=st.checkbox("Confirmo que deseo eliminar o archivar este convenio",key='confirm_delete_agreement')
            if st.button("Eliminar convenio",disabled=not confirm_agreement): run(lambda:db.delete_agreement(UID,selected['id']),"Convenio retirado.")
    active=[a for a in rows if a['active']]
    st.subheader("Importar pacientes")
    template=Path(__file__).parent/'plantilla_importacion_pacientes.xlsx'
    if template.exists(): st.download_button("Descargar plantilla oficial",template.read_bytes(),template.name,"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    if not active: st.info("Primero registre y active un convenio."); return
    choices={proper_name(a['name']):a for a in active}; chosen=choices[st.selectbox("Convenio de destino",choices,key='agreement_import')]
    uploaded=st.file_uploader("Archivo Excel completado",type=['xlsx'],key='patient_xlsx')
    if uploaded:
        try:
            prepared,sheet_used=patient_import_preview(uploaded,chosen['name'])
            st.caption(f'Hoja utilizada: {sheet_used}')
            preview=[{'Documento':r['document'],'Paciente':proper_name(r['name']),'Número afiliado':r['member_number'],'Estado':status} for r,status in prepared]
            st.dataframe(pd.DataFrame(preview),hide_index=True,use_container_width=True)
            valid=[r for r,status in prepared if status=='Listo']; errors=len(prepared)-len(valid)
            st.caption(f"{len(valid)} fila(s) lista(s) · {errors} fila(s) con observaciones")
            if st.button("Confirmar importación",type='primary',disabled=errors>0 or not valid):
                result=run(lambda:db.import_patients(UID,chosen['id'],valid),rerun=False)
                if result:
                    st.session_state.import_result=excel({'Resultado':result}); st.success(f"Importación terminada: {len(result)} pacientes procesados.")
            if st.session_state.get('import_result'):
                st.download_button("Descargar resultado",st.session_state.import_result,"Resultado_importacion.xlsx","application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        except Exception as exc: fail(exc)

def agenda_page(doctor_only=False):
    st.title("Mis citas" if doctor_only else "Agenda")
    start,end=st.date_input("Periodo",value=(now().date(),now().date()+timedelta(days=7)),format='DD/MM/YYYY')
    status=st.selectbox("Estado",['Todos']+STATUSES)
    rows=db.appointments(UID,start,end,None if status=='Todos' else status)
    if rows: st.dataframe(appointment_table(rows),hide_index=True,use_container_width=True)
    else: st.info("No hay citas en el periodo.")
    if doctor_only:
        actionable=[r for r in rows if r['status'] in ('Llegó','En atención')]
        if actionable:
            labels={f"{fmt_dt(r['start_at'])} · {r['patient']} · {r['status']}":r for r in actionable}; ap=labels[st.selectbox("Abrir consulta",labels)]
            if st.button("Continuar atención",type="primary"):
                eid=run(lambda:db.start_encounter(UID,ap['id']),rerun=False)
                if eid:
                    st.session_state.encounter_id=eid
                    st.session_state.next_page='Historia clínica'
                    st.rerun()
        return
    if ROLE not in ('admin','secretaria'): return
    t1,t2=st.tabs(['Nueva cita','Gestionar cita'])
    with t1: booking_form()
    with t2:
        if not rows: return
        labels={f"{fmt_dt(r['start_at'])} · {r['patient']} · {r['doctor']} · {r['status']}":r for r in rows}; ap=labels[st.selectbox("Seleccione",labels,key='manage_ap')]
        st.write(f"**Notas:** {ap['notes'] or '—'}  ")
        allowed=[s for s in STATUSES if s!=ap['status']]
        new_status=st.selectbox("Nuevo estado",allowed)
        reason=st.text_input("Motivo (obligatorio al cancelar o marcar ausencia)")
        if st.button("Cambiar estado"): run(lambda:db.change_status(UID,ap['id'],new_status,reason,ap['version']),"Estado actualizado.")
        if ap['status'] in ('Pendiente','Confirmada','Llegó'):
            with st.expander("Reagendar"):
                booking_form(ap)

def booking_form(existing=None):
    p=patient_picker('book'+str(existing['id'] if existing else 'new')) if not existing else db.get_patient(UID,existing['patient_id'])
    dm=doctor_map();
    if not p or not dm: return
    default=next((name for name,d in dm.items() if existing and d['id']==existing['doctor_id']),next(iter(dm)))
    dname=st.selectbox("Médico",list(dm),index=list(dm).index(default),key='bd'+str(existing and existing['id'])); d=dm[dname]
    specialty=st.selectbox("Especialidad",d['specialties'],index=d['specialties'].index(existing['specialty']) if existing and existing['specialty'] in d['specialties'] else 0,key='bs'+str(existing and existing['id']))
    duration=st.selectbox("Duración",[15,20,30,45,60,90,120],index=[15,20,30,45,60,90,120].index(int((existing['end_at']-existing['start_at']).total_seconds()/60)) if existing and int((existing['end_at']-existing['start_at']).total_seconds()/60) in [15,20,30,45,60,90,120] else 2,key='bu'+str(existing and existing['id']))
    day=st.date_input("Fecha",value=existing['start_at'].astimezone(TZ).date() if existing else now().date()+timedelta(days=1),min_value=now().date(),format='DD/MM/YYYY',key='bf'+str(existing and existing['id']))
    slots=db.available_slots(UID,d['id'],p['id'],day,duration,existing['id'] if existing else None)
    if not slots: st.warning("No hay turnos libres para esa fecha y duración."); return
    labels={x.strftime('%H:%M'):x for x in slots}; selected=st.selectbox("Hora disponible",labels,key='bt'+str(existing and existing['id']))
    # La recepción puede seleccionar cualquier convenio activo. Al guardar la
    # cita, el backend vincula automáticamente al paciente con ese convenio.
    available_agreements=db.agreements(UID,active_only=True)
    options={'Particular':None}|{a['name']:a for a in available_agreements}
    patient_default=next((name for name,a in options.items() if a and str(p.get('coverage') or '').lower()==name.lower()),'Particular')
    current=next((name for name,a in options.items() if a and existing and a['id']==existing.get('agreement_id')),patient_default)
    agreement_name=st.selectbox("Facturación / convenio",list(options),index=list(options).index(current),key='bc'+str(existing and existing['id']))
    agreement=options[agreement_name]; needs_validation=bool(agreement and agreement['requires_validation_date'])
    validation_date=st.date_input("Fecha de validación del convenio",value=existing.get('validation_date') if existing and existing.get('validation_date') else None,disabled=not agreement,format='DD/MM/YYYY',key='bv'+str(existing and existing['id']))
    if needs_validation: st.caption("Este convenio exige registrar la fecha en que se validó la atención.")
    notes=st.text_area("Observaciones",value=(existing.get('notes') or '') if existing else '',key='bn'+str(existing and existing['id']))
    if st.button("Guardar reagendamiento" if existing else "Agendar",type="primary",key='save_book'+str(existing and existing['id'])):
        run(lambda:db.book(UID,p['id'],d['id'],specialty,labels[selected],duration,agreement['id'] if agreement else None,validation_date if agreement else None,notes,existing['id'] if existing else None,existing['version'] if existing else None),"Cita guardada.")

CONDITIONS=['Cardiopatía','Hipertensión','Enfermedad cerebrovascular','Endócrino-metabólica','Cáncer','Tuberculosis','Enfermedad mental','Enfermedad infecciosa','Malformación','Otra']
SYSTEMS=['Piel y anexos','Órganos de los sentidos','Respiratorio','Cardiovascular','Digestivo','Genitourinario','Músculo-esquelético','Endócrino','Hemolinfático','Nervioso']
REGIONAL=['Piel y faneras','Cabeza','Ojos','Oídos','Nariz','Boca','Orofaringe','Cuello','Axilas y mamas','Tórax','Abdomen','Columna vertebral','Ingle y periné','Miembros superiores','Miembros inferiores']
SYSTEMIC=['Órganos de los sentidos','Respiratorio','Cardiovascular','Digestivo','Genital','Urinario','Músculo-esquelético','Endócrino','Hemolinfático','Neurológico']
LAB_TESTS=['Biometría hemática','Hematocrito','Hemoglobina','Plaquetas','Reticulocitos','VSG','Hierro sérico','Ferritina','TP','TTP','INR','Fibrinógeno',
 'Glucosa basal','Glucosa posprandial','Glucosa al azar','Urea','Creatinina','Ácido úrico','Fosfatasa alcalina','AST/TGO','ALT/TGP','GGT','Bilirrubina total',
 'Colesterol total','HDL','LDL','VLDL','Triglicéridos','Proteínas totales','Albúmina','HbA1c','PCR cuantitativo','Amilasa','Lipasa',
 'EMO','Albuminuria','Coprológico/coproparasitario','Sangre oculta','Helicobacter pylori','TSH','T3','T4','FT3','FT4','Insulina','PTH','FSH','LH',
 '25-hidroxivitamina D','Cortisol','Testosterona total','Testosterona libre','Prolactina','Electrolitos','Gasometría arterial','Gasometría venosa',
 'VIH 1+2','Hepatitis A','Hepatitis B','Hepatitis C','VDRL','ANA','ANCA','Anti-DNA','Factor reumatoideo','Troponina I','Troponina T','CK-MB',
 'Grupo y factor','Coombs directo','Coombs indirecto','Cultivo y antibiograma','Estudio micológico','Marcadores tumorales']
def clinical_form(enc):
    data=enc['data'] or {}
    previous=enc.get('previous_data') or {}
    existing_extras=[]
    if data.get('prescription'): existing_extras.append('Receta')
    if data.get('lab_tests') or data.get('other_lab_tests'): existing_extras.append('Laboratorio')
    if data.get('imaging_types'): existing_extras.append('Imagenología')
    if data.get('interconsult_specialty'): existing_extras.append('Interconsulta')
    if data.get('referral_type'): existing_extras.append('Referencia / derivación')
    extras=st.multiselect("Documentos adicionales",['Receta','Laboratorio','Imagenología','Interconsulta','Referencia / derivación'],default=existing_extras,key='clinical_extras')
    normal_exam=st.checkbox("Examen físico sin hallazgos relevantes",value=data.get('physical_details')=='Sin hallazgos patológicos relevantes.',key='normal_exam')
    def prior(key,default=''): return data.get(key,previous.get(key,default))
    if previous and not data: st.caption("Se recuperaron antecedentes, alergias y hábitos de la consulta anterior para que el médico los confirme.")
    with st.form('clinical_form'):
        st.subheader(f"Consulta {enc['consultation_type']}")
        t1,t2,t3=st.tabs(['1. Motivo y antecedentes','2. Examen y diagnóstico','3. Indicaciones']); t4=t5=t3
        with t1:
            motivo=st.text_area("Motivo de consulta *",value=data.get('motivo',''))
            personal_conditions=st.multiselect("Antecedentes patológicos personales",CONDITIONS,default=prior('personal_conditions',[]))
            personal_details=st.text_area("Datos clínicos, quirúrgicos, obstétricos y alérgicos relevantes",value=prior('personal_details'))
            family_conditions=st.multiselect("Antecedentes patológicos familiares",CONDITIONS,default=prior('family_conditions',[]))
            family_details=st.text_area("Descripción de antecedentes familiares",value=prior('family_details'))
            a,b=st.columns(2); habitos=a.text_area("Hábitos de vida",value=prior('habitos')); alergias=b.text_area("Alergias",value=prior('alergias'))
            enfermedad_actual=st.text_area("Enfermedad o problema actual: cronología, localización, características, intensidad, frecuencia y agravantes",value=data.get('enfermedad_actual',''))
        with t2:
            c=st.columns(5)
            temperatura=c[0].number_input("Temperatura °C",0.0,50.0,float(data.get('temperatura') or 0),step=.1)
            pa=c[1].text_input("Presión arterial mmHg",value=data.get('pa','')); fc=c[2].number_input("Pulso/min",0,350,int(data.get('fc') or 0)); fr=c[3].number_input("Respiraciones/min",0,100,int(data.get('fr') or 0)); spo2=c[4].number_input("SpO₂ %",0,100,int(data.get('spo2') or 0))
            c=st.columns(5)
            peso=c[0].number_input("Peso kg",0.0,500.0,float(data.get('peso') or 0),step=.1); talla=c[1].number_input("Talla cm",0.0,280.0,float(data.get('talla') or 0),step=.1)
            imc=round(peso/(talla/100)**2,2) if peso and talla else None; c[2].metric("IMC kg/m²",imc or '—')
            perimetro=c[3].number_input("Perímetro abdominal cm",0.0,300.0,float(data.get('perimetro_abdominal') or 0),step=.1); glucosa=c[4].number_input("Glucosa capilar mg/dL",0.0,1000.0,float(data.get('glucosa_capilar') or 0),step=.1)
            hemoglobina=st.number_input("Hemoglobina capilar g/dL",0.0,30.0,float(data.get('hemoglobina_capilar') or 0),step=.1)
            systems_review=st.multiselect("Revisión de órganos y sistemas con patología",SYSTEMS,default=[] if normal_exam else data.get('systems_review',[])); systems_details=st.text_area("Descripción de la revisión por sistemas",value='Sin hallazgos patológicos relevantes.' if normal_exam else data.get('systems_details',''))
            physical_regional=st.multiselect("Examen físico regional con hallazgos",REGIONAL,default=[] if normal_exam else data.get('physical_regional',[])); physical_systemic=st.multiselect("Examen físico sistémico con hallazgos",SYSTEMIC,default=[] if normal_exam else data.get('physical_systemic',[])); physical_details=st.text_area("Descripción de hallazgos del examen físico",value='Sin hallazgos patológicos relevantes.' if normal_exam else data.get('physical_details',''))
        with t3:
            diagnostico=st.text_area("Diagnóstico principal *",value=data.get('diagnostico',''))
            diagnoses_text=st.text_area("Diagnósticos codificados: una línea por diagnóstico en formato CIE10 | Presuntivo/Definitivo | Descripción",value='\n'.join(data.get('diagnoses',[])))
            tratamiento=st.text_area("Plan diagnóstico, terapéutico y educacional",value=data.get('tratamiento','')); examenes=st.text_area("Resultados de exámenes y procedimientos relevantes",value=data.get('examenes',''))
        with t4:
          if 'Interconsulta' in extras:
            interconsult_specialty=st.text_input("Especialidad para interconsulta",value=data.get('interconsult_specialty','')); interconsult_reason=st.text_area("Motivo de interconsulta",value=data.get('interconsult_reason','')); clinical_summary=st.text_area("Resumen del cuadro clínico",value=data.get('clinical_summary','')); exam_results=st.text_area("Hallazgos relevantes",value=data.get('exam_results','')); therapeutic_plan=st.text_area("Plan terapéutico realizado",value=data.get('therapeutic_plan',''))
          if 'Referencia / derivación' in extras:
            referral_type=st.selectbox("Tipo de referencia",['','Referencia','Derivación','Contrarreferencia','Referencia inversa'],index=['','Referencia','Derivación','Contrarreferencia','Referencia inversa'].index(data.get('referral_type','')) if data.get('referral_type','') in ['','Referencia','Derivación','Contrarreferencia','Referencia inversa'] else 0)
            referral_reasons=st.multiselect("Motivos",['Accesibilidad geográfica','Falta de espacio físico','Falta de equipamiento','Equipos en mal estado','Problemas de infraestructura','Problemas de abastecimiento','Insuficiencia de profesionales','Inadecuada capacidad resolutiva','Ausencia de prestación'],default=data.get('referral_reasons',[]))
            referral_destination=st.text_input("Institución / establecimiento de destino",value=data.get('referral_destination','')); referral_service=st.text_input("Servicio de destino",value=data.get('referral_service','')); referral_specialty=st.text_input("Especialidad de destino",value=data.get('referral_specialty','')); referral_summary=st.text_area("Resumen para referencia",value=data.get('referral_summary','')); referral_findings=st.text_area("Hallazgos para referencia",value=data.get('referral_findings',''))
          if 'Laboratorio' in extras:
            lab_tests=st.multiselect("Exámenes de laboratorio solicitados",LAB_TESTS,default=data.get('lab_tests',[])); other_lab_tests=st.text_area("Otros exámenes / muestra / sitio anatómico",value=data.get('other_lab_tests','')); lab_treatment=st.text_area("Tratamiento terapéutico relacionado con la solicitud",value=data.get('lab_treatment',''))
          if 'Imagenología' in extras:
            imaging_types=st.multiselect("Imagenología solicitada",['RX convencional','RX portátil','Tomografía','Resonancia','Ecografía','Mamografía','Procedimiento','Otro'],default=data.get('imaging_types',[])); imaging_description=st.text_area("Descripción del estudio",value=data.get('imaging_description','')); imaging_reason=st.text_area("Motivo de imagenología",value=data.get('imaging_reason','')); fum=st.date_input("FUM (si corresponde)",value=date.fromisoformat(data['fum']) if isinstance(data.get('fum'),str) else data.get('fum'),format='DD/MM/YYYY'); a,b=st.columns(2); contaminado=a.checkbox("Paciente contaminado",value=bool(data.get('contaminado'))); sedacion=b.checkbox("Requiere sedación",value=bool(data.get('sedacion')))
        with t5:
          if 'Receta' in extras:
            prescription=st.text_area("Medicamentos: una línea por medicamento en formato Nombre/DCI | Concentración y forma | Cantidad | Dosis | Frecuencia | Duración | Horario",value=data.get('prescription',''),height=180)
            prescription_warnings=st.text_area("Indicaciones y advertencias",value=data.get('prescription_warnings',''))
          if not extras: st.info("No se seleccionaron documentos adicionales para esta atención.")
        save=st.form_submit_button("Guardar borrador")
        final=st.form_submit_button("Finalizar y cerrar consulta",type="primary")
        if save or final:
            payload=locals().copy(); payload.update({'perimetro_abdominal':perimetro,'glucosa_capilar':glucosa,'hemoglobina_capilar':hemoglobina,
                                                     'diagnoses':[x.strip() for x in diagnoses_text.splitlines() if x.strip()]})
            run(lambda:db.save_encounter(UID,enc['id'],payload,enc['version'],final),"Consulta finalizada." if final else "Borrador guardado.")

def history_page():
    st.title("Historia clínica")
    if ROLE in ('admin','medico') and st.session_state.get('encounter_id'):
        enc=db.encounter(UID,st.session_state.encounter_id)
        if enc['status']=='Borrador': clinical_form(enc)
        else: st.session_state.pop('encounter_id',None)
    p=patient_picker('history')
    if not p: return
    histories=db.histories(UID,p['id'])
    if histories:
        export_key='clinical_exports_'+str(p['id'])
        if st.button("Preparar expediente completo",type='primary'):
            prepared=run(lambda:(db.export_event(UID,'historia_clinica',p['id'],True),{'word':word_history(p,histories),'excel':clinical_excel(p,histories),'pdf':clinical_pdf(p,histories)})[1],rerun=False)
            if prepared: st.session_state[export_key]=prepared
        if st.session_state.get(export_key):
            files=st.session_state[export_key]; a,b,c=st.columns(3)
            a.download_button("Descargar Word",files['word'],f"Historia_{p['document']}.docx","application/vnd.openxmlformats-officedocument.wordprocessingml.document")
            b.download_button("Descargar Excel",files['excel'],f"Historia_{p['document']}.xlsx","application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
            c.download_button("Descargar PDF",files['pdf'],f"Historia_{p['document']}.pdf","application/pdf")
    for h in histories:
        with st.expander(f"{fmt_dt(h['occurred_at'])} · {h['doctor']} · {h['consultation_type']} · {h['status']}"):
            st.json(h['data'],expanded=True)
            for a in h['amendments']: st.info(f"Corrección {fmt_dt(a['created_at'])} · {a['author']}\n\n**Motivo:** {a['reason']}\n\n{a['text']}")
            if ROLE=='medico' and h['status']=='Finalizada' and h['author_id']==UID:
                reason=st.text_input("Motivo de corrección",key='ar'+str(h['id'])); text=st.text_area("Nota adicional",key='at'+str(h['id']))
                if st.button("Agregar corrección",key='ab'+str(h['id'])):
                    encounter_id=h['id']
                    run(lambda eid=encounter_id,why=reason,note=text:db.amend(UID,eid,why,note),"Corrección registrada.")

def doctors_page():
    st.title("Médicos y horarios")
    st.caption("Registre cada profesional manualmente o cargue varios desde Excel. Los profesionales retirados anteriormente no aparecen en esta lista.")
    dm=doctor_map(active=True)
    if ROLE=='admin':
        manual_tab,excel_tab=st.tabs(["Registrar uno","Cargar profesionales desde Excel"])
        with manual_tab:
            with st.form('new_doctor'):
                name=st.text_input("Nombre"); specialties=st.text_input("Especialidades separadas por coma"); professional_id=st.text_input("Documento de identificación"); registration=st.text_input("Registro profesional / libro / folio"); slot=st.number_input("Turno predeterminado (minutos)",5,240,30)
                if st.form_submit_button("Registrar"): run(lambda:db.save_doctor(UID,{'name':name,'specialties':specialties.split(','),'professional_id':professional_id,'registration':registration,'slot_minutes':slot,'active':True}),"Médico registrado.")
        with excel_tab:
            st.write("El Excel debe tener estas cinco columnas. En **especialidades** puede escribir varias separadas por coma.")
            template=[{'nombre':'Ana Pérez López','especialidades':'Medicina general, Medicina familiar','documento':'1712345678','registro_profesional':'MSP-12345','duracion_turno':30}]
            st.download_button("Descargar plantilla de profesionales",excel({'Profesionales':template}),"Plantilla_profesionales.xlsx","application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",key='doctor_template')
            uploaded=st.file_uploader("Seleccione el Excel completo",type=['xlsx'],key='doctor_excel')
            if uploaded:
                try:
                    frame=pd.read_excel(uploaded,dtype=str).fillna('')
                    columns={normalized_header(c):c for c in frame.columns}
                    required=['nombre','especialidades','documento','registro_profesional','duracion_turno']
                    missing=[x for x in required if x not in columns]
                    if missing: st.error("Faltan estas columnas: "+", ".join(missing))
                    else:
                        rows=[{key:row[columns[key]] for key in required} for _,row in frame.iterrows() if str(row[columns['nombre']]).strip()]
                        st.dataframe(pd.DataFrame(rows),hide_index=True,use_container_width=True)
                        st.caption(f"Se encontraron {len(rows)} profesional(es). La importación no crea usuarios ni contraseñas.")
                        if st.button("Importar profesionales",type='primary',disabled=not rows,key='import_doctors'):
                            result=run(lambda:db.import_doctors(UID,rows),rerun=False)
                            if result:
                                st.success(f"Listo: {result['creados']} creados, {result['actualizados']} actualizados y {len(result['errores'])} omitidos.")
                                if result['errores']: st.warning("\n".join(result['errores'][:20]))
                                st.rerun()
                except Exception as exc: fail(AppError(f"No se pudo leer el Excel: {exc}"))
    if not dm: st.info("No hay médicos registrados."); return
    name=st.selectbox("Médico",list(dm)); d=dm[name]; rules,_=db.schedules(UID,d['id'])
    st.write(pd.DataFrame([{'ID':r['id'],'Día':WEEKDAYS[r['weekday']],'Desde':str(r['start_time'])[:5],'Hasta':str(r['end_time'])[:5]} for r in rules]))
    if ROLE in ('admin','secretaria'):
        with st.form('add_schedule'):
            days=st.multiselect("Días",range(7),format_func=lambda x:WEEKDAYS[x]); start=st.time_input("Desde",time(8)); end=st.time_input("Hasta",time(17))
            if st.form_submit_button("Agregar horario"): run(lambda:db.add_schedule(UID,d['id'],days,start,end),"Horario agregado.")
        if rules:
            rid=st.selectbox("Retirar horario",[r['id'] for r in rules],format_func=lambda x:next(f"{WEEKDAYS[r['weekday']]} {str(r['start_time'])[:5]}–{str(r['end_time'])[:5]}" for r in rules if r['id']==x))
            if st.button("Retirar horario seleccionado"): run(lambda:db.remove_schedule(UID,rid),"Horario retirado.")
    if ROLE=='admin':
        with st.expander("Editar médico"):
            with st.form('edit_doctor'):
                n=st.text_input("Nombre",value=d['name']); specs=st.text_input("Especialidades",value=', '.join(d['specialties'])); professional_id=st.text_input("Documento de identificación",value=d.get('professional_id') or ''); registration=st.text_input("Registro profesional / libro / folio",value=d.get('registration') or ''); slot=st.number_input("Duración predeterminada",5,240,d['slot_minutes']); active=st.checkbox("Activo",value=d['active'])
                if st.form_submit_button("Guardar"): run(lambda:db.save_doctor(UID,{'name':n,'specialties':specs.split(','),'professional_id':professional_id,'registration':registration,'slot_minutes':slot,'active':active},d['id'],d['version']),"Médico actualizado.")

def users_page():
    st.title("Usuarios")
    a,b=st.columns([3,1]); query=a.text_input("Buscar por nombre o usuario"); include_inactive=b.checkbox("Mostrar retirados",value=False)
    rows=db.users(UID,query,include_inactive); st.dataframe(pd.DataFrame(rows),hide_index=True)
    labels={'Nueva cuenta':None}|{f"{proper_name(r['name'])} · {r['username']}":r for r in rows}; selected=labels[st.selectbox("Cuenta",labels)]
    dm=doctor_map(); names=list(dm)
    with st.form('user_form'):
        username=st.text_input("Usuario",value=selected['username'] if selected else '')
        name=st.text_input("Nombre",value=selected['name'] if selected else '')
        roles=['admin','secretaria','medico']; role=st.selectbox("Rol",roles,index=roles.index(selected['role']) if selected else 1)
        current_doc=next((n for n,d in dm.items() if selected and d['id']==selected['doctor_id']),names[0] if names else '')
        dname=st.selectbox("Médico vinculado",names,index=names.index(current_doc) if current_doc in names else 0,disabled=not names)
        active=st.checkbox("Activo",value=selected['active'] if selected else True)
        password=st.text_input("Contraseña temporal (dejar vacía para conservarla)",type="password")
        if st.form_submit_button("Guardar cuenta",type="primary"):
            data={'username':username,'name':name,'role':role,'doctor_id':dm[dname]['id'] if role=='medico' and names else None,'active':active}
            run(lambda:db.save_user(UID,data,selected['id'] if selected else None,password or None),"Cuenta guardada.")
    if selected:
        confirm_user=st.checkbox("Confirmo que deseo eliminar esta cuenta",key='confirm_delete_user')
        if st.button("Eliminar usuario",disabled=not confirm_user): run(lambda:db.delete_user(UID,selected['id']),"Usuario retirado.")

def certificates_page():
    st.title("Certificados médicos")
    st.caption("Emita certificados numerados con los datos del paciente y su registro profesional.")
    patient=patient_picker('certificate_patient')
    if not patient: return
    available_doctors=[d for d in db.doctors(UID,all_rows=False)]
    if ROLE=='admin':
        if not available_doctors: st.info("Primero registre un médico activo."); return
        doctor_labels={proper_name(d['name']):d for d in available_doctors}; profile=doctor_labels[st.selectbox("Médico que emite el certificado",doctor_labels,key='admin_certificate_doctor')]
    else: profile=next((d for d in available_doctors if d['id']==DOCTOR),None)
    if not profile or not profile.get('professional_id') or not profile.get('registration'):
        st.warning('Antes de emitir un certificado, complete su documento y número de registro en “Mi información profesional”.')
    needs_rest=st.checkbox("Requiere reposo médico",key='certificate_needs_rest')
    with st.form('medical_certificate_form'):
        a,b=st.columns(2)
        institution=a.text_input("Establecimiento de salud *",value="Medisuport")
        location=b.text_input("Lugar de emisión *",placeholder="Ej.: Quito")
        specialties=(profile or {}).get('specialties') or ['Medicina general']
        specialty=st.selectbox("Especialidad",specialties)
        diagnosis=st.text_area("Diagnóstico o condición médica *")
        cie10=st.text_input("Código CIE-10 (opcional)",max_chars=20)
        c1,c2=st.columns(2)
        rest_from=c1.date_input("Reposo desde",value=now().date(),disabled=not needs_rest,format='DD/MM/YYYY')
        rest_to=c2.date_input("Reposo hasta",value=now().date(),disabled=not needs_rest,format='DD/MM/YYYY')
        observations=st.text_area("Indicaciones u observaciones",placeholder="Tratamiento, restricciones o recomendaciones relevantes")
        if st.form_submit_button("Emitir certificado",type="primary"):
            data={'institution':institution,'location':location,'specialty':specialty,'diagnosis':diagnosis,'cie10':cie10,
                  'rest_from':rest_from if needs_rest else None,'rest_to':rest_to if needs_rest else None,'observations':observations}
            created=run(lambda:db.create_certificate(UID,patient['id'],data,profile['id'] if profile else None),rerun=False)
            if created:
                st.session_state.last_certificate=created
                st.success("Certificado emitido y registrado correctamente.")
    current=st.session_state.get('last_certificate')
    if current and current.get('patient_id')==patient['id']:
        number=f"CM-{current['issued_at'].astimezone(TZ).year}-{int(current['id']):06d}"
        st.subheader(f"Certificado {number}")
        c1,c2=st.columns(2)
        c1.download_button("Descargar certificado PDF",certificate_pdf(current),f"{number}_{normalize_doc(current['patient'])}.pdf","application/pdf")
        c2.download_button("Descargar certificado Word",certificate_word(current),f"{number}_{normalize_doc(current['patient'])}.docx","application/vnd.openxmlformats-officedocument.wordprocessingml.document")
    previous=db.certificates(UID,patient['id'])
    if previous:
        st.subheader("Certificados anteriores")
        labels={f"CM-{r['issued_at'].astimezone(TZ).year}-{int(r['id']):06d} · {r['issued_at'].astimezone(TZ).strftime('%d/%m/%Y %H:%M')} · {r['diagnosis'][:55]}":r for r in previous}
        selected=labels[st.selectbox("Seleccione un certificado",labels,key='previous_certificate')]
        number=f"CM-{selected['issued_at'].astimezone(TZ).year}-{int(selected['id']):06d}"
        a,b=st.columns(2)
        a.download_button("Descargar PDF nuevamente",certificate_pdf(selected),f"{number}.pdf","application/pdf",key='old_cert_pdf')
        b.download_button("Descargar Word nuevamente",certificate_word(selected),f"{number}.docx","application/vnd.openxmlformats-officedocument.wordprocessingml.document",key='old_cert_word')

def reports_page(full=False):
    st.title("Reportes y respaldo" if full else "Reportes")
    first,last=st.date_input("Periodo del reporte",value=(now().date().replace(day=1),now().date()),format='DD/MM/YYYY',key='report_dates')
    rows=db.appointments(UID,first,last)
    report_rows=[{
        'Fecha':r['start_at'].astimezone(TZ).strftime('%d/%m/%Y'),
        'Hora':r['start_at'].astimezone(TZ).strftime('%H:%M'),
        'Paciente':proper_name(r['patient']),
        'Documento':r['document'],
        'Teléfono':r['phone'] or '',
        'Convenio':r.get('agreement') or 'Particular',
        'Médico':proper_name(r['doctor']),
        'Especialidad':str(r['specialty'] or '').capitalize(),
        'Estado':r['status'],
        'Fecha de validación':r.get('validation_date'),
        'Observaciones':r.get('notes') or ''
    } for r in rows]
    st.caption(f"Periodo: {first.strftime('%d/%m/%Y')} al {last.strftime('%d/%m/%Y')} · {len(report_rows)} cita(s)")
    if report_rows:
        st.dataframe(pd.DataFrame(report_rows),hide_index=True,use_container_width=True)
    else:
        st.info("No existen citas en el periodo seleccionado.")
    if st.button("Preparar agenda Excel"):
        prepared=run(lambda:(db.export_event(UID,'agenda'),excel({'Agenda':report_rows}))[1],rerun=False)
        if prepared: st.session_state.report_excel=prepared
    if st.session_state.get('report_excel'):
        st.download_button("Descargar agenda Excel",st.session_state.report_excel,f"Agenda_{first}_{last}.xlsx","application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    if full:
        st.info("¿Qué es el respaldo recuperable? Es una copia de seguridad completa de pacientes, citas, historias, convenios, usuarios y datos financieros. Solo se usa para recuperar la información si la base de datos se daña, se elimina accidentalmente o se traslada a otra instalación. Descárguelo periódicamente y guárdelo en un lugar privado.")
        if st.button("Preparar respaldo recuperable"):
            prepared=run(lambda:db.backup(UID),rerun=False)
            if prepared: st.session_state.backup_zip=prepared
        if st.session_state.get('backup_zip'):
            st.download_button("Descargar respaldo recuperable",st.session_state.backup_zip,f"Medisuport_respaldo_{now().strftime('%Y%m%d_%H%M')}.zip","application/zip")
        st.caption("El archivo ZIP contiene todas las tablas de la versión 9 y una huella que permite detectar si el respaldo fue alterado o quedó incompleto.")

def financial_page():
    st.title("Facturación y caja")
    st.caption("Control administrativo de tarifas, cuentas por cobrar, cobros y movimientos. Las cuentas internas no reemplazan una factura electrónica autorizada por el SRI.")
    tab0,tab1,tab2,tab3,tab4,tab5=st.tabs(['Resumen','Nueva cuenta','Cuentas y cobros','Servicios y tarifarios','Caja','Reporte Excel'])
    month_start=now().date().replace(day=1)
    with tab0:
        first,last=st.date_input("Periodo",value=(month_start,now().date()),format='DD/MM/YYYY',key='fin_summary_dates')
        totals=db.financial_summary(UID,first,last)
        a,b,c,d=st.columns(4)
        a.metric("Facturado",f"${totals['billed']:,.2f}")
        b.metric("Cobrado",f"${totals['collected']:,.2f}")
        c.metric("Por cobrar",f"${totals['pending']:,.2f}")
        d.metric("Egresos de caja",f"${totals['expenses']:,.2f}")
        st.info(f"Del total facturado, ${totals['agreements']:,.2f} corresponde a convenios. El saldo se controla por cuenta y puede pagarse en varios abonos.")
    with tab1:
        appointments=db.billable_appointments(UID)
        services=db.services(UID,True)
        if not appointments: st.info("No hay citas recientes pendientes de facturar.")
        elif not services: st.warning("Primero active al menos un servicio en ‘Servicios y tarifarios’.")
        else:
            ap_labels={f"{fmt_dt(r['start_at'])} · {proper_name(r['patient'])} · {r.get('agreement') or 'Particular'} · {proper_name(r['doctor'])}":r for r in appointments}
            ap=ap_labels[st.selectbox("Cita a facturar",ap_labels,key='bill_appointment')]
            st.caption(f"Paciente: {proper_name(ap['patient'])} · Documento: {ap['document']} · Responsable: {ap.get('agreement') or 'Paciente particular'}")
            svc_labels={f"{s['code']} · {s['name']}":s for s in services}
            selected=st.multiselect("Servicios prestados",list(svc_labels),key='bill_services')
            tariffs={t['service_id']:t for t in db.tariffs(UID,ap['agreement_id'])} if ap.get('agreement_id') else {}
            items=[]; estimate=0.0
            for label in selected:
                svc=svc_labels[label]; tariff=tariffs.get(svc['id']); unit=float(tariff['agreed_price'] if tariff else svc['base_price'])
                c1,c2,c3=st.columns([3,1,1])
                c1.write(f"**{svc['name']}**  \\Tarifa aplicada: ${unit:,.2f}")
                qty=c2.number_input("Cantidad",min_value=0.01,value=1.0,step=1.0,key=f"qty_{svc['id']}")
                discount=c3.number_input("Descuento",min_value=0.0,value=0.0,step=1.0,key=f"disc_{svc['id']}")
                items.append({'service_id':svc['id'],'quantity':qty,'discount':discount}); estimate+=max(0,unit*qty-discount)
            due=st.date_input("Fecha de vencimiento",value=now().date(),format='DD/MM/YYYY',key='bill_due')
            notes=st.text_area("Observaciones de la cuenta",key='bill_notes')
            st.metric("Total estimado antes de impuestos",f"${estimate:,.2f}")
            if st.button("Emitir cuenta interna",type='primary',disabled=not items,key='create_invoice'):
                created=run(lambda:db.create_invoice(UID,ap['id'],items,due,notes),"Cuenta emitida correctamente.",False)
                if created: st.session_state.selected_invoice=created; st.rerun()
    with tab2:
        c1,c2=st.columns([2,1]); period=c1.date_input("Periodo de emisión",value=(month_start,now().date()),format='DD/MM/YYYY',key='invoice_dates'); status=c2.selectbox("Estado",['Todos','Emitida','Parcial','Pagada','Anulada'],key='invoice_status')
        rows=db.invoices(UID,period[0],period[1],status)
        if not rows: st.info("No hay cuentas en el periodo seleccionado.")
        else:
            table=[{'Cuenta':r['number'],'Fecha':r['issue_date'],'Paciente':proper_name(r['patient']),'Convenio':r.get('agreement') or 'Particular','Total':float(r['total']),'Cobrado':float(r['paid']),'Saldo':float(r['balance']),'Estado':r['status']} for r in rows]
            st.dataframe(pd.DataFrame(table),hide_index=True,use_container_width=True)
            labels={f"{r['number']} · {proper_name(r['patient'])} · saldo ${r['balance']:,.2f}":r for r in rows}
            chosen=labels[st.selectbox("Abrir cuenta",labels,key='invoice_open')]
            inv=db.invoice_detail(UID,chosen['id'])
            st.subheader(f"{inv['number']} · {proper_name(inv['patient'])}")
            st.caption(f"Convenio: {inv.get('agreement') or 'Particular'} · Paciente: ${inv['patient_responsibility']:,.2f} · Convenio: ${inv['agreement_responsibility']:,.2f}")
            st.dataframe(pd.DataFrame([{'Servicio':x['description'],'Cantidad':float(x['quantity']),'Precio':float(x['unit_price']),'Descuento':float(x['discount']),'Impuesto':float(x['tax']),'Total':float(x['total'])} for x in inv['items']]),hide_index=True,use_container_width=True)
            st.download_button("Descargar estado de cuenta PDF",billing_statement_pdf(inv),f"{inv['number']}.pdf","application/pdf",key='invoice_pdf')
            balance=inv['total']-inv['paid']
            if balance>0 and inv['status']!='Anulada':
                with st.form('payment_form'):
                    p1,p2,p3=st.columns(3); pay_date=p1.date_input("Fecha",value=now().date(),format='DD/MM/YYYY'); amount=p2.number_input("Valor",min_value=0.01,max_value=float(balance),value=float(balance),step=1.0); method=p3.selectbox("Método",['Efectivo','Tarjeta','Transferencia','Cheque','Otro'])
                    reference=st.text_input("Referencia"); pay_notes=st.text_input("Nota")
                    if st.form_submit_button("Registrar cobro",type='primary'): run(lambda:db.add_payment(UID,inv['id'],amount,method,reference,pay_notes,pay_date),"Cobro registrado.")
            if inv['payments']:
                st.write("**Abonos registrados**"); st.dataframe(pd.DataFrame([{'Fecha':p['payment_date'],'Valor':float(p['amount']),'Método':p['method'],'Referencia':p['reference']} for p in inv['payments']]),hide_index=True,use_container_width=True)
            if ROLE=='admin' and inv['status'] not in ('Anulada','Pagada'):
                with st.expander("Anular esta cuenta"):
                    reason=st.text_input("Motivo de anulación",key='annul_reason')
                    if st.button("Anular cuenta",disabled=len(reason.strip())<5,key='annul_invoice'): run(lambda:db.annul_invoice(UID,inv['id'],reason),"Cuenta anulada.")
            st.download_button("Descargar cuentas del periodo en Excel",excel({'Cuentas':table}),f"Cuentas_{period[0]}_{period[1]}.xlsx","application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",key='invoice_excel')
    with tab3:
        services=db.services(UID)
        st.write("**Servicios generales incluidos**")
        st.dataframe(pd.DataFrame([{'Código':s['code'],'Servicio':s['name'],'Descripción':s.get('description') or '','Categoría':s['category'],'Precio particular':float(s['base_price']),'Activo':s['active']} for s in services]),hide_index=True,use_container_width=True)
        if ROLE=='admin':
            st.caption("Los servicios generales ya están creados. Coloque sus precios o seleccione “Nuevo servicio” si necesita añadir otro.")
            labels={'Nuevo servicio':None}|{f"{s['code']} · {s['name']}":s for s in services}; selected=labels[st.selectbox("Crear o editar servicio",labels,key='service_edit')]
            with st.form('service_form'):
                categories=['Consulta','Procedimiento','Laboratorio','Imagen','Terapia / rehabilitación','Insumo','Administrativo / otro']
                a,b,c=st.columns(3); code=a.text_input("Código *",value=(selected or {}).get('code','')); name=b.text_input("Nombre *",value=(selected or {}).get('name','')); category=c.selectbox("Categoría",categories,index=categories.index((selected or {}).get('category','Consulta')) if (selected or {}).get('category','Consulta') in categories else 6,help="La categoría solo sirve para ordenar servicios y reportes; no cambia el precio ni el cálculo.")
                description=st.text_area("Descripción para reconocer el servicio",value=(selected or {}).get('description',''))
                d,e,f=st.columns(3); price=d.number_input("Precio particular",min_value=0.0,value=float((selected or {}).get('base_price',0)),step=1.0); tax=e.number_input("Impuesto %",min_value=0.0,max_value=100.0,value=float((selected or {}).get('tax_rate',0)),step=1.0); active=f.checkbox("Activo",value=(selected or {}).get('active',True))
                if st.form_submit_button("Guardar servicio",type='primary'): run(lambda:db.save_service(UID,{'code':code,'name':name,'description':description,'category':category,'base_price':price,'tax_rate':tax,'active':active},(selected or {}).get('id'),(selected or {}).get('version')),"Servicio guardado.")
            active_agreements=db.agreements(UID,True); active_services=[s for s in services if s['active']]
            if active_agreements and active_services:
                st.subheader("Tarifa por convenio")
                amap={a['name']:a for a in active_agreements}; smap={f"{s['code']} · {s['name']}":s for s in active_services}
                with st.form('tariff_form'):
                    agreement=amap[st.selectbox("Convenio",amap)]; service=smap[st.selectbox("Servicio",smap)]; existing=next((t for t in db.tariffs(UID,agreement['id']) if t['service_id']==service['id']),None)
                    x,y=st.columns(2); agreed=x.number_input("Tarifa acordada",min_value=0.0,value=float((existing or {}).get('agreed_price',service['base_price'])),step=1.0); copay=y.number_input("Copago del paciente",min_value=0.0,value=float((existing or {}).get('patient_copay',0)),step=1.0)
                    if st.form_submit_button("Guardar tarifa"): run(lambda:db.save_tariff(UID,agreement['id'],service['id'],agreed,copay),"Tarifa guardada.")
        tariffs=db.tariffs(UID)
        if tariffs: st.dataframe(pd.DataFrame([{'Convenio':t['agreement'],'Código':t['code'],'Servicio':t['service'],'Tarifa':float(t['agreed_price']),'Copago':float(t['patient_copay']),'Activo':t['active']} for t in tariffs]),hide_index=True,use_container_width=True)
    with tab4:
        first,last=st.date_input("Periodo de caja",value=(month_start,now().date()),format='DD/MM/YYYY',key='cash_dates')
        with st.form('cash_form'):
            a,b,c=st.columns(3); movement_date=a.date_input("Fecha",value=now().date(),format='DD/MM/YYYY'); kind=b.selectbox("Tipo",['Egreso','Ingreso']); method=c.selectbox("Método",['Efectivo','Tarjeta','Transferencia','Cheque','Otro'])
            d,e=st.columns(2); category=d.text_input("Categoría",placeholder="Ej.: insumos, arriendo, otro ingreso"); amount=e.number_input("Valor",min_value=0.01,value=1.0,step=1.0)
            description=st.text_input("Descripción"); reference=st.text_input("Referencia")
            if st.form_submit_button("Registrar movimiento",type='primary'): run(lambda:db.add_cash_movement(UID,{'movement_date':movement_date,'movement_type':kind,'category':category,'description':description,'amount':amount,'method':method,'reference':reference}),"Movimiento registrado.")
        movements=db.cash_movements(UID,first,last)
        cash_rows=[{'Fecha':m['movement_date'],'Tipo':m['movement_type'],'Categoría':m['category'],'Descripción':m['description'],'Valor':float(m['amount']),'Método':m['method'],'Cuenta':m.get('cuenta') or '','Usuario':proper_name(m['usuario'])} for m in movements]
        if cash_rows:
            st.dataframe(pd.DataFrame(cash_rows),hide_index=True,use_container_width=True)
            st.download_button("Descargar caja en Excel",excel({'Caja':cash_rows}),f"Caja_{first}_{last}.xlsx","application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",key='cash_excel')
        else: st.info("No hay movimientos de caja en este periodo.")
    with tab5:
        st.subheader("Reporte financiero para Excel")
        st.write("Descarga un solo archivo con cinco hojas: **Resumen, Cuentas, Detalle de servicios, Cobros y Caja**. Puede entregarse al administrador o contador para revisión y registro.")
        report_period=st.date_input("Periodo del reporte financiero",value=(month_start,now().date()),format='DD/MM/YYYY',key='financial_report_dates')
        if st.button("Preparar reporte financiero Excel",type='primary',key='prepare_financial_excel'):
            prepared=run(lambda:excel(db.financial_report(UID,report_period[0],report_period[1])),rerun=False)
            if prepared: st.session_state.financial_excel=prepared
        if st.session_state.get('financial_excel'):
            st.download_button("Descargar reporte financiero Excel",st.session_state.financial_excel,f"Reporte_financiero_{report_period[0]}_{report_period[1]}.xlsx","application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",key='download_financial_excel')

def admin_page():
    st.title("Administración")
    tab1,tab2,tab3,tab4=st.tabs(['Actualización de datos anteriores','Reglas clínicas','Personalización','Registro de actividad'])
    with tab1:
        counts,archived=legacy_preview(db,UID); st.write("Registros detectados en las tablas anteriores:",counts)
        st.caption("La importación conserva las tablas anteriores, guarda una copia JSON de cada fila y puede repetirse sin duplicar lo ya importado.")
        if st.button("Importar datos anteriores",type="primary"): run(lambda:import_legacy(db,UID),"Importación ejecutada.")
        problems=legacy_issues(db,UID)
        if problems:
            st.warning(f"{len(problems)} registros requieren revisión manual.")
            st.dataframe(pd.DataFrame([{'Tabla':r['source_table'],'Clave':r['source_key'],'Problema':r['issue']} for r in problems]),hide_index=True)
            st.download_button("Descargar pendientes",excel({'Pendientes':problems}),"Importacion_pendientes.xlsx")
    with tab2:
        rule=db.settings(UID); labels={'specialty':'Por especialidad','global':'Por historial general'}; choice=st.radio("Cómo asignar C1 / SUB",labels,index=list(labels).index(rule),format_func=lambda x:labels[x])
        if st.button("Guardar regla"): run(lambda:db.settings(UID,choice),"Regla guardada.")
    with tab3:
        st.subheader("Logo y colores de la clínica")
        st.caption("Puede controlar todos los colores visibles. Estos cambios no alteran pacientes, citas ni historias clínicas.")
        with st.form('branding_form'):
            clinic_name=st.text_input("Nombre de la clínica",value=brand['name'])
            st.write("**Colores institucionales y botones**")
            x,y=st.columns(2); primary=x.color_picker("Color principal",value=brand['primary']); secondary=y.color_picker("Color secundario",value=brand['secondary'])
            st.write("**Página, tarjetas y campos**")
            x,y,z=st.columns(3); background=x.color_picker("Fondo de la página",value=brand['background']); surface=y.color_picker("Tarjetas y recuadros",value=brand['surface']); input_color=z.color_picker("Campos de escritura",value=brand['input'])
            st.write("**Textos y separaciones**")
            x,y,z=st.columns(3); text_color=x.color_picker("Texto principal",value=brand['text']); muted=y.color_picker("Texto secundario",value=brand['muted']); border=z.color_picker("Bordes y divisiones",value=brand['border'])
            sidebar_text=st.color_picker("Texto del menú lateral",value=brand['sidebar_text'])
            logo_file=st.file_uploader("Cambiar logo",type=['png','jpg','jpeg'],help="Si no selecciona una imagen se conserva el logo actual.")
            if st.form_submit_button("Guardar personalización",type='primary'):
                logo=''
                if logo_file:
                    if logo_file.size>1_000_000: st.error("Use una imagen menor a 1 MB.")
                    else: logo=base64.b64encode(logo_file.getvalue()).decode()
                colors={'primary':primary,'secondary':secondary,'background':background,'surface':surface,'text':text_color,'muted':muted,'border':border,'input':input_color,'sidebar_text':sidebar_text}
                if not logo_file or logo: run(lambda:db.save_branding(UID,clinic_name,colors,logo),"Personalización guardada.")
        st.markdown(f"""<div style="background:{brand['background']};border:2px solid {brand['border']};border-radius:14px;padding:16px;color:{brand['text']}">
        <b style="color:{brand['primary']}">Vista previa actual</b><br><span style="color:{brand['muted']}">Texto secundario y explicaciones</span>
        <div style="margin-top:10px;background:{brand['surface']};border:1px solid {brand['border']};padding:12px;border-radius:10px">Tarjeta o recuadro visible
        <div style="margin-top:8px;background:{brand['input']};border:1px solid {brand['border']};padding:8px;border-radius:8px">Campo de escritura</div></div></div>""",unsafe_allow_html=True)
        defaults={'primary':'#001F5B','secondary':'#008BC4','background':'#F3F7FA','surface':'#FFFFFF','text':'#17313A','muted':'#506670','border':'#DCE7EC','input':'#FBFDFE','sidebar_text':'#F4FBFC'}
        if st.button("Restaurar colores recomendados",key='reset_brand_colors'):
            run(lambda:db.save_branding(UID,clinic_name if 'clinic_name' in locals() else brand['name'],defaults,''),"Colores recomendados restaurados.")
    with tab4:
        logs=db.audit_rows(UID); st.dataframe(pd.DataFrame(logs),hide_index=True,use_container_width=True)

try:
    {'Inicio':dashboard,'Pacientes':patients_page,'Convenios':agreements_page,'Agenda':agenda_page,'Facturación y caja':financial_page,'Mis citas':lambda:agenda_page(True),'Historia clínica':history_page,
     'Certificados médicos':certificates_page,'Mi información profesional':professional_profile_page,'Médicos y horarios':doctors_page,'Usuarios':users_page,'Reportes':reports_page,'Reportes y respaldo':lambda:reports_page(True),'Administración':admin_page}[page]()
except Exception as exc: fail(exc)
