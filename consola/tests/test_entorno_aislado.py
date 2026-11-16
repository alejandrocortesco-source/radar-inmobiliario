import pytest

from ejecuciones.entorno import settings



@pytest.fixture

def isolated(monkeypatch):

    project='radar-test-unit';number='123456789'

    values=dict(RADAR_ENV='isolated',RADAR_PROJECT=project,RADAR_PROJECT_NUMBER=number,RADAR_REGION='us-central1',RADAR_STATE_BUCKET=project+'-data',RADAR_STATE_OBJECT='radar/state.tar.gz',RADAR_CONTROL_OBJECT='radar/executions/control.json',RADAR_EXECUTION_JOB='radar-manual-review',RADAR_SCHEDULE_TARGET=f'https://radar-schedule-review-{number}.us-central1.run.app',RADAR_SCHEDULE_CALLER=f'dispatch@{project}.iam.gserviceaccount.com',RADAR_WEB_CALLER=f'dispatch@{project}.iam.gserviceaccount.com',RADAR_PUBLIC_ORIGIN=f'https://radar-web-{number}.us-central1.run.app',RADAR_SYNTHETIC_DATA='1')

    for k,v in values.items():monkeypatch.setenv(k,v)

    return values



def test_isolated_resources_are_local(isolated):

    from ejecuciones.cloud_run import CloudRun

    from ejecuciones.scheduler import Scheduler

    c=CloudRun(session=object());s=Scheduler(session=object())

    assert c.name.startswith('projects/radar-test-unit/') and s.name.startswith('projects/radar-test-unit/')

    assert s.account=='dispatch@radar-test-unit.iam.gserviceaccount.com'



@pytest.mark.parametrize('key',['RADAR_PROJECT','RADAR_PROJECT_NUMBER','RADAR_REGION','RADAR_STATE_BUCKET','RADAR_STATE_OBJECT','RADAR_CONTROL_OBJECT','RADAR_EXECUTION_JOB','RADAR_SCHEDULE_TARGET','RADAR_SCHEDULE_CALLER','RADAR_WEB_CALLER','RADAR_PUBLIC_ORIGIN','RADAR_SYNTHETIC_DATA'])

def test_missing_rejects_before_client_creation(isolated,monkeypatch,key):

    from ejecuciones.control import ControlGCS

    monkeypatch.delenv(key)

    with pytest.raises(ValueError):ControlGCS(client=object())



@pytest.mark.parametrize('key,value',[('RADAR_PROJECT','radar-inmobiliario-co'),('RADAR_PROJECT_NUMBER','56106530298'),('RADAR_STATE_BUCKET','radar-inmobiliario-co-state'),('RADAR_SCHEDULE_CALLER','radar-scheduler@radar-inmobiliario-co.iam.gserviceaccount.com'),('RADAR_SCHEDULE_TARGET','https://radar-schedule-review-56106530298.us-central1.run.app')])

def test_productive_values_rejected(isolated,monkeypatch,key,value):

    monkeypatch.setenv(key,value)

    with pytest.raises(ValueError):settings()



@pytest.mark.parametrize('source',['metrocuadrado','wasi','fincaraiz'])

def test_synthetic_input_uses_real_store(isolated,tmp_path,source):

    import asyncio

    from ejecuciones.datos_sinteticos import SyntheticScraper

    from ejecuciones.worker import metrics

    scraper=SyntheticScraper(tmp_path,dict(fuente=source,id_busqueda='synthetic:'+source))

    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=1) as pool:
        assert pool.submit(lambda:asyncio.run(scraper.run())).result()['status']=='completed'

    assert metrics(scraper)['listing_complete']





def test_synthetic_failure(isolated,tmp_path):

    import asyncio

    from ejecuciones.datos_sinteticos import SyntheticScraper

    with pytest.raises(ValueError,match='Fallo sintético'):

        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=1) as pool:
            pool.submit(lambda:asyncio.run(SyntheticScraper(tmp_path,dict(fuente='wasi',id_busqueda='synthetic:error')).run())).result()



@pytest.mark.parametrize('identity,origin,expected',[('allowed',True,200),('wrong',True,401),('allowed',False,403)])

def test_isolated_web_auth_and_origin(isolated,monkeypatch,identity,origin,expected):

    from starlette.testclient import TestClient

    from starlette.responses import JSONResponse

    from consola.acceso import AccesoRadar

    async def app(scope,receive,send):await JSONResponse({'ok':True})(scope,receive,send)

    monkeypatch.setenv('RADAR_AUTH_MODE','oidc')

    monkeypatch.setattr('google.oauth2.id_token.verify_oauth2_token',lambda *a,**k:dict(email=isolated['RADAR_WEB_CALLER'] if identity=='allowed' else 'other@test',email_verified=True))

    response=TestClient(AccesoRadar(app)).post('/test',headers={'Authorization':'Bearer signed-test','Origin':isolated['RADAR_PUBLIC_ORIGIN'] if origin else 'https://wrong.invalid'})

    assert response.status_code==expected

