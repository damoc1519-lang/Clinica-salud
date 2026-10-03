"""Documentos Word y reportes Excel bajo los permisos del backend."""
import io
import re
import unicodedata
from pathlib import Path
from html import escape
from datetime import datetime,date,time
from decimal import Decimal
import pandas as pd
from docx import Document
from docx.shared import Inches,Pt,RGBColor
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl import Workbook, load_workbook
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, KeepTogether
from core import TZ, proper_name

LABELS={'antecedentes_pers':'Antecedentes personales','antecedentes_fam':'Antecedentes familiares','habitos':'Hábitos de vida','motivo':'Motivo de consulta','enfermedad_actual':'Enfermedad actual','peso':'Peso (kg)','talla':'Talla (cm)','pa':'Presión arterial','fc':'Frecuencia cardíaca','imc':'IMC','diagnostico':'Diagnóstico','tratamiento':'Tratamiento / indicaciones','examenes':'Exámenes complementarios'}
SECTIONS=[
 ('ANAMNESIS',[('motivo','Motivo de consulta'),('personal_conditions','Antecedentes personales marcados'),('personal_details','Antecedentes personales relevantes'),('antecedentes_pers','Antecedentes personales anteriores'),('family_conditions','Antecedentes familiares marcados'),('family_details','Antecedentes familiares'),('antecedentes_fam','Antecedentes familiares anteriores'),('habitos','Hábitos de vida'),('alergias','Alergias'),('enfermedad_actual','Enfermedad o problema actual')]),
 ('CONSTANTES VITALES Y ANTROPOMETRÍA',[('temperatura','Temperatura (°C)'),('pa','Presión arterial (mmHg)'),('fc','Pulso/min'),('fr','Frecuencia respiratoria/min'),('peso','Peso (kg)'),('talla','Talla (cm)'),('imc','IMC (kg/m²)'),('perimetro_abdominal','Perímetro abdominal (cm)'),('hemoglobina_capilar','Hemoglobina capilar (g/dL)'),('glucosa_capilar','Glucosa capilar (mg/dL)'),('spo2','Pulsioximetría (%)')]),
 ('REVISIÓN Y EXAMEN FÍSICO',[('systems_review','Sistemas con patología'),('systems_details','Descripción por sistemas'),('physical_regional','Hallazgos regionales'),('physical_systemic','Hallazgos sistémicos'),('physical_details','Descripción del examen físico')]),
 ('DIAGNÓSTICO Y PLAN',[('diagnostico','Diagnóstico principal'),('diagnoses','Diagnósticos CIE10 / tipo / descripción'),('examenes','Resultados relevantes'),('tratamiento','Plan diagnóstico, terapéutico y educacional')]),
 ('INTERCONSULTA',[('interconsult_specialty','Especialidad consultada'),('interconsult_reason','Motivo'),('clinical_summary','Cuadro clínico actual'),('exam_results','Resultados relevantes'),('therapeutic_plan','Plan terapéutico realizado')]),
 ('REFERENCIA / DERIVACIÓN',[('referral_type','Tipo'),('referral_reasons','Motivos'),('referral_destination','Institución o establecimiento de destino'),('referral_service','Servicio'),('referral_specialty','Especialidad'),('referral_summary','Resumen clínico'),('referral_findings','Hallazgos relevantes')]),
 ('LABORATORIO',[('lab_tests','Exámenes solicitados'),('other_lab_tests','Otros exámenes / muestra / sitio anatómico'),('lab_treatment','Tratamiento terapéutico')]),
 ('IMAGENOLOGÍA',[('imaging_types','Estudios solicitados'),('imaging_description','Descripción'),('imaging_reason','Motivo'),('fum','FUM'),('contaminado','Paciente contaminado'),('sedacion','Requiere sedación')]),
 ('RECETA',[('alergias','Alergias'),('prescription','Medicamentos, dosis y horarios'),('prescription_warnings','Indicaciones y advertencias')])]
def pretty(value):
    if value is None or value=='': return 'No registrado'
    if isinstance(value,datetime): return value.astimezone(TZ).strftime('%d/%m/%Y %H:%M')
    if isinstance(value,date): return value.strftime('%d/%m/%Y')
    if isinstance(value,bool): return 'Sí' if value else 'No'
    if isinstance(value,(list,tuple)): return ', '.join(map(str,value)) if value else 'No registrado'
    return str(value)

def _finalized(histories): return [h for h in histories if h['status']=='Finalizada']
def _encounter_rows(data):
    for title,fields in SECTIONS:
        rows=[(label,pretty(data.get(key))) for key,label in fields]
        if any(data.get(key) not in (None,'',[],False,0,0.0) for key,_ in fields): yield title,rows


# Plantilla oficial SNS-MSP / HCU utilizada por el convenio.
ISSFA_TEMPLATE = Path(__file__).parent / 'templates' / 'HISTORIA_CLINICA_ISSFA.xlsx'
OFFICIAL_SHEETS = ['HC','INTER007','REF053','LAB010','IMA012','RECETA']
UNICODIGO = 56398
ESTABLECIMIENTO = 'MEDISUPORT / QMC'

def _norm_text(value):
    if value is None:
        return ''
    text = str(value).upper()
    text = unicodedata.normalize('NFD', text)
    text = ''.join(ch for ch in text if unicodedata.category(ch) != 'Mn')
    text = re.sub(r'[\r\n]+', ' ', text)
    text = re.sub(r'[^A-Z0-9 ]+', ' ', text)
    return re.sub(r'\s+', ' ', text).strip()

def _patient_parts(name, patient=None):
    """Devuelve apellido1, apellido2, nombre1 y nombre2.
    Usa los campos estructurados cuando existen y solo recurre a heurística
    para expedientes antiguos que todavía no los tienen.
    """
    patient=patient or {}
    structured=tuple(proper_name(patient.get(k) or '') for k in ('apellido1','apellido2','nombre1','nombre2'))
    if structured[0] and structured[2]:
        return structured
    words=proper_name(name).split()
    if len(words)>=4:
        return words[0],words[1],words[2],' '.join(words[3:])
    if len(words)==3:
        return words[0],words[1],words[2],''
    if len(words)==2:
        return words[0],'',words[1],''
    return (words[0] if words else '', '', '', '')

