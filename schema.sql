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
UPDATE settings SET value='6' WHERE key='schema_version';
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
-- No políticas para anon/authenticated. La aplicación accede desde el servidor.
DO $$ DECLARE t RECORD; BEGIN
 FOR t IN SELECT tablename FROM pg_tables WHERE schemaname='medisuport' LOOP
  EXECUTE format('ALTER TABLE medisuport.%I ENABLE ROW LEVEL SECURITY',t.tablename);
 END LOOP;
END $$;
