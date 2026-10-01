# Medisuport v2

Sistema clínico en Streamlit con PostgreSQL/Supabase. Esta versión usa el esquema
`medisuport` y conserva intactas las tablas anteriores del esquema `public`.

## Instalación en Codespaces

1. Haga una copia del proyecto actual.
2. Copie todos los archivos de este paquete a la raíz del repositorio.
3. Conserve su archivo `.streamlit/secrets.toml`. Si no existe, copie
   `.streamlit/secrets.example.toml` como `.streamlit/secrets.toml` y coloque la
   clave actual de Supabase.
4. Ejecute:

   ```bash
   python -m pip install -r requirements.txt
   python -m streamlit run app.py
   ```

5. En la primera pantalla, cree la cuenta administradora individual. Use una
   contraseña nueva de al menos 12 caracteres. Las claves compartidas de la
   versión anterior dejan de utilizarse.
6. Entre en **Administración → Actualización de datos anteriores**. Revise las
   cantidades y ejecute la importación. Los registros incompatibles se conservan
   en `medisuport.legacy_archive` y aparecen en un Excel de pendientes.
7. Registre horarios estructurados para cada médico antes de crear citas nuevas.

## Archivos

- `app.py`: interfaz completa.
- `core.py`: seguridad, permisos, reglas clínicas y operaciones de datos.
- `schema.sql`: esquema v3, restricciones y protección contra citas cruzadas.
- `plantilla_importacion_pacientes.xlsx`: plantilla oficial para cargar pacientes de convenios.
- `legacy.py`: importación repetible de la versión anterior.
- `exports.py`: expedientes Word y reportes Excel.
- `manage.py`: creación inicial alternativa y restauración en esquema vacío.

## Cambios funcionales

- Cuentas individuales, contraseñas cifradas, bloqueo de intentos y cambio
  obligatorio de claves temporales.
- Permisos para administración, secretaría y médicos.
- Pacientes editables y archivables; no se eliminan expedientes desde la app.
- Convenios configurables para cualquier institución, afiliaciones múltiples e
  importación de pacientes mediante Excel con validación previa.
- La cita conserva el convenio utilizado y permite exigir autorización según la
  configuración de cada institución.
- Agenda por turnos, duración, disponibilidad, ausencias y control de cruces de
  médico y paciente incluso si dos recepcionistas guardan al mismo tiempo.
- Estados de cita y apertura de consulta desde una cita marcada como “Llegó”.
- Borradores clínicos, IMC automático, hábitos guardados y correcciones mediante
  notas adicionales que conservan el texto original.
- Exportación Word, Excel, respaldo recuperable y registro de actividad.

## Respaldo y restauración

El administrador genera el ZIP desde **Reportes y respaldo**. La restauración no
sobrescribe una base con datos; requiere un esquema `medisuport` vacío:

```bash
python manage.py restore ruta/al/respaldo.zip
```

## Verificación local

```bash
python -m unittest discover -s tests -v
python -m py_compile app.py core.py legacy.py exports.py manage.py
```

La prueba completa contra Supabase debe hacerse desde el Codespace porque el
entorno de construcción no utiliza las credenciales del proyecto.