def _doctor_parts(name):
    words=proper_name(name).split()
    if len(words)>=3:
        return words[0],words[-2],words[-1]
    if len(words)==2:
        return words[0],words[1],''
    return (words[0] if words else '', '', '')

def _system_institution(patient):
    coverage=_norm_text(patient.get('coverage'))
    if 'ISSFA' in coverage:
        return 'ISSFA'
    if coverage:
        return coverage[:40]
    return 'PRIVADO'

def _write_merged(ws, coord, value):
    # Escribe siempre en la esquina superior izquierda de una celda combinada.
    ws[coord] = value if value not in (None, '') else ''

def _clear_cells(ws, coords):
    for coord in coords:
        ws[coord]=''

def _fill_diagnoses(ws, diagnoses, principal=''):
    parsed=[]
    for item in diagnoses or []:
        parts=[p.strip() for p in str(item).split('|')]
        if len(parts)>=3:
            cie,kind,desc=parts[0],parts[1], ' | '.join(parts[2:]).strip()
        elif len(parts)==2:
            cie,desc=parts[0],parts[1]
            kind=''
        else:
            cie,kind,desc='','',parts[0]
        if desc or cie:
            parsed.append((desc,cie,kind))
    if not parsed and principal:
        parsed=[(str(principal).strip(),'','Definitivo')]
    elif parsed and principal and not any(_norm_text(principal) in _norm_text(x[0]) or _norm_text(x[0]) in _norm_text(principal) for x in parsed):
        # Mantener el diagnóstico principal como primera fila cuando existe.
        parsed.insert(0,(str(principal).strip(),'','Definitivo'))
    parsed=parsed[:6]

    left=[(47,48,49),(None,None,None)]
    slots=[(47,'B','Y','AC','AE'),(48,'B','Y','AC','AE'),(49,'B','Y','AC','AE'),
           (47,'AH','BE','BI','BK'),(48,'AH','BE','BI','BK'),(49,'AH','BE','BI','BK')]
    for i,(_,desc,cie,kind) in enumerate([(i,*parsed[i]) for i in range(len(parsed))]):
        row,b,ciecol,precol,defcol=slots[i]
        ws[f'{b}{row}']=desc
        ws[f'{ciecol}{row}']=cie
        ws[f'{precol}{row}']='X' if _norm_text(kind).startswith('PRE') else ''
        ws[f'{defcol}{row}']='X' if _norm_text(kind).startswith('DEF') else ''

