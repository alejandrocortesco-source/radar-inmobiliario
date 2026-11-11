"""Diagnóstico HTTP sin red ni credenciales reales."""
import json
import httpx
import pytest
from oportunidades.gemini import Gemini, Respuesta, error_saneado, esquema_proveedor
from oportunidades.automatizacion import candidato, solicitar_gemini
from oportunidades.matching import comparar
from metro.web import servicio
from test_v03 import necesidades, inmueble
from test_v06 import escenario06


@pytest.mark.parametrize('cuerpo', [b'no-json privado', b'null', b'{}', b'{"error":null}', b'{"error":{"details":null}}', b'x'*65537], ids=['texto','null','objeto','sin_error','details_nulos','grande'])
def test_error_incompleto_sin_cuerpo_crudo(cuerpo):
    r = httpx.Response(400, content=cuerpo)
    datos = error_saneado(r, 'secreto', [])
    assert isinstance(datos, dict) and 'privado' not in json.dumps(datos)


def test_diagnostico_sanea_campos_y_no_guarda_metadata_arbitraria():
    mensaje = 'Invalid parameter generationConfig.responseJsonSchema key=clave-sintetica correo@ejemplo.com 3001234567 Cliente Privado'
    r = httpx.Response(400, json={'error':{'code':400,'status':'INVALID_ARGUMENT','message':mensaje,
        'details':[{'fieldViolations':[{'field':'generationConfig.responseJsonSchema','description':mensaje}],
                    'reason':'INVALID_SCHEMA', 'domain':'generativelanguage.googleapis.com',
                    'metadata':{'authorization':'credencial', 'parameter':'responseJsonSchema'}}]}, 'prompt':'NO CONSERVAR'})
    datos = error_saneado(r, 'clave-sintetica', ['Cliente Privado'])
    texto = json.dumps(datos)
    for privado in ('clave-sintetica','correo@ejemplo.com','3001234567','Cliente Privado','NO CONSERVAR','credencial'):
        assert privado not in texto
    assert datos['code'] == 400 and datos['status'] == 'INVALID_ARGUMENT'
    assert datos['parametros'][0]['field'] == 'generationConfig.responseJsonSchema'
    assert datos['motivos'][0]['reason'] == 'INVALID_SCHEMA'
    assert datos['motivos'][0]['parameter'] == 'responseJsonSchema'
    assert len(datos['message']) <= 800


def test_400_persistido_no_evaluaciones_falsas_y_un_solo_envio(escenario06, monkeypatch):
    _, s, o, repo = escenario06
    monkeypatch.setenv('GEMINI_API_KEY','clave-sintetica')
    llamadas = []
    def responder(req):
        llamadas.append(req)
        cuerpo = json.loads(req.content)
        assert req.url.path == '/v1beta/models/gemini-3.8-flash:generateContent'
        assert req.headers['content-type'] == 'application/json'
        config = cuerpo['generationConfig']
        assert config['maxOutputTokens'] == 12000
        assert config['thinkingConfig'] == {'thinkingLevel':'LOW'}
        assert config['responseMimeType'] == 'application/json'
        assert config['responseJsonSchema'] == esquema_proveedor()
        assert 'responseFormat' not in config
        return httpx.Response(400, headers={'x-request-id':'request-sintetico'}, json={'error':{
            'code':400,'status':'INVALID_ARGUMENT','message':'Invalid parameter generationConfig.responseJsonSchema'}})
    real = httpx.Client
    monkeypatch.setattr(httpx, 'Client', lambda **kw: real(transport=httpx.MockTransport(responder), **kw))
    from uuid import uuid4
    tarea = solicitar_gemini(s, servicio(), o.id, str(uuid4()))
    tarea()
    datos = repo.ultima_gemini(o.id)['datos']
    assert len(llamadas) == 1 and datos['solicitudes'] == 1
    assert datos['http'] == 400 and datos['resultado'] == 'proveedor'
    assert datos['error']['status'] == 'INVALID_ARGUMENT'
    assert datos['x_request_id'] == 'request-sintetico'
    assert not datos['evaluaciones'] and datos['consumo'] == 'no_reportado'
    assert repo.leer(o.id)['datos']['total'] == 10
    assert 'HTTP 400' in datos['aviso'] and 'clave-sintetica' not in json.dumps(datos)


