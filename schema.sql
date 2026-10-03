-- Versión 5: esquema separado; no modifica ni elimina tablas public anteriores.
CREATE SCHEMA IF NOT EXISTS extensions;
CREATE EXTENSION IF NOT EXISTS btree_gist WITH SCHEMA extensions;
CREATE SCHEMA IF NOT EXISTS medisuport;
REVOKE ALL ON SCHEMA medisuport FROM PUBLIC;
SET LOCAL search_path TO medisuport, public, extensions;
CREATE TABLE IF NOT EXISTS settings (
 key TEXT PRIMARY KEY, value TEXT NOT NULL
);
INSERT INTO settings VALUES ('schema_version','2'),('consultation_rule','specialty')
 ON CONFLICT DO NOTHING;
UPDATE settings SET value='9' WHERE key='schema_version';
CREATE TABLE IF NOT EXISTS doctors (
 id BIGSERIAL PRIMARY KEY, name TEXT NOT NULL UNIQUE,
 specialties TEXT[] NOT NULL, active BOOLEAN NOT NULL DEFAULT TRUE,
 professional_id TEXT, registration TEXT,
 slot_minutes INT NOT NULL DEFAULT 30 CHECK(slot_minutes BETWEEN 5 AND 240),
 version INT NOT NULL DEFAULT 1
);
ALTER TABLE doctors ADD COLUMN IF NOT EXISTS professional_id TEXT;
ALTER TABLE doctors ADD COLUMN IF NOT EXISTS registration TEXT;
CREATE TABLE IF NOT EXISTS users (
 id BIGSERIAL PRIMARY KEY, username TEXT NOT NULL UNIQUE,
 name TEXT NOT NULL, password_hash TEXT NOT NULL,
 role TEXT NOT NULL CHECK(role IN ('admin','secretaria','medico')),
 doctor_id BIGINT REFERENCES doctors(id), active BOOLEAN NOT NULL DEFAULT TRUE,
 must_change BOOLEAN NOT NULL DEFAULT TRUE, auth_version INT NOT NULL DEFAULT 1,
 CHECK(role <> 'medico' OR doctor_id IS NOT NULL)
);
CREATE UNIQUE INDEX IF NOT EXISTS user_doctor_unique ON users(doctor_id) WHERE role='medico' AND active;
CREATE TABLE IF NOT EXISTS login_attempts (
 id BIGSERIAL PRIMARY KEY, username TEXT NOT NULL,
 attempted_at TIMESTAMPTZ NOT NULL DEFAULT now(), success BOOLEAN NOT NULL
);
CREATE INDEX IF NOT EXISTS login_recent ON login_attempts(username,attempted_at);
-- Al instalar la versión 8 se retira una sola vez el catálogo anterior de
-- médicos. No se eliminan filas porque historias, citas y certificados deben
-- conservar el profesional que los atendió.
DO $$ BEGIN
 IF NOT EXISTS(SELECT 1 FROM settings WHERE key='doctor_catalog_reset_v8') THEN
  UPDATE users SET active=FALSE,auth_version=auth_version+1 WHERE role='medico';
  UPDATE doctors SET active=FALSE,version=version+1;
  INSERT INTO settings(key,value) VALUES('doctor_catalog_reset_v8','completed');
 END IF;