def _fill_hc(ws, patient, h):
    data=h.get('data') or {}
    occurred=h.get('occurred_at')
    if occurred and occurred.tzinfo:
        occurred=occurred.astimezone(TZ)

    s1,s2,n1,n2=_patient_parts(patient.get('name'),patient)
    d1,ds1,ds2=_doctor_parts(h.get('doctor'))
    # Cabecera del formulario oficial.
    ws['A3']=_system_institution(patient)
    ws['N3']=UNICODIGO
    ws['T3']=ESTABLECIMIENTO
    ws['AH3']=patient.get('document') or ''
    ws['AZ3']=patient.get('birth_date')
    ws['BJ3']=1
    ws['A5']=s1; ws['O5']=s2; ws['AC5']=n1; ws['AQ5']=n2
    ws['BE5']=patient.get('sex') or ''
    ws['A8']=patient.get('phone') or ''
    # La app guarda dirección como un solo campo; se conserva en la parroquia
    # para no perder información en el formulario oficial.
    ws['O8']=''
    ws['AH8']=''
    ws['BA8']=patient.get('address') or ''

    # Motivo y antecedentes.
    ws['A11']=data.get('motivo') or ''
    personal=set(_norm_text(x) for x in data.get('personal_conditions',[]))
    family=set(_norm_text(x) for x in data.get('family_conditions',[]))
    personal_cells={
        'CARDIOPATÍA':'BK14','HIPERTENSIÓN':'BK14','ENFERMEDAD CEREBROVASCULAR':'BK14',
    }
    # Cada casilla oficial está al final del bloque correspondiente.
    condition_slots={
        'CARDIOPATÍA':'G14','HIPERTENSIÓN':'N14','ENFERMEDAD CEREBROVASCULAR':'T14',
        'ENDÓCRINO-METABÓLICA':'AA14','CÁNCER':'AG14','TUBERCULOSIS':'AO14',
        'ENFERMEDAD MENTAL':'AT14','ENFERMEDAD INFECCIOSA':'AZ14','MALFORMACIÓN':'BF14','OTRA':'BK14'
    }
    # Las casillas se encuentran en la última columna de cada bloque.
    condition_checkbox={
        'CARDIOPATÍA':'G14','HIPERTENSIÓN':'N14','ENFERMEDAD CEREBROVASCULAR':'T14',
        'ENDÓCRINO-METABÓLICA':'AG14','CÁNCER':'AG14','TUBERCULOSIS':'AO14',
        'ENFERMEDAD MENTAL':'AT14','ENFERMEDAD INFECCIOSA':'AZ14','MALFORMACIÓN':'BF14','OTRA':'BK14'
    }
    # Ajuste por la geometría real de la plantilla: las casillas son las celdas
    # inmediatamente posteriores a cada etiqueta.
    personal_check=['F14','M14','S14','Z14','AF14','AN14','AS14','AY14','BE14','BK14']
    family_check=['F18','M18','S18','Z18','AF18','AN18','AS18','AY18','BE18','BK18']
    for c in personal_check+family_check: ws[c]=''
    condition_order=['CARDIOPATÍA','HIPERTENSIÓN','ENFERMEDAD CEREBROVASCULAR','ENDÓCRINO-METABÓLICA','CÁNCER','TUBERCULOSIS','ENFERMEDAD MENTAL','ENFERMEDAD INFECCIOSA','MALFORMACIÓN','OTRA']
    for idx,label in enumerate(condition_order):
        aliases={label}
        if label=='ENFERMEDAD CEREBROVASCULAR': aliases.add('ENFERMEDAD CEREBROVASCULAR')
        if label=='ENDÓCRINO-METABÓLICA': aliases.add('ENDÓCRINO METABÓLICA')
        if label=='MALFORMACIÓN': aliases.add('MALFORMACION')
        if any(a in personal for a in aliases): ws[personal_check[idx]]='X'
        if any(a in family for a in aliases): ws[family_check[idx]]='X'
    ws['A16']=data.get('personal_details') or ''
    ws['A19']=data.get('family_details') or ''
    ws['A24']=data.get('enfermedad_actual') or ''

    # Constantes.
    if occurred:
        ws['A27']=occurred.date()
        ws['F27']=occurred.time().replace(second=0,microsecond=0)
    vals={
        'K27':data.get('temperatura'),'O27':data.get('pa'),'T27':data.get('fc'),
        'Y27':data.get('fr'),'AD27':data.get('peso'),'AI27':data.get('talla'),
        'AN27':data.get('imc'),'AS27':data.get('perimetro_abdominal'),
        'AX27':data.get('hemoglobina_capilar'),'BC27':data.get('glucosa_capilar'),
        'BH27':data.get('spo2')
    }
    for coord,val in vals.items(): ws[coord]=val if val not in (None,'',0,0.0) else ''

    # Revisión por sistemas: las X están en la celda posterior a cada etiqueta.
    systems=data.get('systems_review') or []
    sysnorm=set(_norm_text(x) for x in systems)
    system_slots=[
        ('PIEL Y ANEXOS','K31'),('ÓRGANOS DE LOS SENTIDOS','X31'),
        ('RESPIRATORIO','AJ31'),('CARDIOVASCULAR','AX31'),('DIGESTIVO','BK31'),
        ('GENITOURINARIO','K32'),('MÚSCULO-ESQUELÉTICO','X32'),('ENDÓCRINO','AJ32'),
        ('HEMOLINFÁTICO','AX32'),('NERVIOSO','BK32')
    ]
    for _,coord in system_slots: ws[coord]=''
    for label,coord in system_slots:
        if _norm_text(label) in sysnorm or any(_norm_text(label) in s or s in _norm_text(label) for s in sysnorm):
            ws[coord]='X'
    # Descripción por sistemas queda en el área libre inferior.
    ws['A33']=data.get('systems_details') or ''

    # Examen físico regional/sistémico.
    for coord in ['K39','W39','AJ39','AV39','BK39','K40','W40','AJ40','AV40','BK40','K41','W41','AJ41','AV41','BK41','K42','W42','AJ42','AV42','BK42','K43','W43','AJ43','AV43','BK43']:
        ws[coord]=''
    regional_slots=[
        ('PIEL Y FANERAS','K39'),('CABEZA','K40'),('OJOS','K41'),('OÍDOS','K42'),('NARIZ','K43'),
        ('BOCA','W39'),('OROFARINGE','W40'),('CUELLO','W41'),('AXILAS Y MAMAS','W42'),('TÓRAX','W43'),
        ('ABDOMEN','AJ39'),('COLUMNA VERTEBRAL','AJ40'),('INGLE Y PERINÉ','AJ41'),('MIEMBROS SUPERIORES','AJ42'),('MIEMBROS INFERIORES','AJ43')
    ]
    systemic_slots=[
        ('ÓRGANOS DE LOS SENTIDOS','AV39'),('RESPIRATORIO','AV40'),('CARDIOVASCULAR','AV41'),
        ('DIGESTIVO','AV42'),('GENITAL','AV43'),('URINARIO','BK39'),('MÚSCULO-ESQUELÉTICO','BK40'),
        ('ENDÓCRINO','BK41'),('HEMOLINFÁTICO','BK42'),('NEUROLÓGICO','BK43')
    ]
    rn=set(_norm_text(x) for x in data.get('physical_regional',[]))
    sn=set(_norm_text(x) for x in data.get('physical_systemic',[]))
    for label,coord in regional_slots:
        if _norm_text(label) in rn or any(_norm_text(label) in s or s in _norm_text(label) for s in rn): ws[coord]='X'
    for label,coord in systemic_slots:
        if _norm_text(label) in sn or any(_norm_text(label) in s or s in _norm_text(label) for s in sn): ws[coord]='X'
    # Texto del examen físico en el área de observaciones.
    ws['A44']=data.get('physical_details') or ''

    _fill_diagnoses(ws,data.get('diagnoses'),data.get('diagnostico'))
    ws['A52']=data.get('tratamiento') or ''

    if occurred:
        ws['A61']=occurred.date()
        ws['I61']=occurred.time().replace(second=0,microsecond=0)
    ws['O61']=d1
    ws['AH61']=ds1
    ws['AY61']=ds2
    ws['A63']=h.get('professional_id') or ''

def _find_checkbox_for_label(ws, label_cell):
    # Busca la celda combinada angosta que sigue a la etiqueta del examen.
    row=label_cell.row
    # Determina el rango combinado que contiene la etiqueta.
    containing=None
    for mr in ws.merged_cells.ranges:
        if mr.min_row==row and mr.max_row==row and mr.min_col<=label_cell.column<=mr.max_col:
            containing=mr
            break
    if not containing:
        return None
    candidates=[]
    for mr in ws.merged_cells.ranges:
        if mr.min_row==row and mr.max_row==row and mr.min_col>containing.max_col and mr.max_col-mr.min_col<=1:
            candidates.append(mr)
    if candidates:
        candidates.sort(key=lambda r:r.min_col)
        return ws.cell(row,candidates[0].min_col).coordinate
    return None

