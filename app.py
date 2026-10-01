"""Medisuport v2 — interfaz Streamlit."""
from datetime import date, datetime, time, timedelta
from pathlib import Path
import io, json, logging, traceback, re, unicodedata
import pandas as pd
import streamlit as st
from psycopg2.errors import ExclusionViolation, UniqueViolation

from core import Database, AppError, TZ, WEEKDAYS, STATUSES, now, local_datetime, proper_name
from exports import word_history, clinical_excel, clinical_pdf, excel
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
        if success: st.success(success)
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
 'admin':['Inicio','Pacientes','Convenios','Agenda','Historia clínica','Médicos y horarios','Usuarios','Reportes y respaldo','Administración'],
 'secretaria':['Inicio','Pacientes','Convenios','Agenda','Médicos y horarios','Reportes'],
 'medico':['Inicio','Mis citas','Historia clínica','Pacientes']
}[ROLE]
# Los cambios de página solicitados por una acción se aplican al comienzo del
# siguiente ciclo, antes de crear el widget de navegación.
if 'next_page' in st.session_state:
    st.session_state.page=st.session_state.pop('next_page')
st.sidebar.title("Medisuport 🏥")
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
    e=existing or {}
    # La pestaña "Buscar y editar" y la pestaña "Registrar" se renderizan
    # al mismo tiempo. Cada formulario necesita una clave distinta.
    form_key=f"patient_form_{e.get('id', 'new')}"
    with st.form(form_key):
        a,b=st.columns(2)
        with a:
            document=st.text_input("Documento *",value=e.get('document',''),disabled=bool(existing))
            name=st.text_input("Nombre completo *",value=e.get('name',''))
            sex=st.selectbox("Sexo",['','Femenino','Masculino','Otro'],index=['','Femenino','Masculino','Otro'].index(e.get('sex') or '') if (e.get('sex') or '') in ['','Femenino','Masculino','Otro'] else 0)
            birth=st.date_input("Fecha de nacimiento",value=e.get('birth_date'),min_value=date(1900,1,1),max_value=now().date(),format='DD/MM/YYYY')
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
            data={'document':document,'name':name,'sex':sex,'birth_date':birth,'phone':phone,'email':email,
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
            else: st.info("No hay pacientes archivados.")

IMPORT_COLUMNS={'cedula','nombres_completos','sexo','fecha_nacimiento','telefono','correo','direccion','ocupacion','numero_afiliado'}
def normalized_header(value):
    text=unicodedata.normalize('NFKD',str(value or '')).encode('ascii','ignore').decode().lower().strip()
    return re.sub(r'[^a-z0-9]+','_',text).strip('_')
def patient_import_preview(uploaded,agreement_name):
    frame=pd.read_excel(uploaded,sheet_name='Pacientes',dtype=str)
    frame.columns=[normalized_header(c) for c in frame.columns]
    missing=IMPORT_COLUMNS-set(frame.columns)
    if missing: raise AppError('Faltan columnas en la plantilla: '+', '.join(sorted(missing))+'.')
    frame=frame[list(IMPORT_COLUMNS)].fillna('')
    rows=[]; seen=set()
    sex_map={'f':'Femenino','femenino':'Femenino','mujer':'Femenino','m':'Masculino','masculino':'Masculino','hombre':'Masculino','otro':'Otro'}
    for _,source in frame.iterrows():
        if not any(str(x).strip() for x in source): continue
        raw_date=str(source['fecha_nacimiento']).strip(); birth=None
        if raw_date:
            parsed=pd.to_datetime(raw_date,dayfirst=True,errors='coerce')
            birth=None if pd.isna(parsed) else parsed.date()
        document=re.sub(r'\.0$','',str(source['cedula']).strip())
        row={'document':document,'name':source['nombres_completos'],'sex':sex_map.get(normalized_header(source['sexo']),str(source['sexo']).strip()),
             'birth_date':birth,'phone':re.sub(r'\.0$','',str(source['telefono']).strip()),'email':source['correo'],'address':source['direccion'],
             'occupation':source['ocupacion'],'coverage':agreement_name,'origin':'Convenio institucional','member_number':re.sub(r'\.0$','',str(source['numero_afiliado']).strip())}
        try:
            from core import validate_patient
            validate_patient(row)
            if document in seen: raise AppError('Documento repetido dentro del archivo.')
            seen.add(document); status='Listo'
        except Exception as exc: status=str(exc)
        rows.append((row,status))
    return rows

def agreements_page():
    st.title("Convenios e importación")
    st.caption("Registre cualquier institución y cargue sus pacientes con la plantilla oficial de Excel.")
    rows=db.agreements(UID)
    if rows:
        st.dataframe(pd.DataFrame([{'Convenio':proper_name(a['name']),'Código':a['code'] or '', 'Pacientes activos':a['patient_count'],
                                   'Exige autorización':'Sí' if a['requires_authorization'] else 'No','Vigente':'Sí' if a['active'] else 'No'} for a in rows]),hide_index=True,use_container_width=True)
    if ROLE=='admin':
        labels={'Nuevo convenio':None}|{proper_name(a['name']):a for a in rows}; selected=labels[st.selectbox("Crear o editar",labels,key='agreement_edit')]
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
                requires=st.checkbox("Exige autorización para cada cita",value=selected['requires_authorization'] if selected else False)
                active=st.checkbox("Convenio activo",value=selected['active'] if selected else True)
            notes=st.text_area("Observaciones",value=selected['notes'] or '' if selected else '')
            if st.form_submit_button("Guardar convenio",type='primary'):
                data={'name':name,'code':code,'tax_id':tax_id,'contact_name':contact,'phone':phone,'email':email,'notes':notes,
                      'requires_authorization':requires,'active':active,'start_date':selected.get('start_date') if selected else None,'end_date':selected.get('end_date') if selected else None}
                run(lambda:db.save_agreement(UID,data,selected['id'] if selected else None,selected['version'] if selected else None),"Convenio guardado.")
    active=[a for a in rows if a['active']]
    st.subheader("Importar pacientes")
    template=Path(__file__).parent/'plantilla_importacion_pacientes.xlsx'
    if template.exists(): st.download_button("Descargar plantilla oficial",template.read_bytes(),template.name,"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    if not active: st.info("Primero registre y active un convenio."); return
    choices={proper_name(a['name']):a for a in active}; chosen=choices[st.selectbox("Convenio de destino",choices,key='agreement_import')]
    uploaded=st.file_uploader("Archivo Excel completado",type=['xlsx'],key='patient_xlsx')
    if uploaded:
        try:
            prepared=patient_import_preview(uploaded,chosen['name'])
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
    linked=db.patient_agreements(UID,p['id'])
    options={'Particular':None}|{a['name']:a for a in linked}
    current=next((name for name,a in options.items() if a and existing and a['id']==existing.get('agreement_id')),'Particular')
    agreement_name=st.selectbox("Facturación / convenio",list(options),index=list(options).index(current),key='bc'+str(existing and existing['id']))
    agreement=options[agreement_name]; needs_auth=bool(agreement and agreement['requires_authorization'])
    authorization=st.text_input("Número de autorización",value=(existing.get('authorization_code') or '') if existing else '',disabled=not agreement,key='ba'+str(existing and existing['id']))
    expires=st.date_input("Vencimiento autorización",value=existing.get('expires_on') if existing and existing.get('expires_on') else day,disabled=not agreement,format='DD/MM/YYYY',key='be'+str(existing and existing['id']))
    if needs_auth: st.caption("Este convenio exige autorización vigente para agendar.")
    notes=st.text_area("Observaciones",value=(existing.get('notes') or '') if existing else '',key='bn'+str(existing and existing['id']))
    if st.button("Guardar reagendamiento" if existing else "Agendar",type="primary",key='save_book'+str(existing and existing['id'])):
        run(lambda:db.book(UID,p['id'],d['id'],specialty,labels[selected],duration,agreement['id'] if agreement else None,authorization,expires if agreement else None,notes,existing['id'] if existing else None,existing['version'] if existing else None),"Cita guardada.")

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
    with st.form('clinical_form'):
        st.subheader(f"Consulta {enc['consultation_type']}")
        t1,t2,t3,t4,t5=st.tabs(['Anamnesis','Examen físico','Diagnóstico y plan','Solicitudes','Receta'])
        with t1:
            motivo=st.text_area("Motivo de consulta *",value=data.get('motivo',''))
            personal_conditions=st.multiselect("Antecedentes patológicos personales",CONDITIONS,default=data.get('personal_conditions',[]))
            personal_details=st.text_area("Datos clínicos, quirúrgicos, obstétricos y alérgicos relevantes",value=data.get('personal_details',''))
            family_conditions=st.multiselect("Antecedentes patológicos familiares",CONDITIONS,default=data.get('family_conditions',[]))
            family_details=st.text_area("Descripción de antecedentes familiares",value=data.get('family_details',''))
            a,b=st.columns(2); habitos=a.text_area("Hábitos de vida",value=data.get('habitos','')); alergias=b.text_area("Alergias",value=data.get('alergias',''))
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
            systems_review=st.multiselect("Revisión de órganos y sistemas con patología",SYSTEMS,default=data.get('systems_review',[])); systems_details=st.text_area("Descripción de la revisión por sistemas",value=data.get('systems_details',''))
            physical_regional=st.multiselect("Examen físico regional con hallazgos",REGIONAL,default=data.get('physical_regional',[])); physical_systemic=st.multiselect("Examen físico sistémico con hallazgos",SYSTEMIC,default=data.get('physical_systemic',[])); physical_details=st.text_area("Descripción de hallazgos del examen físico",value=data.get('physical_details',''))
        with t3:
            diagnostico=st.text_area("Diagnóstico principal *",value=data.get('diagnostico',''))
            diagnoses_text=st.text_area("Diagnósticos codificados: una línea por diagnóstico en formato CIE10 | Presuntivo/Definitivo | Descripción",value='\n'.join(data.get('diagnoses',[])))
            tratamiento=st.text_area("Plan diagnóstico, terapéutico y educacional",value=data.get('tratamiento','')); examenes=st.text_area("Resultados de exámenes y procedimientos relevantes",value=data.get('examenes',''))
        with t4:
            interconsult_specialty=st.text_input("Especialidad para interconsulta",value=data.get('interconsult_specialty','')); interconsult_reason=st.text_area("Motivo de interconsulta",value=data.get('interconsult_reason','')); clinical_summary=st.text_area("Resumen del cuadro clínico",value=data.get('clinical_summary','')); exam_results=st.text_area("Hallazgos relevantes",value=data.get('exam_results','')); therapeutic_plan=st.text_area("Plan terapéutico realizado",value=data.get('therapeutic_plan',''))
            referral_type=st.selectbox("Tipo de referencia",['','Referencia','Derivación','Contrarreferencia','Referencia inversa'],index=['','Referencia','Derivación','Contrarreferencia','Referencia inversa'].index(data.get('referral_type','')) if data.get('referral_type','') in ['','Referencia','Derivación','Contrarreferencia','Referencia inversa'] else 0)
            referral_reasons=st.multiselect("Motivos",['Accesibilidad geográfica','Falta de espacio físico','Falta de equipamiento','Equipos en mal estado','Problemas de infraestructura','Problemas de abastecimiento','Insuficiencia de profesionales','Inadecuada capacidad resolutiva','Ausencia de prestación'],default=data.get('referral_reasons',[]))
            referral_destination=st.text_input("Institución / establecimiento de destino",value=data.get('referral_destination','')); referral_service=st.text_input("Servicio de destino",value=data.get('referral_service','')); referral_specialty=st.text_input("Especialidad de destino",value=data.get('referral_specialty','')); referral_summary=st.text_area("Resumen para referencia",value=data.get('referral_summary','')); referral_findings=st.text_area("Hallazgos para referencia",value=data.get('referral_findings',''))
            lab_tests=st.multiselect("Exámenes de laboratorio solicitados",LAB_TESTS,default=data.get('lab_tests',[])); other_lab_tests=st.text_area("Otros exámenes / muestra / sitio anatómico",value=data.get('other_lab_tests','')); lab_treatment=st.text_area("Tratamiento terapéutico relacionado con la solicitud",value=data.get('lab_treatment',''))
            imaging_types=st.multiselect("Imagenología solicitada",['RX convencional','RX portátil','Tomografía','Resonancia','Ecografía','Mamografía','Procedimiento','Otro'],default=data.get('imaging_types',[])); imaging_description=st.text_area("Descripción del estudio",value=data.get('imaging_description','')); imaging_reason=st.text_area("Motivo de imagenología",value=data.get('imaging_reason','')); fum=st.date_input("FUM (si corresponde)",value=data.get('fum'),format='DD/MM/YYYY'); a,b=st.columns(2); contaminado=a.checkbox("Paciente contaminado",value=bool(data.get('contaminado'))); sedacion=b.checkbox("Requiere sedación",value=bool(data.get('sedacion')))
        with t5:
            prescription=st.text_area("Medicamentos: una línea por medicamento en formato Nombre/DCI | Concentración y forma | Cantidad | Dosis | Frecuencia | Duración | Horario",value=data.get('prescription',''),height=180)
            prescription_warnings=st.text_area("Indicaciones y advertencias",value=data.get('prescription_warnings',''))
        save=st.form_submit_button("Guardar borrador")
        final=st.form_submit_button("Finalizar y cerrar consulta",type="primary")
        if save or final:
            payload=locals().copy(); payload.update({'perimetro_abdominal':perimetro,'glucosa_capilar':glucosa,'hemoglobina_capilar':hemoglobina,
                                                     'diagnoses':[x.strip() for x in diagnoses_text.splitlines() if x.strip()]})
            run(lambda:db.save_encounter(UID,enc['id'],payload,enc['version'],final),"Consulta finalizada." if final else "Borrador guardado.")

def history_page():
    st.title("Historia clínica")
    if ROLE=='medico' and st.session_state.get('encounter_id'):
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
    dm=doctor_map(active=ROLE!='admin')
    if ROLE=='admin':
        with st.expander("Registrar médico"):
            with st.form('new_doctor'):
                name=st.text_input("Nombre"); specialties=st.text_input("Especialidades separadas por coma"); professional_id=st.text_input("Documento de identificación"); registration=st.text_input("Registro profesional / libro / folio"); slot=st.number_input("Turno predeterminado (minutos)",5,240,30)
                if st.form_submit_button("Registrar"): run(lambda:db.save_doctor(UID,{'name':name,'specialties':specialties.split(','),'professional_id':professional_id,'registration':registration,'slot_minutes':slot,'active':True}),"Médico registrado.")
    if not dm: st.info("No hay médicos registrados."); return
    name=st.selectbox("Médico",list(dm)); d=dm[name]; rules,blocks=db.schedules(UID,d['id'])
    st.write(pd.DataFrame([{'ID':r['id'],'Día':WEEKDAYS[r['weekday']],'Desde':str(r['start_time'])[:5],'Hasta':str(r['end_time'])[:5]} for r in rules]))
    if ROLE in ('admin','secretaria'):
        with st.form('add_schedule'):
            days=st.multiselect("Días",range(7),format_func=lambda x:WEEKDAYS[x]); start=st.time_input("Desde",time(8)); end=st.time_input("Hasta",time(17))
            if st.form_submit_button("Agregar horario"): run(lambda:db.add_schedule(UID,d['id'],days,start,end),"Horario agregado.")
        if rules:
            rid=st.selectbox("Retirar horario",[r['id'] for r in rules],format_func=lambda x:next(f"{WEEKDAYS[r['weekday']]} {str(r['start_time'])[:5]}–{str(r['end_time'])[:5]}" for r in rules if r['id']==x))
            if st.button("Retirar horario seleccionado"): run(lambda:db.remove_schedule(UID,rid),"Horario retirado.")
        st.subheader("Ausencias y bloqueos")
        with st.form('block'):
            day=st.date_input("Fecha",min_value=now().date(),format='DD/MM/YYYY'); a,b=st.columns(2); start=a.time_input("Inicio",time(8)); end=b.time_input("Fin",time(17)); reason=st.text_input("Motivo")
            if st.form_submit_button("Bloquear"): run(lambda:db.add_block(UID,d['id'],local_datetime(day,start),local_datetime(day,end),reason),"Bloqueo agregado.")
        if blocks:
            st.dataframe(pd.DataFrame([{'ID':b['id'],'Desde':fmt_dt(b['start_at']),'Hasta':fmt_dt(b['end_at']),'Motivo':b['reason']} for b in blocks]),hide_index=True)
            bid=st.selectbox("Retirar bloqueo",[b['id'] for b in blocks]);
            if st.button("Retirar bloqueo seleccionado"): run(lambda:db.remove_block(UID,bid),"Bloqueo retirado.")
    if ROLE=='admin':
        with st.expander("Editar médico"):
            with st.form('edit_doctor'):
                n=st.text_input("Nombre",value=d['name']); specs=st.text_input("Especialidades",value=', '.join(d['specialties'])); professional_id=st.text_input("Documento de identificación",value=d.get('professional_id') or ''); registration=st.text_input("Registro profesional / libro / folio",value=d.get('registration') or ''); slot=st.number_input("Duración predeterminada",5,240,d['slot_minutes']); active=st.checkbox("Activo",value=d['active'])
                if st.form_submit_button("Guardar"): run(lambda:db.save_doctor(UID,{'name':n,'specialties':specs.split(','),'professional_id':professional_id,'registration':registration,'slot_minutes':slot,'active':active},d['id'],d['version']),"Médico actualizado.")

def users_page():
    st.title("Usuarios")
    rows=db.users(UID); st.dataframe(pd.DataFrame(rows),hide_index=True)
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
        'Autorización':r.get('authorization_code') or '',
        'Vencimiento':r.get('expires_on'),
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
        if st.button("Preparar respaldo recuperable"):
            prepared=run(lambda:db.backup(UID),rerun=False)
            if prepared: st.session_state.backup_zip=prepared
        if st.session_state.get('backup_zip'):
            st.download_button("Descargar respaldo recuperable",st.session_state.backup_zip,f"Medisuport_respaldo_{now().strftime('%Y%m%d_%H%M')}.zip","application/zip")
        st.caption("El respaldo recuperable contiene todas las tablas de la versión 4 y una huella de integridad.")

def admin_page():
    st.title("Administración")
    tab1,tab2,tab3=st.tabs(['Actualización de datos anteriores','Reglas clínicas','Registro de actividad'])
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
        logs=db.audit_rows(UID); st.dataframe(pd.DataFrame(logs),hide_index=True,use_container_width=True)

try:
    {'Inicio':dashboard,'Pacientes':patients_page,'Convenios':agreements_page,'Agenda':agenda_page,'Mis citas':lambda:agenda_page(True),'Historia clínica':history_page,
     'Médicos y horarios':doctors_page,'Usuarios':users_page,'Reportes':reports_page,'Reportes y respaldo':lambda:reports_page(True),'Administración':admin_page}[page]()
except Exception as exc: fail(exc)
