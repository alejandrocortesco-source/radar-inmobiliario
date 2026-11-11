"""VALIDACIÓN REAL CON GEMINI: optativa, una generación, solo datos sintéticos.

No se importa desde pytest. Sin --ejecutar, sin clave o en CI no llama a Google.
"""
import argparse
from dataclasses import replace
from decimal import Decimal
import json
import os
from pathlib import Path
import sys
from uuid import uuid4

RAIZ = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(RAIZ), str(RAIZ / 'scraper')]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ejecutar', action='store_true', help='Autorizar una única generación real, con posible consumo.')
    args = parser.parse_args()
    if not args.ejecutar:
        print('No ejecutada: requiere --ejecutar y GEMINI_API_KEY en el entorno protegido.')
        return 0
    if os.getenv('CI'):
        print('No ejecutada: la validación real está desactivada en CI.')
        return 2
    if not os.getenv('GEMINI_API_KEY', '').strip():
        print('No ejecutada: falta GEMINI_API_KEY. No incluya claves en el chat ni en argumentos.')
        return 2

    from catalogo.modelos import Inmueble, Origen, Oferta, Operacion, TipoInmueble
    from oportunidades.modelos import Necesidades, ClienteDatos
    from oportunidades.persistencia import SQLite
    from oportunidades.servicio import ServicioOportunidades
    from oportunidades.seguimiento import SeguimientoSQLite
    from oportunidades.automatizacion import solicitar_gemini, recalcular, plan_gemini
    from oportunidades.gemini import Gemini

    class UnaGeneracion(Gemini):
        llamadas = 0

        def evaluar(self, necesidades, candidatos):
            self.llamadas += 1
            assert self.llamadas == 1 and len(candidatos) == 2, 'Se impidió una llamada adicional.'
            assert excluido.id_interno not in {c['id'] for c in candidatos}
            return super().evaluar(necesidades, candidatos)

    ia = UnaGeneracion()  # Valida modelo antes de crear datos o llamar a Google.
    salida = RAIZ / '.tmp' / ('gemini-real-' + str(uuid4()))
    salida.mkdir(parents=True, exist_ok=False)
    # Ignorar por completo cualquier base operativa heredada del proceso.
    os.environ.update(METRO_DB=str(salida / 'catalogo-vacio.sqlite'),
                      WASI_DB=str(salida / 'wasi-vacio.sqlite'),
                      FINCARAIZ_DB=str(salida / 'fincaraiz-vacio.sqlite'),
                      RADAR_CRM_DB=str(salida / 'crm.sqlite'), GEMINI_MAX_CANDIDATES='2')
    s = ServicioOportunidades(SQLite(salida / 'crm.sqlite'))
    n = Necesidades(operacion='compra', tipo='apartamento', ciudad='Bogotá', barrios=['La Carolina'],
                    presupuesto_max=Decimal('500000000'), habitaciones_min=2, banos_min=2)
    o = s.capturar(ClienteDatos(nombre='Escenario sintético Gemini'), n)
    completo = Inmueble(origen=Origen(fuente='metrocuadrado', id_original='gemini-sintetico-a'),
        tipo=TipoInmueble.APARTAMENTO, ciudad='Bogotá', barrio='La Carolina', habitaciones=2, banos=2,
        area_construida_m2=Decimal('80'), area_privada_m2=Decimal('70'),
        ofertas=(Oferta(operacion=Operacion.VENTA, precio=Decimal('450000000')),))
    pendiente = replace(completo, origen=Origen(fuente='wasi', id_original='gemini-sintetico-b'), habitaciones=None)
    excluido = replace(completo, origen=Origen(fuente='fincaraiz', id_original='gemini-sintetico-c'),
                       ofertas=(Oferta(operacion=Operacion.VENTA, precio=Decimal('500000001')),))

    class CatalogoSintetico:
        def listar(self): return [completo, pendiente, excluido]

    cat = CatalogoSintetico()
    repo = SeguimientoSQLite(s.repositorio.ruta)
    repo.decision(o.id, pendiente.id_interno, 'preseleccionado')
    resultados = s.coincidencias(o.id, cat)
    assert len(resultados) == 2 and any(r.pendientes for r in resultados)
    plan = plan_gemini(o, resultados, repo, ia)
    print(f'Modelo: {ia.modelo}. Candidatos: 2; generación máxima: 1; posibles cargos de Google.')
    tarea = solicitar_gemini(s, cat, o.id, str(uuid4()), gemini=ia, esperada=plan['firma'])
    tarea()
    primera = repo.ultima_gemini(o.id)
    # Evidencia saneada aun ante timeout/error. No copiar prompts, clave ni respuesta cruda.
    evidencia = {k:v for k,v in primera.items() if k != 'datos'} | {
        'datos': {k:v for k,v in primera['datos'].items() if k not in ('evaluaciones', 'entradas')},
        'respuesta_validada': primera['datos']['resultado'] == 'correcto', 'validacion_real': False}
    (salida / 'evidencia.json').write_text(json.dumps(evidencia, ensure_ascii=False, indent=2), encoding='utf-8')
    if primera['datos']['resultado'] != 'correcto':
        print('La única llamada no produjo una evaluación válida. No se reintentó. Evidencia: ' + str(salida / 'evidencia.json'))
        return 1
    assert len(primera['datos']['evaluaciones']) == 2
    # El segundo clic solo puede consumir caché; el guardado y la búsqueda tampoco llaman.
    recalcular(s, cat, o.id, True)
    tarea = solicitar_gemini(s, cat, o.id, str(uuid4()), gemini=ia)
    tarea()
    assert ia.llamadas == 1
    segunda = repo.ultima_gemini(o.id)['datos']
    assert segunda['solicitudes'] == 0 and segunda['reutilizadas'] == 2
    assert any(r.pendientes for r in s.coincidencias(o.id, cat))
    assert all(r.inmueble.id_interno != excluido.id_interno for r in resultados)
    assert repo.decisiones(o.id)[pendiente.id_interno]['estado'] == 'preseleccionado'

    # Recorrido por la presentación real, inyectando los mismos datos sintéticos.
    from fastapi.testclient import TestClient
    from metro.web import app, servicio
    from oportunidades.api import proveedor_oportunidades
    app.dependency_overrides[servicio] = lambda: cat
    app.dependency_overrides[proveedor_oportunidades] = lambda: s
    try:
        with TestClient(app) as cliente:
            html = cliente.get(f'/v0.6/clientes/{o.cliente_id}').text
        from bs4 import BeautifulSoup
        pagina = BeautifulSoup(html, 'html.parser')
        assert len(pagina.select('[data-candidate]')) == 2
        assert len(pagina.select('.ai-explanation')) == 2
        fila = pagina.select_one(f'[data-candidate="{pendiente.id_interno}"]')
        assert 'Pendiente de verificar' in fila.text
        assert not pagina.select_one(f'[data-candidate="{excluido.id_interno}"]')
        (salida / 'ficha.html').write_text(html, encoding='utf-8')
    finally:
        app.dependency_overrides.clear()
    evidencia.update(cache_repetida_solicitudes=0, evaluaciones_persistidas=2,
                     requisito_desconocido_pendiente=True, excluido_no_enviado=True, presentacion_verificada=True,
                     decisiones_conservadas=True, validacion_real=True)
    (salida / 'evidencia.json').write_text(json.dumps(evidencia, ensure_ascii=False, indent=2), encoding='utf-8')
    print('VALIDACIÓN REAL CON GEMINI completada. Evidencia: ' + str(salida / 'evidencia.json'))
    print(json.dumps(primera['datos'].get('tokens', {})))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
