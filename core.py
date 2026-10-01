"""Reglas y acceso a datos de Medisuport. No depende de Streamlit."""
from __future__ import annotations
import os, re, json, hashlib, hmac, secrets, logging, io, zipfile, unicodedata
from pathlib import Path
from contextlib import contextmanager
from datetime import datetime, date, time, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo
import psycopg2
from psycopg2.pool import ThreadedConnectionPool
from psycopg2.extras import RealDictCursor, Json
from psycopg2 import sql

TZ = ZoneInfo('America/Guayaquil')
STATUSES = ['Pendiente','Confirmada','Llegó','En atención','Atendida','Cancelada','No asistió']
INACTIVE = ['Cancelada','No asistió']
WEEKDAYS = ['Lunes','Martes','Miércoles','Jueves','Viernes','Sábado','Domingo']
BACKUP_TABLES = ['settings','doctors','users','patients','agreements','patient_agreements','availability','blocks','appointments','encounters','amendments','audit','legacy_archive']
class AppError(Exception): pass

def now(): return datetime.now(TZ)
def json_default(v):
    if isinstance(v,(datetime,date,time)): return v.isoformat()
    if isinstance(v,Decimal): return float(v)
    raise TypeError(type(v).__name__)
def clean(v): return str(v or '').strip()
def proper_name(value):
    """Normaliza nombres personales conservando partículas comunes en español."""
    words=clean(value).lower().split()
    particles={'de','del','la','las','los','y','e'}
    return ' '.join((word.capitalize() if i==0 or word not in particles else word) for i,word in enumerate(words))
def normalize_doc(v): return re.sub(r'\s+', '', clean(v)).upper()
def password_hash(password):
    if len(password)<12: raise AppError('Use una contraseña de al menos 12 caracteres.')
    salt=secrets.token_hex(16)
    digest=hashlib.pbkdf2_hmac('sha256',password.encode(),salt.encode(),600000).hex()
    return f'pbkdf2_sha256$600000${salt}${digest}'
def password_ok(password,encoded):
    try:
        algorithm,iterations,salt,expected=encoded.split('$')
        if algorithm!='pbkdf2_sha256': return False
        actual=hashlib.pbkdf2_hmac('sha256',password.encode(),salt.encode(),int(iterations)).hex()
        return hmac.compare_digest(actual,expected)
    except (ValueError,TypeError,AttributeError): return False
DUMMY_HASH='pbkdf2_sha256$600000$dummy$'+'0'*64

def parse_date(value):
    if not value: return None
    if isinstance(value,datetime): return value.date()
    if isinstance(value,date): return value
    return date.fromisoformat(str(value)[:10])
def parse_time(value):
    if isinstance(value,time): return value
    return time.fromisoformat(str(value))
def local_datetime(day,hour): return datetime.combine(parse_date(day),parse_time(hour),TZ)
def overlaps(a,b,c,d): return a<d and c<b

def slots_for_day(day,rules,busy,blocks,duration,clock=None):
    clock=clock or now(); result=set()
    for rule in rules:
        if rule['weekday']!=day.weekday(): continue
        start=local_datetime(day,rule['start_time']); limit=local_datetime(day,rule['end_time'])
        while start+timedelta(minutes=duration)<=limit:
            end=start+timedelta(minutes=duration)
            if start>=clock and not any(overlaps(start,end,r['start_at'],r['end_at']) for r in busy+blocks):
                result.add(start)
            start+=timedelta(minutes=duration)
    return sorted(result)

def validate_patient(data):
    p={k:clean(data.get(k)) for k in ['document','name','sex','address','phone','email','occupation','coverage','origin']}
    p['document']=normalize_doc(p['document'])
    p['name']=proper_name(p['name'])
    if not p['document'] or len(p['document'])>30: raise AppError('Ingrese un documento de 1 a 30 caracteres.')
    if len(p['name'])<3: raise AppError('Ingrese el nombre completo.')
    if p['email'] and not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+',p['email']): raise AppError('Revise el correo electrónico.')
    if p['phone'] and not re.fullmatch(r'[+0-9 ()-]{6,25}',p['phone']): raise AppError('Revise el teléfono.')
    p['birth_date']=parse_date(data.get('birth_date'))
    if p['birth_date'] and not date(1900,1,1)<=p['birth_date']<=now().date(): raise AppError('Revise la fecha de nacimiento.')
    return p

def clinical_data(data,final=False):
    text_keys=['motivo','antecedentes_pers','antecedentes_fam','personal_details','family_details','habitos','alergias','enfermedad_actual','pa','systems_details','physical_details',
               'diagnostico','tratamiento','examenes','interconsult_specialty','interconsult_reason','clinical_summary','exam_results','therapeutic_plan',
               'referral_type','referral_destination','referral_service','referral_specialty','referral_summary','referral_findings','lab_treatment',
               'other_lab_tests','imaging_description','imaging_reason','prescription','prescription_warnings']
    list_keys=['personal_conditions','family_conditions','systems_review','physical_regional','physical_systemic','diagnoses','referral_reasons','lab_tests','imaging_types']
    result={k:clean(data.get(k)) for k in text_keys}
    for key in list_keys: result[key]=data.get(key) if isinstance(data.get(key),list) else []
    for key,maximum in [('temperatura',50),('fc',350),('fr',100),('peso',500),('talla',280),('perimetro_abdominal',300),('hemoglobina_capilar',30),('glucosa_capilar',1000),('spo2',100)]:
        raw=data.get(key)
        if raw in ('',None,0,0.0): result[key]=None; continue
        try: value=float(raw)
        except (ValueError,TypeError): raise AppError(f'Revise el valor de {key}.')
        if not 0<value<=maximum: raise AppError(f'Revise el valor de {key}.')
        result[key]=value
    fum=parse_date(data.get('fum')); result['fum']=fum.isoformat() if fum else None
    result['contaminado']=bool(data.get('contaminado')); result['sedacion']=bool(data.get('sedacion'))
    result['imc']=round(result['peso']/(result['talla']/100)**2,2) if result['peso'] and result['talla'] else None
    if final and (not result['motivo'] or not result['diagnostico']): raise AppError('Complete motivo y diagnóstico antes de finalizar.')
    return result