def _mark_lab_tests(ws, selected):
    # Las X de la plantilla son solo datos de ejemplo; limpiar el área de exámenes.
    for row in range(17,84):
        for cell in ws[row]:
            if isinstance(cell.value,str) and cell.value.strip().upper()=='X':
                cell.value=''
    wanted=[_norm_text(x) for x in selected or []]
    if not wanted: return
    aliases={
        'VSG':'VELOCIDAD DE ERITROSEDIMENTACIÓN',
        'TP':'TIEMPO DE PROTROMBINA TP',
        'TTP':'TIEMPO DE TROMBOPLASTINA PARCIAL TTP',
        'INR':'INR',
        'PCR CUANTITATIVO':'PCR CUANTITATIVO',
        'HB A1C':'HEMOGLOBINA GLICOSILADA HBA1C',
        'HBA1C':'HEMOGLOBINA GLICOSILADA HBA1C',
        'ELECTROLITOS':'NA',
        'GASOMETRÍA ARTERIAL':'GASOMETRÍA ARTERIAL',
        'GASOMETRÍA VENOSA':'GASOMETRÍA VENOSA',
        'VIH 1 2':'VIH 1 2 CUALITATIVA',
        'HEPATITIS A':'HEPATITIS A TOTAL',
        'HEPATITIS B':'ANTIGENO SUPERFICIE HEPATITIS B HBSAG',
        'HEPATITIS C':'HEPATITIS C HVC',
        'VDRL':'VDRL',
        'ANA':'ANA',
        'ANCA':'ANCA C',
        'ANTI DNA':'ANTI DNA',
        'FACTOR REUMATOIDEO':'FACTOR REUMATOIDEO IGM',
        'TROPONINA I':'TROPONINA I',
        'TROPONINA T':'TROPONINA T',
        'CK MB':'CK MB',
        'GRUPO Y FACTOR':'GRUPO Y FACTOR',
        'COOMBS DIRECTO':'COOMBS DIRECTO',
        'COOMBS INDIRECTO':'COOMBS INDIRECTO',
        'CULTIVO Y ANTIBIOGRAMA':'CULTIVO Y ANTIBIOGRAMA',
        'ESTUDIO MICOLÓGICO':'ESTUDIO MICOLÓGICO KOH DE',
        'MARCADORES TUMORALES':'MARCADORES TUMORALES',
    }
    label_cells=[]
    for row in ws.iter_rows():
        for cell in row:
            if isinstance(cell.value,str) and cell.value and not cell.value.startswith('='):
                label_cells.append(cell)
    for wanted_text in wanted:
        target=aliases.get(wanted_text,wanted_text)
        # Prefer exact normalized match; otherwise a contained match.
        matches=[c for c in label_cells if _norm_text(c.value)==target]
        if not matches:
            matches=[c for c in label_cells if target in _norm_text(c.value) or _norm_text(c.value) in target]
        for c in matches[:1]:
            checkbox=_find_checkbox_for_label(ws,c)
            if checkbox:
                ws[checkbox]='X'
                break

def _fill_interconsult(ws,data,h):
    # Limpiar selecciones que vienen de ejemplo en la plantilla.
    for coord in ['N10','BN10']:
        ws[coord]=''
    ws['N10']='X'  # consulta externa
    # Los bloques grandes de texto están directamente en las filas indicadas.
    ws['Y10']=data.get('interconsult_specialty') or ''
    ws['O11']=data.get('interconsult_specialty') or ''
    ws['O12']=data.get('interconsult_reason') or ''
    ws['A17']=data.get('clinical_summary') or data.get('enfermedad_actual') or ''
    ws['A21']=data.get('exam_results') or data.get('examenes') or ''
    ws['A35']=data.get('therapeutic_plan') or data.get('tratamiento') or ''

def _fill_referral(ws,data):
    typ=_norm_text(data.get('referral_type'))
    ws['AU7']='X' if typ=='REFERENCIA' else ''
    ws['BA7']='X' if typ=='DERIVACIÓN' else ''
    reasons=set(_norm_text(x) for x in data.get('referral_reasons',[]))
    # Motivos 1-9: checkboxes BA/BY columns in the official form.
    reason_cells=['BA9','BA10','BA11','BA12','BA13','BY9','BY10','BY11','BY12']
    labels=[
        'ACCESIBILIDAD GEOGRÁFICA','FALTA DE ESPACIO FÍSICO','FALTA DE EQUIPAMIENTO',
        'EQUIPOS EN MAL ESTADO','PROBLEMAS DE INFRAESTRUCTURA','PROBLEMAS DE ABASTECIMIENTO',
        'INSUFICIENCIA DE PROFESIONALES','INADECUADA CAPACIDAD RESOLUTIVA',
        'AUSENCIA DE PRESTACIÓN'
    ]
    for coord in reason_cells: ws[coord]=''
    for label,coord in zip(labels,reason_cells):
        if any(_norm_text(label)==r or _norm_text(label) in r or r in _norm_text(label) for r in reasons):
            ws[coord]='X'
    ws['S17']=''
    ws['AM17']='CONSULTA EXTERNA'
    ws['BF17']=data.get('referral_specialty') or data.get('referral_service') or ''
    ws['A20']=data.get('referral_summary') or data.get('enfermedad_actual') or ''
    ws['A23']=data.get('referral_findings') or data.get('examenes') or ''

def _fill_imaging(ws,data):
    # Servicio por defecto: consulta externa. La plantilla trae una prioridad
    # y selecciones de ejemplo que no deben salir en la descarga.
    ws['O10']='x'
    ws['BR10']=''
    ws['BR13']=''
    ws['AQ19']=''
    imaging_map={
        'RX CONVENCIONAL':'G13','RX PORTÁTIL':'M13','TOMOGRAFÍA':'U13','RESONANCIA':'AB13',
        'ECOGRAFÍA':'AI13','MAMOGRAFÍA':'AQ13','PROCEDIMIENTO':'AZ13','OTRO':'BE13'
    }
    for coord in imaging_map.values(): ws[coord]=''
    for item in data.get('imaging_types',[]) or []:
        n=_norm_text(item)
        for label,coord in imaging_map.items():
            nl=_norm_text(label)
            if n==nl or nl in n or n in nl:
                ws[coord]='x'
                break
    ws['A16']=data.get('imaging_description') or ''
    ws['A20']=data.get('imaging_reason') or ''
    ws['A25']=data.get('clinical_summary') or data.get('enfermedad_actual') or ''
    ws['BR13']='x' if data.get('sedacion') else ''
    ws['AQ19']='x' if data.get('contaminado') else ''
    ws['A19']=data.get('fum') or ''

