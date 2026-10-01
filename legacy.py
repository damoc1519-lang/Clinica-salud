"""Importación repetible de las tablas anteriores, sin borrarlas ni sobrescribirlas."""
from collections import Counter
import hashlib, json, re, unicodedata
from datetime import datetime, timedelta
from psycopg2 import sql
from psycopg2.extras import Json
from core import AppError, TZ, clean, normalize_doc, parse_date, parse_time, local_datetime, now, json_default

TABLES=['pacientes','disponibilidad','citas','historial']
def plain(text): return ''.join(c for c in unicodedata.normalize('NFD',clean(text).lower()) if unicodedata.category(c)!='Mn')
def parse_schedule(days,hours):
    names=['lunes','martes','miercoles','jueves','viernes','sabado','domingo']; value=plain(days)
    if ' a ' in value:
        ends=value.split(' a ')
        if len(ends)!=2 or ends[0] not in names or ends[1] not in names: raise ValueError('Días no reconocidos')
        first,last=map(names.index,ends)
        if first>last: raise ValueError('Intervalo de días ambiguo')
        weekdays=list(range(first,last+1))
    else:
        words=[v.strip() for v in re.split(r',|\s+y\s+',value) if v.strip()]
        if not words or any(w not in names for w in words): raise ValueError('Días no reconocidos')
        weekdays=[names.index(w) for w in words]
    match=re.fullmatch(r'\s*(\d{1,2}:\d{2})\s*[-–]\s*(\d{1,2}:\d{2})\s*',clean(hours))
    if not match: raise ValueError('Horario no reconocido')
    start,end=map(parse_time,match.groups())
    if start>=end: raise ValueError('Intervalo horario inválido')
    return weekdays,start,end

def source_rows(c):
    result={}
    for table in TABLES:
        c.execute('SELECT to_regclass(%s) AS t',('public.'+table,))
        if not c.fetchone()['t']: result[table]=[]; continue
        c.execute(sql.SQL('SELECT row_to_json(t) AS data FROM public.{} t').format(sql.Identifier(table)))
        result[table]=[r['data'] for r in c.fetchall()]
    return result

def preview(db,uid):
    with db.tx() as c:
        db.actor(c,uid,['admin']); rows=source_rows(c)
        c.execute('SELECT source_table,count(*) AS total,count(imported_id) AS importados FROM legacy_archive GROUP BY source_table'); archived=c.fetchall()
    return {k:len(v) for k,v in rows.items()},archived

def find_doctor(c,name,specialty='Sin especificar'):
    name=clean(name).split(' (')[0]
    if not name: raise ValueError('Falta identificar al médico')
    c.execute('SELECT id FROM doctors WHERE name=%s',(name,)); r=c.fetchone()
    if r: return r['id']
    c.execute('INSERT INTO doctors(name,specialties) VALUES(%s,%s) RETURNING id',(name,[clean(specialty) or 'Sin especificar'])); return c.fetchone()['id']

def find_patient(c,document):
    c.execute('SELECT id FROM patients WHERE document=%s',(normalize_doc(document),)); r=c.fetchone()
    if not r: raise ValueError('El paciente no está importado; revise su documento')
    return r['id']