def load_config():
    try: import tomllib
    except ImportError: import tomli as tomllib
    path=Path(__file__).parent/'.streamlit/secrets.toml'
    cfg=tomllib.loads(path.read_text()) if path.exists() else {}
    def setting(k,default=None): return os.environ.get(k,cfg.get(k,default))
    if not setting('DB_PASSWORD'): raise AppError('Falta DB_PASSWORD en .streamlit/secrets.toml.')
    return dict(host=setting('DB_HOST','aws-0-us-west-2.pooler.supabase.com'),port=int(setting('DB_PORT',5432)),
                dbname=setting('DB_NAME','postgres'),user=setting('DB_USER','postgres.vktnksyxgtgphohpjmke'),
                password=setting('DB_PASSWORD'),sslmode=setting('DB_SSLMODE','require'),connect_timeout=15,
                options='-c search_path=medisuport,public,extensions -c timezone=America/Guayaquil -c statement_timeout=20000')

class Database:
    def __init__(self,config=None):
        self.config=config or load_config()
        self.pool=ThreadedConnectionPool(1,8,**self.config)
    @contextmanager
    def tx(self):
        conn=self.pool.getconn()
        try:
            if conn.closed:
                self.pool.putconn(conn,close=True); conn=self.pool.getconn()
            conn.rollback()
            with conn.cursor() as check: check.execute('SELECT 1')
        except (psycopg2.InterfaceError,psycopg2.OperationalError):
            self.pool.putconn(conn,close=True); conn=self.pool.getconn()
        try:
            with conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur: yield cur
        finally: self.pool.putconn(conn,close=bool(conn.closed))
    def initialize(self):
        with self.tx() as c:
            c.execute('SELECT pg_advisory_xact_lock(861230)')
            c.execute((Path(__file__).parent/'schema.sql').read_text())
    def ready(self):
        with self.tx() as c:
            c.execute("SELECT to_regclass('medisuport.users') AS t")
            if not c.fetchone()['t']: return False
            c.execute('SELECT EXISTS(SELECT 1 FROM users WHERE role=\'admin\' AND active) AS ok')
            return c.fetchone()['ok']
    def actor(self,c,user_id,roles=None):
        c.execute('SELECT * FROM users WHERE id=%s AND active',(user_id,)); a=c.fetchone()
        if not a: raise AppError('La sesión ya no está autorizada. Ingrese nuevamente.')
        if roles and a['role'] not in roles: raise AppError('Su perfil no permite realizar esta acción.')
        if a['role']=='medico':
            c.execute('SELECT active FROM doctors WHERE id=%s',(a['doctor_id'],))
            if not c.fetchone()['active']: raise AppError('El médico está desactivado.')
        return a
    def audit(self,c,a,action,entity,entity_id=None,detail=None):
        c.execute('INSERT INTO audit(actor_id,action,entity,entity_id,detail) VALUES(%s,%s,%s,%s,%s)',
                  (a['id'] if a else None,action,entity,str(entity_id) if entity_id is not None else None,Json(detail or {},dumps=lambda x:json.dumps(x,default=json_default))))
    def bootstrap(self,username,name,password):
        username=clean(username).lower()
        if not re.fullmatch(r'[a-z0-9_.@-]{3,80}',username): raise AppError('Usuario: de 3 a 80 letras, números, punto o guion.')
        encoded=password_hash(password)
        with self.tx() as c:
            c.execute('SELECT pg_advisory_xact_lock(861230)')
            c.execute('SELECT COUNT(*) AS n FROM users')
            if c.fetchone()['n']: raise AppError('Ya existen usuarios. El alta inicial está cerrada.')
            c.execute("INSERT INTO users(username,name,password_hash,role,must_change) VALUES(%s,%s,%s,'admin',FALSE)",(username,proper_name(name),encoded))
            self.audit(c,None,'alta_inicial','users')
    def login(self,username,password):
        username=clean(username).lower(); result=None
        with self.tx() as c:
            c.execute('SELECT pg_advisory_xact_lock(hashtext(%s))',('login:'+username,))
            c.execute("SELECT count(*) AS n FROM login_attempts WHERE username=%s AND NOT success AND attempted_at>now()-interval '15 minutes'",(username,))
            if c.fetchone()['n']>=5: raise AppError('Demasiados intentos. Espere 15 minutos antes de volver a intentar.')
            c.execute('SELECT * FROM users WHERE username=%s AND active',(username,)); a=c.fetchone()
            valid=password_ok(password,a['password_hash'] if a else DUMMY_HASH)
            if valid and a:
                if a['role']=='medico':
                    c.execute('SELECT active FROM doctors WHERE id=%s',(a['doctor_id'],)); valid=c.fetchone()['active']
                if valid: result={k:a[k] for k in ['id','name','role','doctor_id','auth_version','must_change']}
            c.execute('INSERT INTO login_attempts(username,success) VALUES(%s,%s)',(username,bool(result)))
            if result:
                c.execute('DELETE FROM login_attempts WHERE username=%s AND NOT success',(username,))
                self.audit(c,a,'ingreso','users',a['id'])
        if not result: raise AppError('Usuario o contraseña incorrectos.')
        return result
    def session_user(self,user_id,auth_version):
        with self.tx() as c:
            a=self.actor(c,user_id)
            if a['auth_version']!=auth_version: raise AppError('La cuenta cambió. Ingrese nuevamente.')
            return {k:v for k,v in a.items() if k!='password_hash'}
    def change_password(self,uid,current,new):
        encoded=password_hash(new)
        with self.tx() as c:
            a=self.actor(c,uid)
            if not password_ok(current,a['password_hash']): raise AppError('La contraseña actual no coincide.')
            if password_ok(new,a['password_hash']): raise AppError('Elija una contraseña diferente.')
            c.execute('UPDATE users SET password_hash=%s,must_change=FALSE,auth_version=auth_version+1 WHERE id=%s',(encoded,uid))
            self.audit(c,a,'cambio_clave','users',uid)
    def users(self,uid,query='',include_inactive=True):
        with self.tx() as c:
            self.actor(c,uid,['admin']); q='%'+clean(query)+'%'
            c.execute('SELECT id,username,name,role,doctor_id,active FROM users WHERE (%s OR active) AND (name ILIKE %s OR username ILIKE %s) ORDER BY active DESC,name',(include_inactive,q,q)); return c.fetchall()
    def save_user(self,uid,data,target=None,temp_password=None):
        with self.tx() as c:
            a=self.actor(c,uid,['admin']); c.execute('SELECT pg_advisory_xact_lock(861231)')
            username=clean(data['username']).lower(); role=data['role']; doctor=data.get('doctor_id') if role=='medico' else None
            display_name=proper_name(data['name'])
            if not re.fullmatch(r'[a-z0-9_.@-]{3,80}',username) or not clean(data['name']): raise AppError('Revise usuario y nombre.')
            if role=='medico' and not doctor: raise AppError('Seleccione el médico de la cuenta.')
            if target==uid and (not data['active'] or role!='admin'): raise AppError('No puede desactivar o quitar su propio rol administrador.')
            if target:
                c.execute('SELECT role,active FROM users WHERE id=%s FOR UPDATE',(target,)); previous=c.fetchone()
                if not previous: raise AppError('La cuenta ya no existe.')
                if previous['role']=='admin' and previous['active'] and (role!='admin' or not data['active']):
                    c.execute("SELECT count(*) AS n FROM users WHERE role='admin' AND active")
                    if c.fetchone()['n']<=1: raise AppError('Debe conservar al menos una cuenta administradora activa.')
                c.execute('UPDATE users SET username=%s,name=%s,role=%s,doctor_id=%s,active=%s,auth_version=auth_version+1 WHERE id=%s',
                    (username,display_name,role,doctor,data['active'],target))
            else:
                if not temp_password: raise AppError('Ingrese una contraseña temporal individual.')
                c.execute('INSERT INTO users(username,name,role,doctor_id,active,password_hash) VALUES(%s,%s,%s,%s,%s,%s) RETURNING id',
                    (username,display_name,role,doctor,data['active'],password_hash(temp_password))); target=c.fetchone()['id']
            if temp_password:
                c.execute('UPDATE users SET password_hash=%s,must_change=TRUE,auth_version=auth_version+1 WHERE id=%s',(password_hash(temp_password),target))
                c.execute('DELETE FROM login_attempts WHERE username=%s',(username,))
            self.audit(c,a,'actualizar_usuario','users',target)
    def delete_user(self,uid,target):
        with self.tx() as c:
            a=self.actor(c,uid,['admin'])
            if target==uid: raise AppError('No puede eliminar su propia cuenta.')
            c.execute('SELECT * FROM users WHERE id=%s FOR UPDATE',(target,)); user=c.fetchone()
            if not user: raise AppError('La cuenta ya no existe.')
            if user['role']=='admin' and user['active']:
                c.execute("SELECT count(*) AS n FROM users WHERE role='admin' AND active")
                if c.fetchone()['n']<=1: raise AppError('Debe conservar al menos una cuenta administradora activa.')
            c.execute('''SELECT EXISTS(SELECT 1 FROM audit WHERE actor_id=%s) OR EXISTS(SELECT 1 FROM encounters WHERE author_id=%s)
                         OR EXISTS(SELECT 1 FROM amendments WHERE author_id=%s) AS used''',(target,target,target)); used=c.fetchone()['used']
            if used:
                c.execute("UPDATE users SET active=FALSE,username=%s,doctor_id=NULL,auth_version=auth_version+1 WHERE id=%s",(f"eliminado_{target}_{int(now().timestamp())}",target))
                self.audit(c,a,'desactivar_usuario_con_historial','users',target); return 'Cuenta retirada. Se conservó su autoría clínica y auditoría.'
            c.execute('DELETE FROM login_attempts WHERE username=%s',(user['username'],)); c.execute('DELETE FROM users WHERE id=%s',(target,)); self.audit(c,a,'eliminar_usuario','users',target); return 'Cuenta eliminada definitivamente.'
    def doctors(self,uid,all_rows=False):
        with self.tx() as c:
            self.actor(c,uid); c.execute('SELECT * FROM doctors WHERE (%s OR active) ORDER BY name',(all_rows,)); return c.fetchall()
    def save_doctor(self,uid,data,target=None,version=None):
        name=proper_name(data['name']); specialties=[clean(x).capitalize() for x in data['specialties'] if clean(x)]
        if not name or not specialties: raise AppError('Complete nombre y especialidades.')
        with self.tx() as c:
            a=self.actor(c,uid,['admin'])
            if target:
                c.execute('SELECT id FROM doctors WHERE id=%s FOR UPDATE',(target,))
                if not data['active']:
                    c.execute("SELECT count(*) AS n FROM appointments WHERE doctor_id=%s AND start_at>=now() AND status NOT IN ('Cancelada','No asistió','Atendida')",(target,))
                    if c.fetchone()['n']: raise AppError('Reagende o cancele las citas futuras antes de desactivar al médico.')
                c.execute('UPDATE doctors SET name=%s,specialties=%s,slot_minutes=%s,professional_id=%s,registration=%s,active=%s,version=version+1 WHERE id=%s AND version=%s RETURNING id',
                          (name,specialties,data['slot_minutes'],clean(data.get('professional_id')),clean(data.get('registration')),data['active'],target,version))
                if not c.fetchone(): raise AppError('El médico cambió en otra sesión. Actualice la pantalla.')
            else:
                c.execute('INSERT INTO doctors(name,specialties,slot_minutes,professional_id,registration) VALUES(%s,%s,%s,%s,%s) RETURNING id',(name,specialties,data['slot_minutes'],clean(data.get('professional_id')),clean(data.get('registration')))); target=c.fetchone()['id']
            self.audit(c,a,'guardar_medico','doctors',target)
    def update_my_professional(self,uid,professional_id,registration):
        with self.tx() as c:
            a=self.actor(c,uid,['medico'])
            if not clean(professional_id) or not clean(registration): raise AppError('Complete documento de identificación y registro profesional.')
            c.execute('UPDATE doctors SET professional_id=%s,registration=%s,version=version+1 WHERE id=%s',(clean(professional_id),clean(registration),a['doctor_id']))
            self.audit(c,a,'actualizar_perfil_profesional','doctors',a['doctor_id'])
    def patient_scope(self,c,a,pid,clinical=False):
        if clinical and a['role']=='secretaria': raise AppError('El historial clínico requiere un perfil médico o administrador.')
        if a['role']=='medico':
            c.execute("SELECT EXISTS(SELECT 1 FROM appointments WHERE patient_id=%s AND doctor_id=%s AND status<>'Cancelada') OR EXISTS(SELECT 1 FROM encounters WHERE patient_id=%s AND doctor_id=%s) AS ok",(pid,a['doctor_id'],pid,a['doctor_id']))
            if not c.fetchone()['ok']: raise AppError('El paciente no está asignado a este médico.')
    def patients(self,uid,query='',archived=False,limit=100):
        with self.tx() as c:
            a=self.actor(c,uid)
            where=''; args=[archived]+['%'+clean(query)+'%']*3
            if a['role']=='medico':
                where=" AND (EXISTS(SELECT 1 FROM appointments x WHERE x.patient_id=p.id AND x.doctor_id=%s AND x.status<>'Cancelada') OR EXISTS(SELECT 1 FROM encounters e WHERE e.patient_id=p.id AND e.doctor_id=%s))"; args += [a['doctor_id']]*2
            c.execute('SELECT p.* FROM patients p WHERE (%s OR p.active) AND (p.name ILIKE %s OR p.document ILIKE %s OR p.phone ILIKE %s)'+where+' ORDER BY p.name LIMIT %s',args+[limit]); return c.fetchall()
    def get_patient(self,uid,pid,clinical=False):
        with self.tx() as c:
            a=self.actor(c,uid); self.patient_scope(c,a,pid,clinical)
            c.execute('SELECT * FROM patients WHERE id=%s',(pid,)); return c.fetchone()
    def save_patient(self,uid,data,pid=None,version=None):
        p=validate_patient(data); keys=list(p)
        with self.tx() as c:
            a=self.actor(c,uid,['admin','secretaria'])
            if pid:
                c.execute(sql.SQL('UPDATE patients SET {} ,version=version+1,updated_at=now() WHERE id=%s AND version=%s RETURNING id').format(sql.SQL(',').join(sql.SQL('{}=%s').format(sql.Identifier(k)) for k in keys)),list(p.values())+[pid,version])
                if not c.fetchone(): raise AppError('Otro usuario actualizó la ficha. Recargue antes de guardar.')
            else:
                c.execute(sql.SQL('INSERT INTO patients ({}) VALUES ({}) RETURNING id').format(sql.SQL(',').join(map(sql.Identifier,keys)),sql.SQL(',').join(sql.Placeholder()*len(keys))),list(p.values())); pid=c.fetchone()['id']
            self.audit(c,a,'editar_paciente' if version else 'registrar_paciente','patients',pid,{'campos':keys})
            return pid
    def agreements(self,uid,active_only=False):
        with self.tx() as c:
            self.actor(c,uid)
            c.execute('''SELECT a.*,count(pa.patient_id) FILTER (WHERE pa.active) AS patient_count
                         FROM agreements a LEFT JOIN patient_agreements pa ON pa.agreement_id=a.id
                         WHERE (%s=FALSE OR a.active) GROUP BY a.id ORDER BY a.name''',(active_only,))
            return c.fetchall()
    def save_agreement(self,uid,data,target=None,version=None):
        name=proper_name(data.get('name')); code=clean(data.get('code')).upper(); email=clean(data.get('email')).lower()
        start=parse_date(data.get('start_date')); end=parse_date(data.get('end_date'))
        if len(name)<2: raise AppError('Ingrese el nombre del convenio.')
        if email and not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+',email): raise AppError('Revise el correo del convenio.')
        if start and end and end<start: raise AppError('La fecha final no puede ser anterior a la inicial.')
        values=(name,code,clean(data.get('tax_id')),proper_name(data.get('contact_name')),clean(data.get('phone')),email,start,end,clean(data.get('notes')),bool(data.get('requires_validation_date')),bool(data.get('active',True)))
        with self.tx() as c:
            a=self.actor(c,uid,['admin'])
            if target:
                c.execute('''UPDATE agreements SET name=%s,code=%s,tax_id=%s,contact_name=%s,phone=%s,email=%s,
                             start_date=%s,end_date=%s,notes=%s,requires_validation_date=%s,active=%s,version=version+1,updated_at=now()
                             WHERE id=%s AND version=%s RETURNING id''',values+(target,version))
                if not c.fetchone(): raise AppError('El convenio cambió en otra sesión. Actualice la pantalla.')
            else:
                c.execute('''INSERT INTO agreements(name,code,tax_id,contact_name,phone,email,start_date,end_date,notes,requires_validation_date,active)
                             VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id''',values); target=c.fetchone()['id']
            self.audit(c,a,'guardar_convenio','agreements',target)
            return target
    def delete_agreement(self,uid,target):
        with self.tx() as c:
            a=self.actor(c,uid,['admin']); c.execute('SELECT * FROM agreements WHERE id=%s FOR UPDATE',(target,)); agreement=c.fetchone()
            if not agreement: raise AppError('El convenio ya no existe.')
            c.execute('SELECT EXISTS(SELECT 1 FROM patient_agreements WHERE agreement_id=%s) OR EXISTS(SELECT 1 FROM appointments WHERE agreement_id=%s) AS used',(target,target)); used=c.fetchone()['used']
            if used:
                c.execute('UPDATE agreements SET active=FALSE,version=version+1,updated_at=now() WHERE id=%s',(target,)); self.audit(c,a,'archivar_convenio','agreements',target); return 'Convenio archivado porque tiene pacientes o citas relacionadas.'
            c.execute('DELETE FROM agreements WHERE id=%s',(target,)); self.audit(c,a,'eliminar_convenio','agreements',target); return 'Convenio eliminado definitivamente.'
    def patient_agreements(self,uid,pid,active_only=True):
        with self.tx() as c:
            a=self.actor(c,uid); self.patient_scope(c,a,pid)
            c.execute('''SELECT a.*,pa.member_number FROM patient_agreements pa JOIN agreements a ON a.id=pa.agreement_id
                         WHERE pa.patient_id=%s AND (%s=FALSE OR (pa.active AND a.active)) ORDER BY a.name''',(pid,active_only))
            return c.fetchall()
    def import_patients(self,uid,agreement_id,rows):
        if not rows: raise AppError('El archivo no contiene pacientes válidos para importar.')
        prepared=[]
        for item in rows:
            p=validate_patient(item); prepared.append((p,clean(item.get('member_number'))))
        results=[]
        with self.tx() as c:
            a=self.actor(c,uid,['admin','secretaria'])
            c.execute('SELECT * FROM agreements WHERE id=%s AND active FOR UPDATE',(agreement_id,)); agreement=c.fetchone()
            if not agreement: raise AppError('El convenio no existe o está inactivo.')
            for p,member in prepared:
                c.execute('SELECT id FROM patients WHERE document=%s FOR UPDATE',(p['document'],)); found=c.fetchone()
                if found:
                    pid=found['id']; status='Paciente existente vinculado'
                else:
                    keys=list(p); c.execute(sql.SQL('INSERT INTO patients ({}) VALUES ({}) RETURNING id').format(sql.SQL(',').join(map(sql.Identifier,keys)),sql.SQL(',').join(sql.Placeholder()*len(keys))),list(p.values())); pid=c.fetchone()['id']; status='Paciente registrado'
                c.execute('''INSERT INTO patient_agreements(patient_id,agreement_id,member_number,active) VALUES(%s,%s,%s,TRUE)
                             ON CONFLICT(patient_id,agreement_id) DO UPDATE SET member_number=EXCLUDED.member_number,active=TRUE''',(pid,agreement_id,member))
                results.append({'Documento':p['document'],'Paciente':p['name'],'Resultado':status})
            self.audit(c,a,'importar_pacientes','agreements',agreement_id,{'cantidad':len(results)})
        return results
    def archive_patient(self,uid,pid,reason,active=False):
        if not clean(reason): raise AppError('Escriba el motivo.')
        with self.tx() as c:
            a=self.actor(c,uid,['admin','secretaria']); c.execute('SELECT id FROM patients WHERE id=%s FOR UPDATE',(pid,))
            if not active:
                c.execute("SELECT COUNT(*) AS n FROM appointments WHERE patient_id=%s AND start_at>=now() AND status NOT IN ('Cancelada','No asistió','Atendida')",(pid,))
                if c.fetchone()['n']: raise AppError('Reagende o cancele las citas futuras antes de archivar.')
            c.execute('UPDATE patients SET active=%s,archive_reason=%s,version=version+1,updated_at=now() WHERE id=%s',(active,reason,pid))
            self.audit(c,a,'reactivar' if active else 'archivar','patients',pid,{'motivo':reason})
    def schedules(self,uid,did):
        with self.tx() as c:
            self.actor(c,uid); c.execute('SELECT * FROM availability WHERE doctor_id=%s ORDER BY weekday,start_time',(did,)); rules=c.fetchall()
            c.execute('SELECT * FROM blocks WHERE doctor_id=%s AND end_at>=now() ORDER BY start_at',(did,)); return rules,c.fetchall()
    def add_schedule(self,uid,did,days,start,end):
        if not days or end<=start: raise AppError('Seleccione días y un intervalo de horas válido.')
        with self.tx() as c:
            a=self.actor(c,uid,['admin','secretaria']); c.execute('SELECT id FROM doctors WHERE id=%s FOR UPDATE',(did,))
            for day in days:
                c.execute('SELECT id FROM availability WHERE doctor_id=%s AND weekday=%s AND start_time<%s AND end_time>%s',(did,day,end,start))
                if c.fetchone(): raise AppError('Ese intervalo se cruza con un horario ya registrado.')
                c.execute('INSERT INTO availability(doctor_id,weekday,start_time,end_time) VALUES(%s,%s,%s,%s)',(did,day,start,end))
            self.audit(c,a,'agregar_horario','doctors',did)
    def remove_schedule(self,uid,sid):
        with self.tx() as c:
            a=self.actor(c,uid,['admin','secretaria']); c.execute('SELECT * FROM availability WHERE id=%s',(sid,)); row=c.fetchone()
            if not row: raise AppError('El horario ya no existe.')
            c.execute('SELECT id FROM doctors WHERE id=%s FOR UPDATE',(row['doctor_id'],))
            c.execute('DELETE FROM availability WHERE id=%s',(sid,))
            c.execute("SELECT start_at,end_at FROM appointments WHERE doctor_id=%s AND start_at>=now() AND status NOT IN ('Cancelada','No asistió','Atendida')",(row['doctor_id'],)); pending=c.fetchall()
            c.execute('SELECT * FROM availability WHERE doctor_id=%s',(row['doctor_id'],)); rules=c.fetchall()
            for r in pending:
                s=r['start_at'].astimezone(TZ); e=r['end_at'].astimezone(TZ)
                if not any(x['weekday']==s.weekday() and x['start_time']<=s.time() and x['end_time']>=e.time() for x in rules): raise AppError('Hay citas futuras que quedarían fuera de horario. Reagéndelas primero.')
            self.audit(c,a,'retirar_horario','availability',sid)
    def add_block(self,uid,did,start,end,reason):
        if end<=start or not clean(reason): raise AppError('Revise el intervalo y el motivo del bloqueo.')
        with self.tx() as c:
            a=self.actor(c,uid,['admin','secretaria']); c.execute('SELECT id FROM doctors WHERE id=%s FOR UPDATE',(did,))
            c.execute("SELECT id FROM appointments WHERE doctor_id=%s AND status NOT IN ('Cancelada','No asistió') AND start_at<%s AND end_at>%s",(did,end,start))
            if c.fetchone(): raise AppError('Hay citas dentro del bloqueo. Reagéndelas o cancélelas primero.')
            c.execute('INSERT INTO blocks(doctor_id,start_at,end_at,reason) VALUES(%s,%s,%s,%s) RETURNING id',(did,start,end,reason)); bid=c.fetchone()['id']; self.audit(c,a,'bloquear_horario','blocks',bid)
    def remove_block(self,uid,bid):
        with self.tx() as c:
            a=self.actor(c,uid,['admin','secretaria']); c.execute('DELETE FROM blocks WHERE id=%s',(bid,)); self.audit(c,a,'retirar_bloqueo','blocks',bid)
    def available_slots(self,uid,did,pid,day,duration,exclude=None):
        with self.tx() as c:
            self.actor(c,uid,['admin','secretaria']); c.execute('SELECT * FROM availability WHERE doctor_id=%s',(did,)); rules=c.fetchall()
            start=local_datetime(day,time.min); end=start+timedelta(days=1)
            c.execute("SELECT start_at,end_at FROM appointments WHERE (doctor_id=%s OR patient_id=%s) AND status NOT IN ('Cancelada','No asistió') AND start_at<%s AND end_at>%s AND (%s IS NULL OR id<>%s)",(did,pid,end,start,exclude,exclude)); busy=c.fetchall()
            c.execute('SELECT start_at,end_at FROM blocks WHERE doctor_id=%s AND start_at<%s AND end_at>%s',(did,end,start)); blocks=c.fetchall()
        return slots_for_day(day,rules,busy,blocks,duration)
    def appointments(self,uid,first,last,status=None):
        with self.tx() as c:
            a=self.actor(c,uid); args=[local_datetime(first,time.min),local_datetime(last+timedelta(days=1),time.min)]
            more=''
            if a['role']=='medico': more+=' AND x.doctor_id=%s'; args.append(a['doctor_id'])
            if status: more+=' AND x.status=%s'; args.append(status)
            c.execute('SELECT x.*,p.name AS patient,p.document,p.phone,d.name AS doctor,a.name AS agreement FROM appointments x JOIN patients p ON p.id=x.patient_id JOIN doctors d ON d.id=x.doctor_id LEFT JOIN agreements a ON a.id=x.agreement_id WHERE x.start_at>=%s AND x.start_at<%s'+more+' ORDER BY x.start_at',args); return c.fetchall()
    def book(self,uid,pid,did,specialty,start,duration,agreement_id=None,validation_date=None,notes='',aid=None,version=None):
        end=start+timedelta(minutes=int(duration))
        if start<now() or not 5<=duration<=240 or start.date()!=end.date(): raise AppError('Elija un horario futuro y una duración de 5 a 240 minutos.')
        with self.tx() as c:
            a=self.actor(c,uid,['admin','secretaria'])
            c.execute('SELECT * FROM doctors WHERE id=%s FOR UPDATE',(did,)); d=c.fetchone()
            c.execute('SELECT * FROM patients WHERE id=%s FOR UPDATE',(pid,)); p=c.fetchone()
            if not p or not p['active'] or not d or not d['active']: raise AppError('El paciente o el médico están inactivos.')
            if specialty not in d['specialties']: raise AppError('La especialidad no corresponde al médico.')
            agreement=None
            if agreement_id:
                c.execute('SELECT * FROM agreements WHERE id=%s AND active',(agreement_id,)); agreement=c.fetchone()
                if not agreement: raise AppError('El convenio seleccionado no existe o está inactivo.')
                c.execute('''INSERT INTO patient_agreements(patient_id,agreement_id,active) VALUES(%s,%s,TRUE)
                             ON CONFLICT(patient_id,agreement_id) DO UPDATE SET active=TRUE''',(pid,agreement_id))
            if agreement and agreement['requires_validation_date'] and not validation_date: raise AppError('Ingrese la fecha de validación del convenio.')
            if not agreement: validation_date=None
            c.execute('SELECT * FROM availability WHERE doctor_id=%s',(did,)); rules=c.fetchall()
            if not any(r['weekday']==start.weekday() and r['start_time']<=start.time().replace(tzinfo=None) and r['end_time']>=end.time().replace(tzinfo=None) for r in rules): raise AppError('La cita está fuera del horario del médico.')
            c.execute('SELECT id FROM blocks WHERE doctor_id=%s AND start_at<%s AND end_at>%s',(did,end,start))
            if c.fetchone(): raise AppError('El médico tiene un bloqueo en ese intervalo.')
            if aid:
                c.execute('SELECT * FROM appointments WHERE id=%s FOR UPDATE',(aid,)); old=c.fetchone()
                if not old or old['version']!=version: raise AppError('La cita cambió en otra sesión. Actualice la pantalla.')
                if old['status'] not in ('Pendiente','Confirmada','Llegó'): raise AppError('Esta cita ya no permite reagendamiento.')
                c.execute("UPDATE appointments SET doctor_id=%s,specialty=%s,start_at=%s,end_at=%s,agreement_id=%s,validation_date=%s,authorization_code='',expires_on=NULL,notes=%s,status='Pendiente',version=version+1 WHERE id=%s",(did,specialty,start,end,agreement_id,validation_date,notes,aid))
                self.audit(c,a,'reagendar','appointments',aid,{'anterior':old['start_at'],'nuevo':start})
            else:
                c.execute("INSERT INTO appointments(patient_id,doctor_id,specialty,start_at,end_at,agreement_id,validation_date,authorization_code,expires_on,notes) VALUES(%s,%s,%s,%s,%s,%s,%s,'',NULL,%s) RETURNING id",(pid,did,specialty,start,end,agreement_id,validation_date,notes)); aid=c.fetchone()['id']; self.audit(c,a,'agendar','appointments',aid)
            return aid
    def appointment(self,c,a,aid):
        c.execute('SELECT * FROM appointments WHERE id=%s FOR UPDATE',(aid,)); r=c.fetchone()
        if not r or (a['role']=='medico' and r['doctor_id']!=a['doctor_id']): raise AppError('La cita no está disponible para este usuario.')
        return r
    def change_status(self,uid,aid,status,reason,version):
        transitions={'Pendiente':['Confirmada','Llegó','Cancelada','No asistió'],'Confirmada':['Llegó','Cancelada','No asistió'],'Llegó':['Cancelada','No asistió'],'En atención':[],'Atendida':[],'Cancelada':[],'No asistió':[]}
        with self.tx() as c:
            a=self.actor(c,uid,['admin','secretaria']); old=self.appointment(c,a,aid)
            if old['version']!=version: raise AppError('La cita cambió en otra sesión. Actualice la pantalla.')
            if status not in transitions[old['status']]: raise AppError('Ese cambio de estado no está permitido.')
            if status in ('Cancelada','No asistió') and not clean(reason): raise AppError('Escriba el motivo.')
            if status=='No asistió' and old['start_at']>now(): raise AppError('La hora de la cita todavía no llega.')
            c.execute('UPDATE appointments SET status=%s,cancel_reason=%s,version=version+1 WHERE id=%s',(status,reason,aid)); self.audit(c,a,'estado_cita','appointments',aid,{'anterior':old['status'],'nuevo':status,'motivo':reason})
    def start_encounter(self,uid,aid):
        with self.tx() as c:
            a=self.actor(c,uid,['medico']); ap=self.appointment(c,a,aid)
            c.execute('SELECT id FROM encounters WHERE appointment_id=%s',(aid,)); row=c.fetchone()
            if row: return row['id']
            if ap['status'] not in ('Llegó','En atención'): raise AppError('Recepción debe marcar que el paciente llegó.')
            c.execute('SELECT value FROM settings WHERE key=\'consultation_rule\''); rule=c.fetchone()['value']
            filt=' AND specialty=%s' if rule=='specialty' else ''; params=[ap['patient_id']]+([ap['specialty']] if filt else [])
            c.execute("SELECT COUNT(*) AS n FROM encounters WHERE patient_id=%s AND status='Finalizada'"+filt,params); typ='SUB' if c.fetchone()['n'] else 'C1'
            c.execute("INSERT INTO encounters(patient_id,doctor_id,appointment_id,author_id,specialty,status,consultation_type) VALUES(%s,%s,%s,%s,%s,'Borrador',%s) RETURNING id",(ap['patient_id'],a['doctor_id'],aid,uid,ap['specialty'],typ)); eid=c.fetchone()['id']
            c.execute("UPDATE appointments SET status='En atención',version=version+1 WHERE id=%s",(aid,)); self.audit(c,a,'abrir_consulta','encounters',eid); return eid
    def encounter(self,uid,eid):
        with self.tx() as c:
            a=self.actor(c,uid,['admin','medico']); c.execute('SELECT * FROM encounters WHERE id=%s',(eid,)); r=c.fetchone()
            if not r: raise AppError('La consulta no existe.')
            self.patient_scope(c,a,r['patient_id'],True)
            if r['status']=='Borrador' and a['role']=='medico' and r['author_id']!=uid: raise AppError('El borrador pertenece a otro médico.')
            c.execute("SELECT data FROM encounters WHERE patient_id=%s AND id<>%s AND status='Finalizada' ORDER BY occurred_at DESC LIMIT 1",(r['patient_id'],eid)); previous=c.fetchone(); r['previous_data']=previous['data'] if previous else {}
            return r
    def save_encounter(self,uid,eid,data,version,final=False):
        data=clinical_data(data,final)
        with self.tx() as c:
            a=self.actor(c,uid,['medico']); c.execute('SELECT * FROM encounters WHERE id=%s FOR UPDATE',(eid,)); old=c.fetchone()
            if not old or old['author_id']!=uid or old['status']!='Borrador': raise AppError('Solo el autor puede guardar su borrador.')
            if old['version']!=version: raise AppError('El borrador cambió en otra ventana. Recargue antes de guardar.')
            c.execute("UPDATE encounters SET data=%s,status=%s,version=version+1,finalized_at=CASE WHEN %s THEN now() ELSE NULL END WHERE id=%s",(Json(data),'Finalizada' if final else 'Borrador',final,eid))
            if final: c.execute("UPDATE appointments SET status='Atendida',version=version+1 WHERE id=%s",(old['appointment_id'],))
            self.audit(c,a,'finalizar_consulta' if final else 'guardar_borrador','encounters',eid)
    def histories(self,uid,pid):
        with self.tx() as c:
            a=self.actor(c,uid,['admin','medico']); self.patient_scope(c,a,pid,True)
            c.execute("SELECT e.*,COALESCE(d.name,e.legacy_author,'Sin asignar') AS doctor,d.professional_id,d.registration FROM encounters e LEFT JOIN doctors d ON d.id=e.doctor_id WHERE e.patient_id=%s AND (e.status='Finalizada' OR e.author_id=%s) ORDER BY e.occurred_at DESC",(pid,uid)); rows=c.fetchall()
            for row in rows:
                c.execute('SELECT m.*,u.name AS author FROM amendments m JOIN users u ON u.id=m.author_id WHERE encounter_id=%s ORDER BY m.created_at',(row['id'],)); row['amendments']=c.fetchall()
            self.audit(c,a,'consultar_historial','patients',pid); return rows
    def amend(self,uid,eid,reason,text):
        if not clean(reason) or not clean(text): raise AppError('Complete el motivo y el texto de la corrección.')
        with self.tx() as c:
            a=self.actor(c,uid,['medico']); c.execute('SELECT * FROM encounters WHERE id=%s FOR UPDATE',(eid,)); r=c.fetchone()
            if not r or r['author_id']!=uid or r['status']!='Finalizada': raise AppError('Solo el autor puede añadir una corrección a su consulta finalizada.')
            c.execute('INSERT INTO amendments(encounter_id,author_id,reason,text) VALUES(%s,%s,%s,%s)',(eid,uid,reason,text)); self.audit(c,a,'anotar_correccion','encounters',eid)
    def export_event(self,uid,entity,entity_id=None,clinical=False):
        with self.tx() as c:
            a=self.actor(c,uid,['admin','medico'] if clinical else ['admin','secretaria','medico'])
            if entity_id: self.patient_scope(c,a,entity_id,clinical)
            self.audit(c,a,'exportar',entity,entity_id)
    def settings(self,uid,rule=None):
        with self.tx() as c:
            a=self.actor(c,uid,['admin'])
            if rule:
                if rule not in ('global','specialty'): raise AppError('Regla desconocida.')
                c.execute("UPDATE settings SET value=%s WHERE key='consultation_rule'",(rule,)); self.audit(c,a,'regla_consulta','settings',detail={'regla':rule})
            c.execute("SELECT value FROM settings WHERE key='consultation_rule'"); return c.fetchone()['value']
    def audit_rows(self,uid):
        with self.tx() as c:
            self.actor(c,uid,['admin']); c.execute('SELECT a.created_at,u.name AS usuario,a.action,a.entity,a.entity_id,a.detail FROM audit a LEFT JOIN users u ON u.id=a.actor_id ORDER BY a.id DESC LIMIT 500'); return c.fetchall()
    def backup(self,uid):
        with self.tx() as c:
            c.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ')
            a=self.actor(c,uid,['admin']); self.audit(c,a,'respaldo','database')
            payload={}
            for table in BACKUP_TABLES:
                c.execute(sql.SQL('SELECT * FROM {}').format(sql.Identifier(table))); payload[table]=[dict(r) for r in c.fetchall()]
        raw=json.dumps({'version':5,'created_at':now(),'tables':payload},ensure_ascii=False,default=json_default).encode()
        out=io.BytesIO()
        with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED) as z:
            z.writestr('datos.json',raw); z.writestr('sha256.txt',hashlib.sha256(raw).hexdigest())
        return out.getvalue()
    def restore_empty(self,blob):
        with zipfile.ZipFile(io.BytesIO(blob)) as z:
            if z.getinfo('datos.json').file_size>100_000_000: raise AppError('Respaldo demasiado grande para este restaurador.')
            raw=z.read('datos.json')
            if not hmac.compare_digest(hashlib.sha256(raw).hexdigest(),z.read('sha256.txt').decode().strip()): raise AppError('El respaldo está dañado.')
        data=json.loads(raw)
        if data.get('version')!=5 or set(data.get('tables',{}))!=set(BACKUP_TABLES): raise AppError('El respaldo no es compatible con esta versión.')
        with self.tx() as c:
            c.execute('SELECT pg_advisory_xact_lock(861230)')
            for table in BACKUP_TABLES:
                if table=='settings': continue
                c.execute(sql.SQL('SELECT count(*) AS n FROM {}').format(sql.Identifier(table)))
                if c.fetchone()['n']: raise AppError('La restauración requiere un esquema medisuport vacío. No se sobreescriben datos.')
            for table in BACKUP_TABLES:
                if table=='settings': c.execute('DELETE FROM settings')
                for row in data['tables'][table]:
                    values=[Json(v) if isinstance(v,dict) else v for v in row.values()]
                    c.execute(sql.SQL('INSERT INTO {} ({}) VALUES ({})').format(sql.Identifier(table),sql.SQL(',').join(map(sql.Identifier,row)),sql.SQL(',').join(sql.Placeholder()*len(row))),values)
                c.execute('SELECT pg_get_serial_sequence(%s,%s) AS seq',('medisuport.'+table,'id')) if table not in ('settings','legacy_archive') else None
                if table not in ('settings','legacy_archive'):
                    seq=c.fetchone()['seq']
                    if seq:
                        c.execute(sql.SQL('SELECT MAX(id) AS maximum FROM {}').format(sql.Identifier(table))); maximum=c.fetchone()['maximum']
                        c.execute('SELECT setval(%s,%s,%s)',(seq,maximum or 1,bool(maximum)))
            self.audit(c,None,'restaurar','database')