END $$;
CREATE TABLE IF NOT EXISTS patients (
 id BIGSERIAL PRIMARY KEY, document TEXT NOT NULL UNIQUE, name TEXT NOT NULL,
 apellido1 TEXT, apellido2 TEXT, nombre1 TEXT, nombre2 TEXT,
 sex TEXT, birth_date DATE, address TEXT, phone TEXT, email TEXT,
 occupation TEXT, coverage TEXT, origin TEXT,
 active BOOLEAN NOT NULL DEFAULT TRUE, archive_reason TEXT,
 version INT NOT NULL DEFAULT 1, created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
 updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS patient_name_idx ON patients(lower(name));
ALTER TABLE patients ADD COLUMN IF NOT EXISTS apellido1 TEXT;
ALTER TABLE patients ADD COLUMN IF NOT EXISTS apellido2 TEXT;
ALTER TABLE patients ADD COLUMN IF NOT EXISTS nombre1 TEXT;
ALTER TABLE patients ADD COLUMN IF NOT EXISTS nombre2 TEXT;
CREATE TABLE IF NOT EXISTS agreements (
 id BIGSERIAL PRIMARY KEY, name TEXT NOT NULL UNIQUE, code TEXT,
 tax_id TEXT, contact_name TEXT, phone TEXT, email TEXT,
 start_date DATE, end_date DATE, notes TEXT,
 requires_authorization BOOLEAN NOT NULL DEFAULT FALSE,
 requires_validation_date BOOLEAN NOT NULL DEFAULT FALSE,
 active BOOLEAN NOT NULL DEFAULT TRUE, version INT NOT NULL DEFAULT 1,
 created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
 updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
 CHECK(end_date IS NULL OR start_date IS NULL OR end_date>=start_date)
);
CREATE TABLE IF NOT EXISTS patient_agreements (
 patient_id BIGINT NOT NULL REFERENCES patients(id),
 agreement_id BIGINT NOT NULL REFERENCES agreements(id),
 member_number TEXT, active BOOLEAN NOT NULL DEFAULT TRUE,
 created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
 PRIMARY KEY(patient_id,agreement_id)
);
CREATE TABLE IF NOT EXISTS availability (
 id BIGSERIAL PRIMARY KEY, doctor_id BIGINT NOT NULL REFERENCES doctors(id),
 weekday INT NOT NULL CHECK(weekday BETWEEN 0 AND 6),
 start_time TIME NOT NULL, end_time TIME NOT NULL, CHECK(end_time>start_time),
 UNIQUE(doctor_id,weekday,start_time,end_time)
);
CREATE TABLE IF NOT EXISTS blocks (
 id BIGSERIAL PRIMARY KEY, doctor_id BIGINT NOT NULL REFERENCES doctors(id),
 start_at TIMESTAMPTZ NOT NULL, end_at TIMESTAMPTZ NOT NULL, reason TEXT NOT NULL,
 CHECK(end_at>start_at)
);
CREATE TABLE IF NOT EXISTS appointments (
 id BIGSERIAL PRIMARY KEY, patient_id BIGINT NOT NULL REFERENCES patients(id),
 doctor_id BIGINT NOT NULL REFERENCES doctors(id), specialty TEXT NOT NULL,
 start_at TIMESTAMPTZ NOT NULL, end_at TIMESTAMPTZ NOT NULL,
 status TEXT NOT NULL DEFAULT 'Pendiente' CHECK(status IN
 ('Pendiente','Confirmada','Llegó','En atención','Atendida','Cancelada','No asistió')),
 authorization_code TEXT, expires_on DATE, notes TEXT, cancel_reason TEXT,
 version INT NOT NULL DEFAULT 1, CHECK(end_at>start_at),
 CONSTRAINT doctor_no_overlap EXCLUDE USING gist
 (doctor_id WITH =, tstzrange(start_at,end_at,'[)') WITH &&)
 WHERE(status NOT IN ('Cancelada','No asistió')),
 CONSTRAINT patient_no_overlap EXCLUDE USING gist
 (patient_id WITH =, tstzrange(start_at,end_at,'[)') WITH &&)
 WHERE(status NOT IN ('Cancelada','No asistió'))
);
ALTER TABLE appointments ADD COLUMN IF NOT EXISTS agreement_id BIGINT REFERENCES agreements(id);
ALTER TABLE agreements ADD COLUMN IF NOT EXISTS requires_authorization BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE agreements ADD COLUMN IF NOT EXISTS requires_validation_date BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE appointments ADD COLUMN IF NOT EXISTS validation_date DATE;
CREATE INDEX IF NOT EXISTS appointment_date_idx ON appointments(start_at);
CREATE INDEX IF NOT EXISTS patient_agreement_idx ON patient_agreements(agreement_id,patient_id);
CREATE TABLE IF NOT EXISTS encounters (
 id BIGSERIAL PRIMARY KEY, patient_id BIGINT NOT NULL REFERENCES patients(id),
 doctor_id BIGINT REFERENCES doctors(id), appointment_id BIGINT UNIQUE REFERENCES appointments(id),
 author_id BIGINT REFERENCES users(id), specialty TEXT,
 status TEXT NOT NULL CHECK(status IN ('Borrador','Finalizada')),
 consultation_type TEXT NOT NULL DEFAULT 'C1', data JSONB NOT NULL DEFAULT '{}',
 version INT NOT NULL DEFAULT 1, occurred_at TIMESTAMPTZ NOT NULL DEFAULT now(),
 finalized_at TIMESTAMPTZ, legacy_author TEXT
);
CREATE TABLE IF NOT EXISTS amendments (
 id BIGSERIAL PRIMARY KEY, encounter_id BIGINT NOT NULL REFERENCES encounters(id),
 author_id BIGINT NOT NULL REFERENCES users(id), reason TEXT NOT NULL, text TEXT NOT NULL,
 created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS certificates (
 id BIGSERIAL PRIMARY KEY, patient_id BIGINT NOT NULL REFERENCES patients(id),
 doctor_id BIGINT NOT NULL REFERENCES doctors(id), issued_by BIGINT NOT NULL REFERENCES users(id),
 institution TEXT NOT NULL, location TEXT NOT NULL, specialty TEXT,
 diagnosis TEXT NOT NULL, cie10 TEXT, rest_from DATE, rest_to DATE,
 observations TEXT, issued_at TIMESTAMPTZ NOT NULL DEFAULT now(),
 created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS certificate_patient_idx ON certificates(patient_id,issued_at DESC);
CREATE INDEX IF NOT EXISTS certificate_doctor_idx ON certificates(doctor_id,issued_at DESC);
-- Módulo financiero administrativo. Estas cuentas internas no sustituyen al
-- comprobante electrónico autorizado por el SRI.
CREATE TABLE IF NOT EXISTS services (
 id BIGSERIAL PRIMARY KEY, code TEXT NOT NULL UNIQUE, name TEXT NOT NULL,
 description TEXT, category TEXT NOT NULL DEFAULT 'Consulta', base_price NUMERIC(12,2) NOT NULL DEFAULT 0 CHECK(base_price>=0),
 tax_rate NUMERIC(5,2) NOT NULL DEFAULT 0 CHECK(tax_rate BETWEEN 0 AND 100),
 active BOOLEAN NOT NULL DEFAULT TRUE, version INT NOT NULL DEFAULT 1,
 created_at TIMESTAMPTZ NOT NULL DEFAULT now(), updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
ALTER TABLE services ADD COLUMN IF NOT EXISTS description TEXT;
INSERT INTO services(code,name,description,category,base_price,tax_rate) VALUES
 ('CONS-GEN','Consulta médica general','Valoración médica general inicial o atención por enfermedad común.','Consulta',0,0),
 ('CONS-ESP','Consulta médica especializada','Valoración realizada por un profesional de una especialidad médica.','Consulta',0,0),
 ('CONS-CTL','Consulta de control','Seguimiento posterior de una consulta, tratamiento o procedimiento.','Consulta',0,0),
 ('EMER-001','Atención de emergencia','Evaluación y atención inmediata de una condición urgente.','Consulta',0,0),
 ('ECO-001','Ecografía','Estudio diagnóstico mediante ultrasonido; especifique el tipo en la cuenta.','Imagen',0,0),
 ('RX-001','Radiografía','Estudio radiológico; especifique la región examinada en la cuenta.','Imagen',0,0),
 ('LAB-001','Exámenes de laboratorio','Pruebas de laboratorio clínico; detalle los exámenes realizados.','Laboratorio',0,0),
 ('CUR-001','Curación','Limpieza, tratamiento y cobertura de heridas.','Procedimiento',0,0),
 ('INY-001','Aplicación de medicamento','Administración de medicamento por vía indicada por el profesional.','Procedimiento',0,0),
 ('PROC-001','Procedimiento médico menor','Procedimiento ambulatorio menor; detalle cuál se realizó.','Procedimiento',0,0),
 ('CERT-001','Certificado médico','Emisión de certificado médico cuando corresponda legal y clínicamente.','Otro',0,0),
 ('TER-001','Sesión de terapia','Sesión individual de terapia o rehabilitación.','Procedimiento',0,0),
 ('ENF-001','Atención de enfermería','Servicio independiente realizado por personal de enfermería.','Procedimiento',0,0),
 ('DOM-001','Visita domiciliaria','Atención de un profesional de salud en el domicilio del paciente.','Consulta',0,0),
 ('TEL-001','Teleconsulta','Atención profesional realizada mediante videollamada o medio remoto.','Consulta',0,0)
 ON CONFLICT(code) DO UPDATE SET name=EXCLUDED.name,description=EXCLUDED.description,category=EXCLUDED.category,active=TRUE;
CREATE TABLE IF NOT EXISTS agreement_tariffs (
 agreement_id BIGINT NOT NULL REFERENCES agreements(id),
 service_id BIGINT NOT NULL REFERENCES services(id),
 agreed_price NUMERIC(12,2) NOT NULL CHECK(agreed_price>=0),
 patient_copay NUMERIC(12,2) NOT NULL DEFAULT 0 CHECK(patient_copay>=0),
 active BOOLEAN NOT NULL DEFAULT TRUE, updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
 PRIMARY KEY(agreement_id,service_id)
);
CREATE TABLE IF NOT EXISTS invoices (
 id BIGSERIAL PRIMARY KEY, number TEXT UNIQUE,
 appointment_id BIGINT UNIQUE REFERENCES appointments(id),
 patient_id BIGINT NOT NULL REFERENCES patients(id),
 agreement_id BIGINT REFERENCES agreements(id),
 issue_date DATE NOT NULL DEFAULT CURRENT_DATE, due_date DATE NOT NULL DEFAULT CURRENT_DATE,
 status TEXT NOT NULL DEFAULT 'Emitida' CHECK(status IN ('Emitida','Parcial','Pagada','Anulada')),
 subtotal NUMERIC(12,2) NOT NULL DEFAULT 0, discount NUMERIC(12,2) NOT NULL DEFAULT 0,
 tax NUMERIC(12,2) NOT NULL DEFAULT 0, total NUMERIC(12,2) NOT NULL CHECK(total>=0),
 patient_responsibility NUMERIC(12,2) NOT NULL DEFAULT 0 CHECK(patient_responsibility>=0),
 agreement_responsibility NUMERIC(12,2) NOT NULL DEFAULT 0 CHECK(agreement_responsibility>=0),
 notes TEXT, created_by BIGINT NOT NULL REFERENCES users(id),
 created_at TIMESTAMPTZ NOT NULL DEFAULT now(), updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS invoice_date_idx ON invoices(issue_date,status);
CREATE INDEX IF NOT EXISTS invoice_agreement_idx ON invoices(agreement_id,issue_date);
CREATE TABLE IF NOT EXISTS invoice_items (
 id BIGSERIAL PRIMARY KEY, invoice_id BIGINT NOT NULL REFERENCES invoices(id) ON DELETE CASCADE,
 service_id BIGINT REFERENCES services(id), description TEXT NOT NULL,
 quantity NUMERIC(10,2) NOT NULL CHECK(quantity>0), unit_price NUMERIC(12,2) NOT NULL CHECK(unit_price>=0),
 discount NUMERIC(12,2) NOT NULL DEFAULT 0 CHECK(discount>=0), tax_rate NUMERIC(5,2) NOT NULL DEFAULT 0,
 subtotal NUMERIC(12,2) NOT NULL, tax NUMERIC(12,2) NOT NULL, total NUMERIC(12,2) NOT NULL
);
CREATE TABLE IF NOT EXISTS payments (
 id BIGSERIAL PRIMARY KEY, invoice_id BIGINT NOT NULL REFERENCES invoices(id),
 payment_date DATE NOT NULL DEFAULT CURRENT_DATE, amount NUMERIC(12,2) NOT NULL CHECK(amount>0),
 method TEXT NOT NULL CHECK(method IN ('Efectivo','Tarjeta','Transferencia','Cheque','Otro')),
 reference TEXT, notes TEXT, received_by BIGINT NOT NULL REFERENCES users(id),
 created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS payment_invoice_idx ON payments(invoice_id,payment_date);
CREATE TABLE IF NOT EXISTS cash_movements (
 id BIGSERIAL PRIMARY KEY, movement_date DATE NOT NULL DEFAULT CURRENT_DATE,
 movement_type TEXT NOT NULL CHECK(movement_type IN ('Ingreso','Egreso')),
 category TEXT NOT NULL, description TEXT NOT NULL,
 amount NUMERIC(12,2) NOT NULL CHECK(amount>0),
 method TEXT NOT NULL CHECK(method IN ('Efectivo','Tarjeta','Transferencia','Cheque','Otro')),
 reference TEXT, invoice_id BIGINT REFERENCES invoices(id), created_by BIGINT NOT NULL REFERENCES users(id),
 created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS cash_date_idx ON cash_movements(movement_date,movement_type);
CREATE TABLE IF NOT EXISTS audit (
 id BIGSERIAL PRIMARY KEY, actor_id BIGINT REFERENCES users(id), action TEXT NOT NULL,
 entity TEXT NOT NULL, entity_id TEXT, detail JSONB NOT NULL DEFAULT '{}',
 created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS legacy_archive (
 source_table TEXT NOT NULL, source_key TEXT NOT NULL, data JSONB NOT NULL,
 imported_entity TEXT, imported_id BIGINT, issue TEXT,
 PRIMARY KEY(source_table,source_key)
);
-- Reinicio definitivo solicitado para comenzar la empresa desde cero.
-- Se ejecuta una sola vez y conserva únicamente las cuentas administradoras.
DO $$ BEGIN
 IF NOT EXISTS(SELECT 1 FROM settings WHERE key='company_reset_v9') THEN
  TRUNCATE TABLE audit,login_attempts,cash_movements,payments,invoice_items,invoices,
   agreement_tariffs,certificates,amendments,encounters,appointments,blocks,
   availability,patient_agreements,legacy_archive,patients,agreements RESTART IDENTITY;
  DELETE FROM users WHERE role<>'admin';
  DELETE FROM doctors;
  DELETE FROM services WHERE code NOT IN ('CONS-GEN','CONS-ESP','CONS-CTL','EMER-001','ECO-001','RX-001','LAB-001','CUR-001','INY-001','PROC-001','CERT-001','TER-001','ENF-001','DOM-001','TEL-001');
  UPDATE services SET base_price=0,tax_rate=0,active=TRUE,version=version+1;
  INSERT INTO settings(key,value) VALUES('company_reset_v9','completed');
 END IF;
END $$;
-- No políticas para anon/authenticated. La aplicación accede desde el servidor.
DO $$ DECLARE t RECORD; BEGIN
 FOR t IN SELECT tablename FROM pg_tables WHERE schemaname='medisuport' LOOP
  EXECUTE format('ALTER TABLE medisuport.%I ENABLE ROW LEVEL SECURITY',t.tablename);
 END LOOP;
END $$;
