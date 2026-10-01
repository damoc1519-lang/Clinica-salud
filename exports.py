"""Documentos Word y reportes Excel bajo los permisos del backend."""
import io
from datetime import datetime,date,time
from decimal import Decimal
import pandas as pd
from docx import Document
from docx.shared import Inches,Pt,RGBColor
from core import TZ

LABELS={'antecedentes_pers':'Antecedentes personales','antecedentes_fam':'Antecedentes familiares','habitos':'Hábitos de vida','motivo':'Motivo de consulta','enfermedad_actual':'Enfermedad actual','peso':'Peso (kg)','talla':'Talla (cm)','pa':'Presión arterial','fc':'Frecuencia cardíaca','imc':'IMC','diagnostico':'Diagnóstico','tratamiento':'Tratamiento / indicaciones','examenes':'Exámenes complementarios'}
def pretty(value):
    if value is None or value=='': return 'No registrado'
    if isinstance(value,datetime): return value.astimezone(TZ).strftime('%d/%m/%Y %H:%M')
    if isinstance(value,date): return value.strftime('%d/%m/%Y')
    return str(value)
def word_history(patient,histories):
    d=Document()
    style=d.styles['Normal']; style.font.name='Arial'; style.font.size=Pt(10)
    for section in d.sections:
        section.header.paragraphs[0].text='MEDISUPORT · HISTORIA CLÍNICA'
        section.left_margin=section.right_margin=Inches(.8)
        section.footer.paragraphs[0].text='Documento confidencial · Copia exportada del sistema'
    d.add_heading('Expediente clínico',0)
    for key,label in [('name','Paciente'),('document','Documento'),('sex','Sexo'),('birth_date','Nacimiento'),('phone','Teléfono'),('email','Correo'),('address','Dirección'),('occupation','Ocupación'),('coverage','Cobertura')]:
        p=d.add_paragraph(); p.add_run(label+': ').bold=True; p.add_run(pretty(patient.get(key)))
    for h in histories:
        if h['status']!='Finalizada': continue
        d.add_heading(f"Atención · {pretty(h['occurred_at'])}",1)
        d.add_paragraph(f"Médico: {h['doctor']} · Especialidad: {pretty(h.get('specialty'))} · Tipo: {h['consultation_type']}")
        for key,label in LABELS.items():
            p=d.add_paragraph(); p.add_run(label+': ').bold=True; p.add_run(pretty(h['data'].get(key)))
        for a in h.get('amendments',[]):
            d.add_heading('Nota adicional / corrección',2)
            d.add_paragraph(f"{pretty(a['created_at'])} · {a['author']}\nMotivo: {a['reason']}\n{a['text']}")
    if not any(h['status']=='Finalizada' for h in histories): d.add_paragraph('No hay consultas finalizadas.')
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
            for col in sheet.columns:
                sheet.column_dimensions[col[0].column_letter].width=min(55,max(14,max(len(str(c.value or '')) for c in col)+2))
    return out.getvalue()