def import_one(c,table,r):
    warning=None
    if table=='pacientes':
        doc=normalize_doc(r.get('cedula')); name=clean(r.get('nombre'))
        if not doc or not name: raise ValueError('Faltan documento o nombre')
        c.execute('SELECT id FROM patients WHERE document=%s',(doc,))
        if c.fetchone(): raise ValueError('El documento ya existe en la nueva versión; requiere revisión antes de combinar datos')
        birth=parse_date(r.get('fecha_nacimiento'))
        if birth and birth>now().date(): raise ValueError('Fecha de nacimiento futura')
        c.execute('INSERT INTO patients(document,name,sex,birth_date,address,phone,email,occupation,coverage,origin) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id',
                  (doc,name,r.get('sexo'),birth,r.get('domicilio'),r.get('telefono'),r.get('correo'),r.get('ocupacion'),r.get('prevision'),r.get('origen')))
        return 'patients',c.fetchone()['id'],warning
    if table=='disponibilidad':
        did=find_doctor(c,r.get('medico'),r.get('especialidad'))
        days,start,end=parse_schedule(r.get('dias'),r.get('horas'))
        for day in days:
            c.execute('INSERT INTO availability(doctor_id,weekday,start_time,end_time) VALUES(%s,%s,%s,%s) ON CONFLICT DO NOTHING',(did,day,start,end))
        return 'doctors',did,None
    if table=='citas':
        pid=find_patient(c,r.get('cedula_paciente')); did=find_doctor(c,r.get('medico'),r.get('especialidad'))
        start=local_datetime(r.get('fecha'),r.get('hora')); end=start+timedelta(minutes=30)
        states={'agendada':'Pendiente','reagendada':'Pendiente','pendiente':'Pendiente','confirmada':'Confirmada','llego':'Llegó','en atencion':'En atención','atendida':'Atendida','cancelada':'Cancelada','no asistio':'No asistió'}
        status=states.get(plain(r.get('estado')))
        if not status: raise ValueError('Estado de cita no reconocido')
        c.execute('INSERT INTO appointments(patient_id,doctor_id,specialty,start_at,end_at,status,authorization_code,expires_on,notes) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id',
                  (pid,did,clean(r.get('especialidad')) or 'Sin especificar',start,end,status,clean(r.get('autorizacion')),parse_date(r.get('vencimiento_issfa')),r.get('observaciones')))
        return 'appointments',c.fetchone()['id'],'Duración anterior no registrada: importada con 30 minutos; revisar.'
    if table=='historial':
        pid=find_patient(c,r.get('cedula_paciente')); author=clean(r.get('medico_atn'))
        c.execute('SELECT id,specialties FROM doctors WHERE name=%s',(author.split(' (')[0],)); d=c.fetchone()
        occurred=datetime.fromisoformat(str(r.get('fecha_atencion')))
        if occurred.tzinfo is None: occurred=occurred.replace(tzinfo=TZ)
        data={k:r.get(k) for k in ['antecedentes_pers','antecedentes_fam','habitos','motivo','enfermedad_actual','peso','talla','pa','fc','imc','diagnostico','tratamiento','examenes']}
        c.execute("INSERT INTO encounters(patient_id,doctor_id,status,consultation_type,data,occurred_at,finalized_at,legacy_author,specialty) VALUES(%s,%s,'Finalizada',%s,%s,%s,%s,%s,%s) RETURNING id",(pid,d['id'] if d else None,clean(r.get('tipo_consulta')) or 'C1',Json(data),occurred,occurred,author,d['specialties'][0] if d and len(d['specialties'])==1 else None))
        return 'encounters',c.fetchone()['id'],None
    raise ValueError('Tabla desconocida')

def import_legacy(db,uid):
    counts=Counter()
    with db.tx() as c:
        a=db.actor(c,uid,['admin']); c.execute('SELECT pg_advisory_xact_lock(861232)')
        rows=source_rows(c)
        for table,items in rows.items():
            seen=Counter()
            for r in items:
                base=str(r['id']) if r.get('id') is not None else hashlib.sha256(json.dumps(r,sort_keys=True,default=json_default).encode()).hexdigest()
                seen[base]+=1; key=base+':'+str(seen[base])
                c.execute('SELECT imported_id,data FROM legacy_archive WHERE source_table=%s AND source_key=%s',(table,key)); old=c.fetchone()
                if old and old['imported_id'] is not None: counts['ya_importados']+=1; continue
                if old and old['data']!=r:
                    db.audit(c,a,'revision_origen','legacy_archive',key,{'tabla':table,'anterior':old['data']})
                c.execute('INSERT INTO legacy_archive(source_table,source_key,data) VALUES(%s,%s,%s) ON CONFLICT(source_table,source_key) DO UPDATE SET data=EXCLUDED.data',(table,key,Json(r)))
                c.execute('SAVEPOINT legacy_row')
                try:
                    entity,target,warning=import_one(c,table,r)
                    c.execute('RELEASE SAVEPOINT legacy_row')
                    c.execute('UPDATE legacy_archive SET imported_entity=%s,imported_id=%s,issue=%s WHERE source_table=%s AND source_key=%s',(entity,target,warning,table,key)); counts['importados']+=1
                except Exception as exc:
                    c.execute('ROLLBACK TO SAVEPOINT legacy_row'); c.execute('RELEASE SAVEPOINT legacy_row')
                    if getattr(exc,'pgcode',None)=='23P01': message='La cita se superpone con otra; requiere reagendamiento en los datos de origen.'
                    else: message=str(exc).splitlines()[0][:350]
                    c.execute('UPDATE legacy_archive SET issue=%s WHERE source_table=%s AND source_key=%s',(message,table,key)); counts['por_revisar']+=1
        db.audit(c,a,'importar_anterior','legacy_archive',detail=dict(counts))
    return dict(counts)

def issues(db,uid):
    with db.tx() as c:
        db.actor(c,uid,['admin']); c.execute('SELECT source_table,source_key,imported_id,issue,data FROM legacy_archive WHERE issue IS NOT NULL ORDER BY source_table,source_key'); return c.fetchall()