def _fill_recipe(ws,patient,data,h):
    ws['C20']=proper_name(h.get('doctor'))
    ws['C21']=h.get('specialty') or ''
    ws['B8']=f"Alergias: {data.get('alergias') or 'NO'}"
    lines=[x.strip() for x in str(data.get('prescription') or '').splitlines() if x.strip()]
    for row in range(10,18):
        for col in ['B','G','H','I','J']:
            ws[f'{col}{row}']=''
    for i,line in enumerate(lines[:8],10):
        parts=[x.strip() for x in line.split('|')]
        while len(parts)<7: parts.append('')
        # B: medicamento + concentración/forma + cantidad
        ws[f'B{i}']=' | '.join(parts[:3]).strip(' |')
        ws[f'G{i}']=parts[3]
        ws[f'H{i}']=parts[4]
        ws[f'I{i}']=parts[5]
        ws[f'J{i}']=parts[6]
    ws['B35']=data.get('prescription_warnings') or ''

def _prepare_official_sheet(ws,source_name):
    # Recalcula fórmulas al abrirse en Excel/LibreOffice.
    ws.sheet_view.showGridLines=False
    ws.freeze_panes=None

def _populate_official_group(wb, suffix, patient, h):
    names={base:(base if suffix==1 else f'{base}_{suffix:02d}') for base in OFFICIAL_SHEETS}
    hc=wb[names['HC']]
    _fill_hc(hc,patient,h)
    _fill_interconsult(wb[names['INTER007']],h.get('data') or {},h)
    _fill_referral(wb[names['REF053']],h.get('data') or {})
    _mark_lab_tests(wb[names['LAB010']],(h.get('data') or {}).get('lab_tests'))
    lab=wb[names['LAB010']]
    lab['A12']=(h.get('data') or {}).get('lab_treatment') or ''
    lab['A13']=(h.get('data') or {}).get('other_lab_tests') or ''
    _fill_imaging(wb[names['IMA012']],h.get('data') or {})
    _fill_recipe(wb[names['RECETA']],patient,h.get('data') or {},h)
    return names


def clinical_excel(patient,histories):
    finished=_finalized(histories)
    wb=load_workbook(ISSFA_TEMPLATE)
    # El formulario oficial es una atención por juego de hojas. Si el expediente
    # tiene varias atenciones, se conservan todas en juegos numerados.
    if not finished:
        out=io.BytesIO(); wb.save(out); return out.getvalue()
    # Crear primero todos los juegos secundarios desde la plantilla todavía intacta;
    # así una atención no arrastra datos de otra.
    for i in range(2,len(finished)+1):
        names={base:(base if i==1 else f'{base}_{i:02d}') for base in OFFICIAL_SHEETS}
        for base,new_name in names.items():
            source=wb[base]
            copy=wb.copy_worksheet(source)
            copy.title=new_name
            for row in copy.iter_rows():
                for cell in row:
                    if isinstance(cell.value,str) and cell.value.startswith('='):
                        cell.value=cell.value.replace('HC!',f"'{names['HC']}'!")
    for i,h in enumerate(finished,1):
        _populate_official_group(wb,i,patient,h)
    wb.active=wb.sheetnames.index('HC')
    try:
        wb.calculation.fullCalcOnLoad=True
        wb.calculation.forceFullCalc=True
        wb.calculation.calcMode='auto'
    except Exception:
        pass
    out=io.BytesIO(); wb.save(out); return out.getvalue()

