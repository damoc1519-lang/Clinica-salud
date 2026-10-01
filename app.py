"""Medisuport v2 — interfaz Streamlit."""
from datetime import date, datetime, time, timedelta
import io, json, logging, traceback
import pandas as pd
import streamlit as st
from psycopg2.errors import ExclusionViolation, UniqueViolation

from core import Database, AppError, TZ, WEEKDAYS, STATUSES, now, local_datetime
from exports import word_history, excel
from legacy import preview as legacy_preview, import_legacy, issues as legacy_issues

st.set_page_config(page_title="Medisuport", page_icon="🏥", layout="wide")
logging.basicConfig(level=logging.INFO)
st.markdown("""
<style>
.block-container{padding-top:1.2rem;max-width:1500px}.stMetric{border:1px solid #e6e9ef;border-radius:12px;padding:12px}
[data-testid="stSidebar"]{background:#f5f8fb}.small-note{color:#586174;font-size:.88rem}
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
                if ok is None:
                    st.session_state.pop('user',None); st.rerun()
    st.stop()

pages={
 'admin':['Inicio','Pacientes','Agenda','Historia clínica','Médicos y horarios','Usuarios','Reportes y respaldo','Administración'],
 'secretaria':['Inicio','Pacientes','Agenda','Médicos y horarios','Reportes'],
 'medico':['Inicio','Mis citas','Historia clínica','Pacientes']
}[ROLE]
st.sidebar.title("Medisuport 🏥")
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
def doctor_map(active=True): return {d['name']:d for d in doctors(active)}
def patient_picker(key,active=True):
    query=st.text_input("Buscar por nombre, documento o teléfono",key=key+"_q")
    rows=db.patients(UID,query,archived=not active)
    if not rows: st.info("No hay pacientes que coincidan."); return None
    labels={f"{p['name']} · {p['document']}":p for p in rows}
    return labels[st.selectbox("Paciente",labels,key=key+"_p")]
def fmt_dt(v): return v.astimezone(TZ).strftime('%d/%m/%Y %H:%M') if v else ''
def appointment_table(rows):
    return pd.DataFrame([{'Hora':fmt_dt(r['start_at']),'Paciente':r['patient'],'Documento':r['document'],'Teléfono':r['phone'],'Médico':r['doctor'],'Especialidad':r['specialty'],'Estado':r['status']} for r in rows])

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
    with st.form("patient_form"):
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
            coverages=['Particular / Propio de la Clínica','ISSFA','IESS','MSP','Seguro Privado']
            coverage=st.selectbox("Cobertura",coverages,index=coverages.index(e.get('coverage')) if e.get('coverage') in coverages else 0)
            origins=['Propio de la Clínica','Prestador Externo ISSFA']
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
                labels={f"{p['name']} · {p['document']}":p for p in archived}; p=labels[st.selectbox("Archivado",labels)]
                st.warning(f"Motivo: {p['archive_reason'] or 'No registrado'}")
                reason=st.text_input("Motivo de reactivación")
                if st.button("Reactivar"): run(lambda:db.archive_patient(UID,p['id'],reason,True),"Paciente reactivado.")
            else: st.info("No hay pacientes archivados.")

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
                if eid: st.session_state.encounter_id=eid; st.session_state.page='Historia clínica'; st.rerun()
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
    issfa=p['coverage']=='ISSFA' or 'ISSFA' in (p['origin'] or '')
    authorization=st.text_input("Número de autorización ISSFA",value=(existing.get('authorization_code') or '') if existing else '',disabled=not issfa,key='ba'+str(existing and existing['id']))
    expires=st.date_input("Vencimiento autorización",value=existing.get('expires_on') if existing and existing.get('expires_on') else day,disabled=not issfa,format='DD/MM/YYYY',key='be'+str(existing and existing['id']))
    notes=st.text_area("Observaciones",value=(existing.get('notes') or '') if existing else '',key='bn'+str(existing and existing['id']))
    if st.button("Guardar reagendamiento" if existing else "Agendar",type="primary",key='save_book'+str(existing and existing['id'])):
        run(lambda:db.book(UID,p['id'],d['id'],specialty,labels[selected],duration,authorization,expires if issfa else None,notes,existing['id'] if existing else None,existing['version'] if existing else None),"Cita guardada.")

CLINICAL_KEYS=['antecedentes_pers','antecedentes_fam','habitos','motivo','enfermedad_actual','peso','talla','pa','fc','diagnostico','tratamiento','examenes']
def clinical_form(enc):
    data=enc['data'] or {}
    with st.form('clinical_form'):
        st.subheader(f"Consulta {enc['consultation_type']}")
        a,b=st.columns(2)
        with a:
            antecedentes_pers=st.text_area("Antecedentes personales",value=data.get('antecedentes_pers',''))
            antecedentes_fam=st.text_area("Antecedentes familiares",value=data.get('antecedentes_fam',''))
        with b: habitos=st.text_area("Hábitos de vida",value=data.get('habitos',''))
        motivo=st.text_area("Motivo de consulta *",value=data.get('motivo',''))
        enfermedad_actual=st.text_area("Enfermedad actual",value=data.get('enfermedad_actual',''))
        cols=st.columns(5)
        peso=cols[0].number_input("Peso kg",0.0,500.0,float(data.get('peso') or 0),step=.1)
        talla=cols[1].number_input("Talla cm",0.0,280.0,float(data.get('talla') or 0),step=.1)
        pa=cols[2].text_input("PA",value=data.get('pa',''))
        fc=cols[3].number_input("FC",0,350,int(data.get('fc') or 0))
        imc=round(peso/(talla/100)**2,2) if peso and talla else None; cols[4].metric("IMC",imc or '—')
        diagnostico=st.text_area("Diagnóstico *",value=data.get('diagnostico',''))
        tratamiento=st.text_area("Tratamiento e indicaciones",value=data.get('tratamiento',''))
        examenes=st.text_area("Exámenes complementarios",value=data.get('examenes',''))
        save=st.form_submit_button("Guardar borrador")
        final=st.form_submit_button("Finalizar y cerrar consulta",type="primary")
        if save or final:
            payload={'antecedentes_pers':antecedentes_pers,'antecedentes_fam':antecedentes_fam,'habitos':habitos,
                     'motivo':motivo,'enfermedad_actual':enfermedad_actual,'peso':peso,'talla':talla,'pa':pa,
                     'fc':fc,'diagnostico':diagnostico,'tratamiento':tratamiento,'examenes':examenes}
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
        export_key='word_export_'+str(p['id'])
        if st.button("Preparar expediente Word"):
            prepared=run(lambda:(db.export_event(UID,'historia_clinica',p['id'],True),word_history(p,histories))[1],rerun=False)
            if prepared: st.session_state[export_key]=prepared
        if st.session_state.get(export_key):
            st.download_button("Descargar expediente Word",st.session_state[export_key],f"Historia_{p['document']}.docx","application/vnd.openxmlformats-officedocument.wordprocessingml.document")
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
                name=st.text_input("Nombre"); specialties=st.text_input("Especialidades separadas por coma"); slot=st.number_input("Turno predeterminado (minutos)",5,240,30)
                if st.form_submit_button("Registrar"): run(lambda:db.save_doctor(UID,{'name':name,'specialties':specialties.split(','),'slot_minutes':slot,'active':True}),"Médico registrado.")
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
                n=st.text_input("Nombre",value=d['name']); specs=st.text_input("Especialidades",value=', '.join(d['specialties'])); slot=st.number_input("Duración predeterminada",5,240,d['slot_minutes']); active=st.checkbox("Activo",value=d['active'])
                if st.form_submit_button("Guardar"): run(lambda:db.save_doctor(UID,{'name':n,'specialties':specs.split(','),'slot_minutes':slot,'active':active},d['id'],d['version']),"Médico actualizado.")

def users_page():
    st.title("Usuarios")
    rows=db.users(UID); st.dataframe(pd.DataFrame(rows),hide_index=True)
    labels={'Nueva cuenta':None}|{f"{r['name']} · {r['username']}":r for r in rows}; selected=labels[st.selectbox("Cuenta",labels)]
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
    if st.button("Preparar agenda Excel"):
        prepared=run(lambda:(db.export_event(UID,'agenda'),excel({'Agenda':rows}))[1],rerun=False)
        if prepared: st.session_state.report_excel=prepared
    if st.session_state.get('report_excel'):
        st.download_button("Descargar agenda Excel",st.session_state.report_excel,f"Agenda_{first}_{last}.xlsx","application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    if full:
        if st.button("Preparar respaldo recuperable"):
            prepared=run(lambda:db.backup(UID),rerun=False)
            if prepared: st.session_state.backup_zip=prepared
        if st.session_state.get('backup_zip'):
            st.download_button("Descargar respaldo recuperable",st.session_state.backup_zip,f"Medisuport_respaldo_{now().strftime('%Y%m%d_%H%M')}.zip","application/zip")
        st.caption("El respaldo recuperable contiene todas las tablas de la versión 2 y una huella de integridad.")

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
    {'Inicio':dashboard,'Pacientes':patients_page,'Agenda':agenda_page,'Mis citas':lambda:agenda_page(True),'Historia clínica':history_page,
     'Médicos y horarios':doctors_page,'Usuarios':users_page,'Reportes':reports_page,'Reportes y respaldo':lambda:reports_page(True),'Administración':admin_page}[page]()
except Exception as exc: fail(exc)
