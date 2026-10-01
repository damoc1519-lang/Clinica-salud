"""Documentos Word y reportes Excel bajo los permisos del backend."""
import io
from html import escape
from datetime import datetime,date,time
from decimal import Decimal
import pandas as pd
from docx import Document
from docx.shared import Inches,Pt,RGBColor
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl import Workbook
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

def clinical_excel(patient,histories):
    wb=Workbook(); ws=wb.active; ws.title='Paciente'; ws.sheet_view.showGridLines=False
    navy='0F4C5C'; teal='147D92'; light='EAF4F5'; edge=Side(style='thin',color='D5E3E7')
    ws.merge_cells('A1:D1'); ws['A1']='HISTORIA CLÍNICA'; ws['A1'].fill=PatternFill('solid',fgColor=navy); ws['A1'].font=Font(color='FFFFFF',bold=True,size=16); ws['A1'].alignment=Alignment(horizontal='center')
    patient_rows=[('Paciente',proper_name(patient.get('name'))),('Documento / historia clínica',patient.get('document')),('Sexo',patient.get('sex')),('Fecha de nacimiento',pretty(patient.get('birth_date'))),('Teléfono',patient.get('phone')),('Correo',patient.get('email')),('Dirección',patient.get('address')),('Ocupación',patient.get('occupation')),('Cobertura',patient.get('coverage'))]
    for r,(label,value) in enumerate(patient_rows,3): ws.cell(r,1,label); ws.cell(r,2,pretty(value)); ws.cell(r,1).font=Font(bold=True,color=navy)
    ws.column_dimensions['A'].width=31; ws.column_dimensions['B'].width=70
    for index,h in enumerate(_finalized(histories),1):
        sh=wb.create_sheet(f'Atención {index}'); sh.sheet_view.showGridLines=False; sh.merge_cells('A1:D1'); sh['A1']=f"ATENCIÓN {pretty(h['occurred_at'])}"; sh['A1'].fill=PatternFill('solid',fgColor=navy); sh['A1'].font=Font(color='FFFFFF',bold=True,size=14); sh['A1'].alignment=Alignment(horizontal='center')
        meta=[('Paciente',proper_name(patient.get('name'))),('Documento',patient.get('document')),('Médico',proper_name(h.get('doctor'))),('Especialidad',h.get('specialty')),('Tipo de consulta',h.get('consultation_type')),('Documento profesional',h.get('professional_id')),('Registro profesional',h.get('registration'))]
        row=3
        for label,value in meta: sh.cell(row,1,label).font=Font(bold=True,color=navy); sh.cell(row,2,pretty(value)); row+=1
        row+=1
        for title,items in _encounter_rows(h.get('data') or {}):
            sh.merge_cells(start_row=row,start_column=1,end_row=row,end_column=4); cell=sh.cell(row,1,title); cell.fill=PatternFill('solid',fgColor=teal); cell.font=Font(color='FFFFFF',bold=True); row+=1
            for label,value in items:
                sh.cell(row,1,label).font=Font(bold=True,color=navy); sh.merge_cells(start_row=row,start_column=2,end_row=row,end_column=4); sh.cell(row,2,value); sh.cell(row,2).alignment=Alignment(wrap_text=True,vertical='top'); row+=1
            row+=1
        sh.column_dimensions['A'].width=34; sh.column_dimensions['B'].width=34; sh.column_dimensions['C'].width=22; sh.column_dimensions['D'].width=22
        for cells in sh.iter_rows(min_row=3,max_row=row,max_col=4):
            for cell in cells: cell.border=Border(bottom=edge); cell.alignment=Alignment(wrap_text=True,vertical='top')
        sh.freeze_panes='A3'; sh.page_setup.fitToWidth=1; sh.sheet_properties.pageSetUpPr.fitToPage=True
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
