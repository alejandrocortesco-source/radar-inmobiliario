"""Destinos de operador; un perfil aislado incompleto nunca utiliza defaults productivos."""
import os,re
from types import SimpleNamespace

def settings():
    env=os.environ
    mode=env.get('RADAR_ENV','production')
    if mode not in {'production','isolated'}:raise ValueError('Entorno inválido')
    project=env.get('RADAR_PROJECT','radar-inmobiliario-co')
    region=env.get('RADAR_REGION','us-central1')
    if mode=='production' and (project!='radar-inmobiliario-co' or region!='us-central1'):
        raise ValueError('Un destino alternativo exige configuración aislada completa')
    if mode=='isolated':
        required=['RADAR_PROJECT','RADAR_REGION','RADAR_PROJECT_NUMBER','RADAR_STATE_BUCKET','RADAR_STATE_OBJECT','RADAR_CONTROL_OBJECT','RADAR_EXECUTION_JOB','RADAR_SCHEDULE_TARGET','RADAR_SCHEDULE_CALLER','RADAR_WEB_CALLER','RADAR_PUBLIC_ORIGIN']
        if any(not env.get(k) for k in required):raise ValueError('Configuración aislada incompleta')
        number=env['RADAR_PROJECT_NUMBER']
        if not re.fullmatch(r'radar-test-[a-z0-9-]+',project) or not number.isdigit() or number=='56106530298':raise ValueError('Proyecto aislado inválido')
        if region!='us-central1' or not env['RADAR_STATE_BUCKET'].startswith(project+'-'):raise ValueError('Almacenamiento aislado inválido')
        if env['RADAR_EXECUTION_JOB']!='radar-manual-review':raise ValueError('Job aislado inválido')
        for key in ['RADAR_SCHEDULE_CALLER','RADAR_WEB_CALLER']:
            if not re.fullmatch(r'[a-z0-9-]+@'+re.escape(project)+r'\.iam\.gserviceaccount\.com',env[key]):raise ValueError('Identidad ajena al entorno')
        if env['RADAR_PUBLIC_ORIGIN']!=f'https://radar-web-{number}.{region}.run.app' or env['RADAR_SCHEDULE_TARGET']!=f'https://radar-schedule-review-{number}.{region}.run.app':raise ValueError('URL ajena al entorno')
        if env.get('RADAR_SYNTHETIC_DATA')!='1':raise ValueError('El entorno aislado requiere datos sintéticos')
    return SimpleNamespace(isolated=mode=='isolated',project=project,region=region,parent=f'projects/{project}/locations/{region}',
        caller=env.get('RADAR_SCHEDULE_CALLER',f'radar-scheduler@{project}.iam.gserviceaccount.com'))