def test_esquema_inline_conserva_entrada_sintetica_anterior(monkeypatch):
    """Compara lo recibido por httpx conservando el cuerpo ajeno al formato.

    La captura anterior usó estos mismos tres anuncios y la oportunidad aislada:
    .tmp/gemini-real-908b6ee9-9fb7-4817-bea7-36f0f194673b.
    Las huellas excluyen solo la declaración del formato, nunca instrucciones,
    candidatos, LOW ni maxOutputTokens. No se usa red ni se lee esa base aquí.
    """
    from dataclasses import replace
    from decimal import Decimal
    import hashlib
    from catalogo.modelos import Inmueble, Origen, Oferta, Operacion, TipoInmueble
    from oportunidades.modelos import Necesidades
    from oportunidades.matching import buscar
    monkeypatch.setenv('GEMINI_API_KEY', 'solo-simulacion-local')
    monkeypatch.setenv('GEMINI_MODEL', 'gemini-3.8-flash')
    n = Necesidades(operacion='compra', tipo='apartamento', ciudad='Bogotá', barrios=['La Carolina'],
                    presupuesto_max=Decimal('500000000'), habitaciones_min=2, banos_min=2)
    a = Inmueble(origen=Origen(fuente='metrocuadrado', id_original='gemini-sintetico-a'),
        tipo=TipoInmueble.APARTAMENTO, ciudad=n.ciudad, barrio=n.barrios[0], habitaciones=2, banos=2,
        area_construida_m2=Decimal('80'), area_privada_m2=Decimal('70'),
        ofertas=(Oferta(operacion=Operacion.VENTA, precio=Decimal('450000000')),))
    b = replace(a, origen=Origen(fuente='wasi', id_original='gemini-sintetico-b'), habitaciones=None)
    c = replace(a, origen=Origen(fuente='fincaraiz', id_original='gemini-sintetico-c'),
                ofertas=(Oferta(operacion=Operacion.VENTA, precio=Decimal('500000001')),))
    resultados = buscar(n, [a, b, c])
    candidatos = [candidato(r) for r in resultados]
    llamadas = []
    def firma(datos):
        return hashlib.sha256(json.dumps(datos, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    def responder(req):
        llamadas.append(req)
        assert str(req.url) == 'https://generativelanguage.googleapis.com/v1beta/models/gemini-3.8-flash:generateContent'
        cuerpo = json.loads(req.content)
        config = cuerpo['generationConfig']
        assert set(config) == {'maxOutputTokens', 'thinkingConfig', 'responseMimeType', 'responseJsonSchema'}
        assert config.pop('responseMimeType') == 'application/json'
        schema = config.pop('responseJsonSchema')
        assert schema == esquema_proveedor()
        assert '$ref' not in json.dumps(schema) and 'additionalProperties' not in json.dumps(schema)
        assert 'minimum' not in json.dumps(schema) and 'maxLength' not in json.dumps(schema)
        assert schema['properties']['evaluaciones']['items']['required'] == ['id', 'puntuacion', 'explicacion', 'evidencias']
        # El contrato local conserva las restricciones que no viajan al proveedor.
        assert Respuesta.model_json_schema()['$defs']['Evaluacion']['properties']['puntuacion']['maximum'] == 100
        assert firma(cuerpo) == '1c8c28bb4110aebdf44dd2efbefec92bf81ed3a759a5dc2a0befda7f65262213'
        datos = {'evaluaciones': [{'id': x['id'], 'puntuacion': 80, 'explicacion': 'Ciudad documentada.',
                 'evidencias': [{'campo': 'ciudad', 'valor': x['hechos']['ciudad']}]} for x in candidatos]}
        return httpx.Response(200, json={'candidates': [{'finishReason': 'STOP', 'content': {'parts': [{'text': json.dumps(datos)}]}}]})
    real = httpx.Client
    monkeypatch.setattr(httpx, 'Client', lambda **kw: real(transport=httpx.MockTransport(responder), **kw))
    evaluaciones, aviso = Gemini().evaluar(n.model_dump(mode='json', exclude={'observaciones'}), candidatos)
    assert len(llamadas) == 1 and not aviso
    assert set(evaluaciones) == {a.id_interno, b.id_interno}
    assert c.id_interno not in evaluaciones and any(r.pendientes for r in resultados)


@pytest.mark.parametrize('cambio', [
    {'puntuacion':101}, {'puntuacion':80.5}, {'extra':'no admitido'},
    {'explicacion':'x'*801}, {'evidencias':[{'campo':'ciudad','valor':'Bogotá'}]*13}
], ids=['puntuacion','entero_estricto','extra','longitud','limite_evidencias'])
def test_restricciones_locales_intactas_con_schema_wire_simplificado(cambio):
    from pydantic import ValidationError
    datos = {'id':'sintetico','puntuacion':80,'explicacion':'Texto',
             'evidencias':[{'campo':'ciudad','valor':'Bogotá'}]} | cambio
    with pytest.raises(ValidationError):
        Respuesta.model_validate({'evaluaciones':[datos]})
