"""Herramientas locales: instalación, administrador inicial y restauración."""
import argparse, getpass, logging
from pathlib import Path
from core import Database,AppError

def main():
    parser=argparse.ArgumentParser(description='Administración de Medisuport')
    parser.add_argument('action',choices=['setup','restore'])
    parser.add_argument('backup',nargs='?')
    args=parser.parse_args()
    db=Database(); db.initialize()
    if args.action=='setup':
        if db.ready(): print('Base preparada. El administrador ya existe.'); return
        print('Cree su cuenta individual de administrador. Las claves antiguas no se usan.')
        username=input('Usuario administrador: ').strip()
        name=input('Nombre del administrador: ').strip()
        password=getpass.getpass('Contraseña nueva (mínimo 12 caracteres): ')
        if password!=getpass.getpass('Repita la contraseña: '): raise AppError('Las contraseñas no coinciden.')
        db.bootstrap(username,name,password)
        print('Configuración terminada. Ejecute: python -m streamlit run app.py')
    else:
        if not args.backup: raise AppError('Indique el archivo ZIP de respaldo.')
        if input('Se restaurará únicamente en un esquema vacío. Escriba RESTAURAR: ')!='RESTAURAR': return
        db.restore_empty(Path(args.backup).read_bytes()); print('Respaldo restaurado y registrado.')
if __name__=='__main__':
    try: main()
    except AppError as exc: print('No se completó:',exc); raise SystemExit(1)
    except Exception:
        logging.exception('Error de administración')
        print('No se completó. Revise el error anterior en esta terminal.'); raise SystemExit(1)
