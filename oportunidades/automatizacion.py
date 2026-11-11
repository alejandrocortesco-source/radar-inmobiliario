"""Matching reutilizable en segundo plano; SQLite evita trabajos simultáneos duplicados."""
import hashlib
import json
import logging
import os
from pathlib import Path

from .matching import buscar
from .seguimiento import SeguimientoSQLite
from .gemini import Gemini


def huella(datos):
    return hashlib.sha256(json.dumps(datos, default=str, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def candidato(r):
    i = r.inmueble
    return {'id': i.id_interno, 'politica_precios': 'COP-unica-v1', 'pendientes': r.pendientes, 'hechos': {
        'tipo': i.tipo, 'ciudad': i.ciudad, 'barrio': i.barrio, 'zona': i.zona,
        'precio': str(r.oferta.precio) if r.oferta and r.oferta.precio is not None else None,
        'moneda': 'COP',
        'habitaciones': i.habitaciones, 'banos': i.banos, 'parqueaderos': i.parqueaderos,
        'area_construida_m2': str(i.area_construida_m2) if i.area_construida_m2 else None,
        'area_privada_m2': str(i.area_privada_m2) if i.area_privada_m2 else None,
        'area_publicada_m2': str(i.area_publicada_m2) if i.area_publicada_m2 else None,
        'caracteristicas': ' · '.join(i.caracteristicas)[:4000] or None,
        'descripcion': (i.descripcion or '')[:4000] or None,
    }}


def recalcular(s, catalogo, identificador, forzar=False, gemini=None, seguimiento=None):
    o = s.oportunidad(identificador)
    repo = seguimiento or SeguimientoSQLite(s.repositorio.ruta)
    if o.estado != 'abierta' or not repo.activo(o.cliente_id):
        return False
    resultados = buscar(o.necesidades, catalogo.listar())
    entradas = [candidato(r) for r in resultados]
    try:
        ia = gemini or Gemini()
        limite = max(1, min(30, int(os.getenv('GEMINI_MAX_CANDIDATES', '20'))))
    except ValueError:
        ia = None
        limite = 20
    configuracion = (ia.modelo, bool(ia.clave), ia.version) if ia else ('invalido', False)
    firma = huella([o.necesidades.model_dump(mode='json'), entradas, configuracion, limite])
    if not repo.iniciar(o.id, firma, forzar):
        return False
    evaluaciones, aviso = {}, ''
    try:
        # Un lote por oportunidad/ejecución como máximo; el resto sigue visible sin IA.
        seleccion = entradas[:limite]
        claves = {c['id']: huella([configuracion, o.necesidades.model_dump(mode='json'), c]) for c in seleccion}
        faltantes = []
        for c in seleccion:
            cache = repo.cache(claves[c['id']])
            if cache:
                evaluaciones[c['id']] = cache
            else:
                faltantes.append(c)
        if ia is None:
            aviso = 'Configuración de Gemini inválida. Se conserva el matching determinista.'
        elif faltantes:
            nuevas, aviso = ia.evaluar(o.necesidades.model_dump(mode='json'), faltantes)
            for iid, datos in nuevas.items():
                repo.guardar_cache(claves[iid], datos)
            evaluaciones.update(nuevas)
        elif not ia.clave:
            aviso = 'Gemini no está configurado. Se muestra el matching determinista.'
        repetir = repo.terminar(o.id, firma, {'ids': [r.inmueble.id_interno for r in resultados],
            'evaluaciones': evaluaciones, 'aviso': aviso, 'modelo': ia.modelo if ia else None,
            'total': len(resultados), 'limite_ia': limite, 'entradas': {c['id']: huella(c) for c in entradas},
            'necesidades_huella': huella(o.necesidades.model_dump(mode='json'))})
        if repetir:
            recalcular(s, catalogo, identificador, gemini=gemini, seguimiento=repo)
    except Exception:
        logging.getLogger(__name__).exception('No se pudo completar el matching de la oportunidad %s', o.id)
        repo.terminar(o.id, firma, {'ids': [r.inmueble.id_interno for r in resultados], 'evaluaciones': {},
            'aviso': 'No se pudo completar la evaluación adicional. El matching determinista está disponible.'})
    return True


def recalcular_seguro(s, catalogo, identificador, forzar=False):
    """El guardado ya terminó: los fallos adicionales no convierten su respuesta en error."""
    try:
        return recalcular(s, catalogo, identificador, forzar)
    except Exception:
        logging.getLogger(__name__).exception('No se pudo iniciar el matching de %s', identificador)
        return False


def recalcular_abiertas(s, catalogo):
    for o in s.oportunidades():
        if o.estado == 'abierta':
            recalcular_seguro(s, catalogo, o.id)


def despues_scraper(ruta):
    """Solo se invoca después de una ejecución completada; usa el catálogo en lectura."""
    from catalogo.persistencia.integrado import catalogo_configurado
    from catalogo.servicio import ServicioCatalogo
    from .persistencia import SQLite
    from .servicio import ServicioOportunidades
    ruta = Path(ruta).resolve()
    crm = Path(os.getenv('RADAR_CRM_DB', str(ruta.with_name(ruta.stem + '-consola.sqlite')))).resolve()
    wasi = Path(os.getenv('WASI_DB', str(ruta.with_name('wasi.sqlite')))).resolve()
    fincaraiz = Path(os.getenv('FINCARAIZ_DB', str(ruta.with_name('fincaraiz.sqlite')))).resolve()
    if crm in (ruta, wasi, fincaraiz):
        raise ValueError('La base auxiliar debe ser distinta al catálogo')
    from catalogo.persistencia.asociaciones import AsociacionesSQLite
    asociaciones = AsociacionesSQLite(crm)
    catalogo = ServicioCatalogo(catalogo_configurado(ruta), asociaciones=asociaciones)
    try:
        asociaciones.analizar(catalogo.listar())
    except Exception:
        logging.getLogger(__name__).exception('Identificación pendiente de reintento; captura conservada')
    recalcular_abiertas(ServicioOportunidades(SQLite(crm)), catalogo)