def clinical_pdf(patient,histories):
    out=io.BytesIO(); doc=SimpleDocTemplate(out,pagesize=A4,rightMargin=1.1*cm,leftMargin=1.1*cm,topMargin=1.15*cm,bottomMargin=1.15*cm)
    styles=getSampleStyleSheet(); styles.add(ParagraphStyle(name='ClinicalTitle',parent=styles['Title'],fontName='Helvetica-Bold',fontSize=17,textColor=colors.HexColor('#0F4C5C'),alignment=TA_CENTER,spaceAfter=7)); styles.add(ParagraphStyle(name='Section',parent=styles['Heading2'],fontName='Helvetica-Bold',fontSize=9.5,textColor=colors.white,backColor=colors.HexColor('#147D92'),borderPadding=4,spaceBefore=5,spaceAfter=2)); body=styles['BodyText']; body.fontName='Helvetica'; body.fontSize=8; body.leading=9.5
    story=[Paragraph('HISTORIA CLÍNICA',styles['ClinicalTitle'])]
    ptable=Table([[Paragraph(f'<b>{escape(label)}</b>',body),Paragraph(escape(pretty(value)),body)] for label,value in [('Paciente',proper_name(patient.get('name'))),('Documento / historia clínica',patient.get('document')),('Sexo',patient.get('sex')),('Fecha de nacimiento',patient.get('birth_date')),('Teléfono',patient.get('phone')),('Dirección',patient.get('address')),('Cobertura',patient.get('coverage'))]],colWidths=[5.2*cm,12.2*cm])
    ptable.setStyle(TableStyle([('BACKGROUND',(0,0),(0,-1),colors.HexColor('#EAF4F5')),('TEXTCOLOR',(0,0),(0,-1),colors.HexColor('#0F4C5C')),('GRID',(0,0),(-1,-1),.35,colors.HexColor('#D5E3E7')),('VALIGN',(0,0),(-1,-1),'TOP'),('LEFTPADDING',(0,0),(-1,-1),5),('RIGHTPADDING',(0,0),(-1,-1),5)])); story+=[ptable,Spacer(1,10)]
    finished=_finalized(histories)
    if not finished: story.append(Paragraph('No hay consultas finalizadas.',body))
    for idx,h in enumerate(finished):
        if idx: story.append(PageBreak())
        story.append(Paragraph(f"Atención {pretty(h['occurred_at'])}",styles['Heading1']))
        meta=Table([[Paragraph('<b>Médico</b>',body),Paragraph(proper_name(h.get('doctor')),body),Paragraph('<b>Especialidad</b>',body),Paragraph(pretty(h.get('specialty')),body)],[Paragraph('<b>Tipo</b>',body),Paragraph(pretty(h.get('consultation_type')),body),Paragraph('<b>Documento profesional</b>',body),Paragraph(pretty(h.get('professional_id')),body)]],colWidths=[2.6*cm,5.7*cm,3.4*cm,5.7*cm]); meta.setStyle(TableStyle([('GRID',(0,0),(-1,-1),.35,colors.HexColor('#D5E3E7')),('VALIGN',(0,0),(-1,-1),'TOP'),('BACKGROUND',(0,0),(0,-1),colors.HexColor('#EAF4F5')),('BACKGROUND',(2,0),(2,-1),colors.HexColor('#EAF4F5'))])); story+=[meta,Spacer(1,4)]
        for title,items in _encounter_rows(h.get('data') or {}):
            rows=[[Paragraph(f'<b>{escape(label)}</b>',body),Paragraph(escape(value).replace('\n','<br/>'),body)] for label,value in items]
            table=Table(rows,colWidths=[5.3*cm,12.1*cm],repeatRows=0); table.setStyle(TableStyle([('GRID',(0,0),(-1,-1),.3,colors.HexColor('#D5E3E7')),('BACKGROUND',(0,0),(0,-1),colors.HexColor('#F3F7FA')),('VALIGN',(0,0),(-1,-1),'TOP'),('LEFTPADDING',(0,0),(-1,-1),4),('RIGHTPADDING',(0,0),(-1,-1),4)])); story += [Paragraph(title,styles['Section']),table]
        story += [Spacer(1,5),Paragraph(f"Profesional responsable: {proper_name(h.get('doctor'))} · Registro: {pretty(h.get('registration'))}",body),Spacer(1,10),Paragraph('Firma y sello: ______________________________________________',body)]
    def footer(canvas,doc):
        canvas.saveState(); canvas.setFont('Helvetica',7); canvas.setFillColor(colors.HexColor('#506670')); canvas.drawString(1.3*cm,.65*cm,'Medisuport · Documento clínico confidencial'); canvas.drawRightString(19.7*cm,.65*cm,f'Página {doc.page}'); canvas.restoreState()
    doc.build(story,onFirstPage=footer,onLaterPages=footer); return out.getvalue()
def word_history(patient,histories):
    d=Document()
    style=d.styles['Normal']; style.font.name='Arial'; style.font.size=Pt(10)
    for section in d.sections:
        section.header.paragraphs[0].text='MEDISUPORT · HISTORIA CLÍNICA'
        section.left_margin=section.right_margin=Inches(.8)
        section.footer.paragraphs[0].text='Documento confidencial · Copia exportada del sistema'
    d.add_heading('Expediente clínico',0)
    for key,label in [('name','Paciente'),('document','Documento'),('sex','Sexo'),('birth_date','Nacimiento'),('phone','Teléfono'),('email','Correo'),('address','Dirección'),('occupation','Ocupación'),('coverage','Cobertura')]:
        value=proper_name(patient.get(key)) if key=='name' else pretty(patient.get(key))
        p=d.add_paragraph(); p.add_run(label+': ').bold=True; p.add_run(value)
    for h in histories:
        if h['status']!='Finalizada': continue
        d.add_heading(f"Atención · {pretty(h['occurred_at'])}",1)
        d.add_paragraph(f"Médico: {proper_name(h['doctor'])} · Especialidad: {pretty(h.get('specialty'))} · Tipo: {h['consultation_type']}")
        for title,items in _encounter_rows(h.get('data') or {}):
            d.add_heading(title.title(),2)
            for label,value in items:
                p=d.add_paragraph(); p.add_run(label+': ').bold=True; p.add_run(value)
        for a in h.get('amendments',[]):
            d.add_heading('Nota adicional / corrección',2)
            d.add_paragraph(f"{pretty(a['created_at'])} · {proper_name(a['author'])}\nMotivo: {a['reason']}\n{a['text']}")
    if not any(h['status']=='Finalizada' for h in histories): d.add_paragraph('No hay consultas finalizadas.')
    out=io.BytesIO(); d.save(out); return out.getvalue()

def _certificate_age(birth,issued):
    if not birth: return None
    day=issued.date() if isinstance(issued,datetime) else issued
    return day.year-birth.year-((day.month,day.day)<(birth.month,birth.day))

