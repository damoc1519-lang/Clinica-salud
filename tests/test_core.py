from datetime import date,time,datetime,timedelta
import unittest
from core import TZ,AppError,password_hash,password_ok,validate_patient,clinical_data,slots_for_day
from legacy import parse_schedule

class CoreTests(unittest.TestCase):
 def test_password_hash_is_salted_and_verifies(self):
    a=password_hash('ClaveSegura123'); b=password_hash('ClaveSegura123')
    assert a!=b and password_ok('ClaveSegura123',a) and not password_ok('otra',a)

 def test_patient_validation_normalizes_and_rejects_future_birth(self):
    p=validate_patient({'document':' 17 123 ','name':' Ana Ruiz ','birth_date':date(2000,1,1),'email':'a@b.ec'})
    assert p['document']=='17123' and p['name']=='Ana Ruiz'
    with self.assertRaises(AppError): validate_patient({'document':'1','name':'Ana','birth_date':date.today()+timedelta(days=1)})

 def test_clinical_data_keeps_habits_and_calculates_bmi(self):
    d=clinical_data({'habitos':'No fuma','motivo':'Dolor','diagnostico':'Control','peso':80,'talla':200,'fc':70},True)
    assert d['habitos']=='No fuma' and d['imc']==20

 def test_slots_remove_busy_blocked_and_past(self):
    day=date(2030,1,7) # lunes
    rule={'weekday':0,'start_time':time(8),'end_time':time(10)}
    busy={'start_at':datetime(2030,1,7,8,30,tzinfo=TZ),'end_at':datetime(2030,1,7,9,tzinfo=TZ)}
    block={'start_at':datetime(2030,1,7,9,tzinfo=TZ),'end_at':datetime(2030,1,7,9,30,tzinfo=TZ)}
    slots=slots_for_day(day,[rule],[busy],[block],30,datetime(2029,1,1,tzinfo=TZ))
    assert [s.strftime('%H:%M') for s in slots]==['08:00','09:30']

 def test_legacy_schedule_parser(self):
    days,start,end=parse_schedule('Lunes, Miércoles y Viernes','08:00 - 12:00')
    assert days==[0,2,4] and start==time(8) and end==time(12)

if __name__=='__main__': unittest.main()