def certificate_pdf(c):
    out=io.BytesIO(); doc=SimpleDocTemplate(out,pagesize=A4,rightMargin=2.1*cm,leftMargin=2.1*cm,topMargin=1.7*cm,bottomMargin=1.6*cm)
    styles=getSampleStyleSheet()
    styles.add(ParagraphStyle(name='CertHead',parent=styles['Title'],fontName='Helvetica-Bold',fontSize=16,textColor=colors.HexColor('#0F4C5C'),alignment=TA_CENTER,spaceAfter=4))
    styles.add(ParagraphStyle(name='CertSub',parent=styles['Normal'],fontName='Helvetica-Bold',fontSize=10,textColor=colors.HexColor('#147D92'),alignment=TA_CENTER,spaceAfter=18))
    body=ParagraphStyle(name='CertBody',parent=styles['BodyText'],fontName='Helvetica',fontSize=11,leading=18,alignment=0)
    issued=c['issued_at'].astimezone(TZ); age=_certificate_age(c.get('birth_date'),issued)
    number=f"CM-{issued.year}-{int(c['id']):06d}"
    patient=proper_name(c.get('patient')); doctor=proper_name(c.get('doctor'))
    rest=''
    if c.get('rest_from') and c.get('rest_to'):
        days=(c['rest_to']-c['rest_from']).days+1
        rest=f"Se recomienda reposo médico desde el <b>{pretty(c['rest_from'])}</b> hasta el <b>{pretty(c['rest_to'])}</b>, por un total de <b>{days} día(s)</b>."
    story=[Paragraph(escape(c.get('institution') or 'Establecimiento de salud'),styles['CertHead']),Paragraph('CERTIFICADO MÉDICO',styles['CertSub']),
           Paragraph(f"<b>Certificado N.º:</b> {number}",body),Spacer(1,10),
           Paragraph(f"Yo, <b>{escape(doctor)}</b>, certifico que el/la paciente <b>{escape(patient)}</b>, identificado(a) con documento <b>{escape(str(c.get('document') or ''))}</b>{(' de <b>'+str(age)+' años</b>') if age is not None else ''}, fue valorado(a) el <b>{issued.strftime('%d/%m/%Y')}</b>.",body),Spacer(1,8),
           Paragraph(f"<b>Diagnóstico:</b> {escape(c.get('diagnosis') or '')}",body)]
    if c.get('cie10'): story.append(Paragraph(f"<b>Código CIE-10:</b> {escape(c['cie10'])}",body))
    if rest: story += [Spacer(1,8),Paragraph(rest,body)]
    if c.get('observations'): story += [Spacer(1,8),Paragraph(f"<b>Indicaciones u observaciones:</b> {escape(c['observations']).replace(chr(10),'<br/>')}",body)]
    story += [Spacer(1,14),Paragraph('Se emite el presente certificado a petición del interesado para los fines que estime pertinentes.',body),Spacer(1,12),Paragraph(f"{escape(c.get('location') or '')}, {issued.strftime('%d de %m de %Y')}",body),Spacer(1,55),Paragraph('________________________________________',body),Paragraph(f"<b>{escape(doctor)}</b><br/>{escape(c.get('specialty') or '')}<br/>Documento profesional: {escape(str(c.get('professional_id') or ''))}<br/>Registro profesional: {escape(str(c.get('registration') or ''))}<br/>Firma y sello",body)]
    def footer(canvas,doc):
        canvas.saveState(); canvas.setStrokeColor(colors.HexColor('#147D92')); canvas.line(2.1*cm,1.15*cm,18.9*cm,1.15*cm); canvas.setFont('Helvetica',7); canvas.setFillColor(colors.HexColor('#506670')); canvas.drawString(2.1*cm,.8*cm,'Documento clínico generado por Medisuport'); canvas.drawRightString(18.9*cm,.8*cm,number); canvas.restoreState()
    doc.build(story,onFirstPage=footer,onLaterPages=footer); return out.getvalue()

def certificate_word(c):
    d=Document(); normal=d.styles['Normal']; normal.font.name='Arial'; normal.font.size=Pt(11)
    for section in d.sections:
        section.left_margin=section.right_margin=Inches(.85)
        section.footer.paragraphs[0].text=f"Medisuport · Certificado CM-{c['issued_at'].astimezone(TZ).year}-{int(c['id']):06d}"
    issued=c['issued_at'].astimezone(TZ); age=_certificate_age(c.get('birth_date'),issued); doctor=proper_name(c.get('doctor')); patient=proper_name(c.get('patient'))
    p=d.add_paragraph(); p.alignment=1; r=p.add_run(c.get('institution') or 'Establecimiento de salud'); r.bold=True; r.font.size=Pt(16); r.font.color.rgb=RGBColor(15,76,92)
    p=d.add_paragraph(); p.alignment=1; r=p.add_run('CERTIFICADO MÉDICO'); r.bold=True; r.font.size=Pt(14)
    d.add_paragraph(f"Certificado N.º CM-{issued.year}-{int(c['id']):06d}")
    text=f"Yo, {doctor}, certifico que el/la paciente {patient}, identificado(a) con documento {c.get('document') or ''}"
    if age is not None: text+=f", de {age} años"
    text+=f", fue valorado(a) el {issued.strftime('%d/%m/%Y')}."
    d.add_paragraph(text); d.add_paragraph(f"Diagnóstico: {c.get('diagnosis') or ''}")
    if c.get('cie10'): d.add_paragraph(f"Código CIE-10: {c['cie10']}")
    if c.get('rest_from') and c.get('rest_to'):
        days=(c['rest_to']-c['rest_from']).days+1; d.add_paragraph(f"Se recomienda reposo médico desde el {pretty(c['rest_from'])} hasta el {pretty(c['rest_to'])}, por un total de {days} día(s).")
    if c.get('observations'): d.add_paragraph(f"Indicaciones u observaciones: {c['observations']}")
    d.add_paragraph('Se emite el presente certificado a petición del interesado para los fines que estime pertinentes.')
    d.add_paragraph(f"{c.get('location') or ''}, {issued.strftime('%d/%m/%Y')}"); d.add_paragraph('\n\n________________________________________')
    d.add_paragraph(f"{doctor}\n{c.get('specialty') or ''}\nDocumento profesional: {c.get('professional_id') or ''}\nRegistro profesional: {c.get('registration') or ''}\nFirma y sello")
    out=io.BytesIO(); d.save(out); return out.getvalue()
def excel(sheets):
    out=io.BytesIO()
    with pd.ExcelWriter(out,engine='openpyxl') as writer:
        for name,rows in sheets.items():
            data=[]
            for row in rows:
                converted={}
                for k,v in row.items():
                    if isinstance(v,datetime): v=v.astimezone(TZ).strftime('%Y-%m-%d %H:%M:%S')
                    elif isinstance(v,(dict,list,tuple)): v=str(v)
                    elif isinstance(v,Decimal): v=float(v)
                    if isinstance(v,str) and v.startswith(('=','+','-','@')): v="'"+v
                    converted[k]=v
                data.append(converted)
            pd.DataFrame(data).to_excel(writer,sheet_name=name[:31],index=False)
            sheet=writer.sheets[name[:31]]; sheet.freeze_panes='A2'
            sheet.auto_filter.ref=sheet.dimensions
            sheet.sheet_view.showGridLines=False
            sheet.auto_filter.ref=sheet.dimensions
            header_fill=PatternFill('solid',fgColor='0F4C5C')
            stripe_fill=PatternFill('solid',fgColor='EAF4F5')
            edge=Side(style='thin',color='D5E3E7')
            for cell in sheet[1]:
                cell.fill=header_fill
                cell.font=Font(color='FFFFFF',bold=True)
                cell.alignment=Alignment(horizontal='center',vertical='center')
                cell.border=Border(bottom=edge)
            sheet.row_dimensions[1].height=24
            for row_index,row in enumerate(sheet.iter_rows(min_row=2),start=2):
                for cell in row:
                    if row_index%2==0: cell.fill=stripe_fill
                    cell.alignment=Alignment(vertical='top',wrap_text=True)
                    cell.border=Border(bottom=edge)
            for col in sheet.columns:
                sheet.column_dimensions[col[0].column_letter].width=min(55,max(14,max(len(str(c.value or '')) for c in col)+2))
            sheet.page_setup.orientation='landscape'
            sheet.page_setup.fitToWidth=1
            sheet.sheet_properties.pageSetUpPr.fitToPage=True
            sheet.auto_filter.ref=sheet.dimensions
    return out.getvalue()

def billing_statement_pdf(inv):
    """Estado de cuenta imprimible; expresamente no es comprobante tributario."""
    out=io.BytesIO(); doc=SimpleDocTemplate(out,pagesize=A4,rightMargin=1.6*cm,leftMargin=1.6*cm,topMargin=1.5*cm,bottomMargin=1.5*cm)
    styles=getSampleStyleSheet(); title=ParagraphStyle('BillTitle',parent=styles['Title'],textColor=colors.HexColor('#0F4C5C'),fontSize=18,leading=22)
    normal=ParagraphStyle('BillBody',parent=styles['BodyText'],fontSize=9.5,leading=13)
    story=[Paragraph('MEDISUPORT',title),Paragraph('ESTADO DE CUENTA INTERNO · NO ES COMPROBANTE TRIBUTARIO',styles['Heading3']),Spacer(1,8)]
    head=[[Paragraph('<b>Cuenta</b>',normal),inv.get('number',''),Paragraph('<b>Fecha</b>',normal),pretty(inv.get('issue_date'))],
          [Paragraph('<b>Paciente</b>',normal),proper_name(inv.get('patient')),Paragraph('<b>Documento</b>',normal),str(inv.get('document') or '')],
          [Paragraph('<b>Convenio</b>',normal),inv.get('agreement') or 'Particular',Paragraph('<b>Vencimiento</b>',normal),pretty(inv.get('due_date'))]]
    table=Table(head,colWidths=[2.6*cm,6.0*cm,2.6*cm,5.0*cm]); table.setStyle(TableStyle([('GRID',(0,0),(-1,-1),.4,colors.HexColor('#DCE7EC')),('BACKGROUND',(0,0),(0,-1),colors.HexColor('#EAF4F5')),('BACKGROUND',(2,0),(2,-1),colors.HexColor('#EAF4F5')),('VALIGN',(0,0),(-1,-1),'MIDDLE'),('PADDING',(0,0),(-1,-1),6)])); story += [table,Spacer(1,12)]
    rows=[['Servicio','Cant.','P. unitario','Descuento','Impuesto','Total']]
    for item in inv.get('items',[]): rows.append([item['description'],f"{item['quantity']:.2f}",f"${item['unit_price']:,.2f}",f"${item['discount']:,.2f}",f"${item['tax']:,.2f}",f"${item['total']:,.2f}"])
    details=Table(rows,colWidths=[6.6*cm,1.6*cm,2.7*cm,2.4*cm,2.2*cm,2.4*cm],repeatRows=1)
    details.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#0F4C5C')),('TEXTCOLOR',(0,0),(-1,0),colors.white),('FONTNAME',(0,0),(-1,0),'Helvetica-Bold'),('ALIGN',(1,1),(-1,-1),'RIGHT'),('GRID',(0,0),(-1,-1),.35,colors.HexColor('#DCE7EC')),('VALIGN',(0,0),(-1,-1),'TOP'),('FONTSIZE',(0,0),(-1,-1),8.5),('PADDING',(0,0),(-1,-1),5)])); story += [details,Spacer(1,10)]
    paid=inv.get('paid') or Decimal('0'); balance=inv['total']-paid
    totals=[['Subtotal',f"${inv['subtotal']:,.2f}"],['Descuento',f"-${inv['discount']:,.2f}"],['Impuesto',f"${inv['tax']:,.2f}"],['TOTAL',f"${inv['total']:,.2f}"],['Cobrado',f"${paid:,.2f}"],['SALDO',f"${balance:,.2f}"]]
    summary=Table(totals,colWidths=[3.4*cm,3.2*cm],hAlign='RIGHT'); summary.setStyle(TableStyle([('ALIGN',(1,0),(1,-1),'RIGHT'),('FONTNAME',(0,3),(-1,3),'Helvetica-Bold'),('FONTNAME',(0,-1),(-1,-1),'Helvetica-Bold'),('LINEABOVE',(0,3),(-1,3),.7,colors.HexColor('#0F4C5C')),('BACKGROUND',(0,-1),(-1,-1),colors.HexColor('#EAF4F5')),('PADDING',(0,0),(-1,-1),5)])); story += [summary,Spacer(1,8)]
    story.append(Paragraph(f"Responsabilidad del paciente: ${inv['patient_responsibility']:,.2f} · Responsabilidad del convenio: ${inv['agreement_responsibility']:,.2f}",normal))
    if inv.get('notes'): story += [Spacer(1,6),Paragraph('<b>Observaciones:</b> '+escape(inv['notes']).replace(chr(10),'<br/>'),normal)]
    doc.build(story); return out.getvalue()
