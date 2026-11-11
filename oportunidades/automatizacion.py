"""Matching reutilizable en segundo plano; SQLite evita trabajos simultáneos duplicados."""
import hashlib
import json
import logging
import os
import time
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
        # Los textos libres pueden incluir contactos o identidad del cliente.
        # Se conservan localmente; el proveedor recibe solo hechos estructurados.
    }}


def necesidades_ia(o):
    return o.necesidades.model_dump(mode='json', exclude={'observaciones'})


def clave_novedad(r):
    return 'g:' + r.inmueble.inmueble_id if r.inmueble.inmueble_id else 'p:' + r.inmueble.id_interno


def recalcular(s, catalogo, identificador, forzar=False, seguimiento=None):
    """Solo matching determinista. Ninguna configuración habilita al proveedor."""
    o = s.oportunidad(identificador)
    repo = seguimiento or SeguimientoSQLite(s.repositorio.ruta)
    if o.estado != 'abierta' or not repo.activo(o.cliente_id):
        return False
    resultados = buscar(o.necesidades, catalogo.listar())
    entradas = [candidato(r) for r in resultados]
    firma = huella([o.necesidades.model_dump(mode='json'), entradas])
    repo.registrar_resultados(o.id, resultados)
    anterior = repo.leer(o.id)
    if anterior and anterior['huella'] == firma and not forzar:
        return False
    repo.guardar_matching(o.id, firma, {'ids': [c['id'] for c in entradas], 'total': len(resultados),
        'entradas': {c['id']: huella(c) for c in entradas},
        'necesidades_huella': huella(o.necesidades.model_dump(mode='json')),
        'aviso': 'Búsqueda determinista actualizada. Gemini solo se ejecuta al solicitarlo.'})
    return True


def plan_gemini(o, resultados, repo, gemini=None):
    """Vista previa sin red; misma selección estable que se usa al solicitar."""
    aviso = ''
    try:
        ia = gemini or Gemini()
        limite = int(os.getenv('GEMINI_MAX_CANDIDATES', '20'))
        if not 1 <= limite <= 30:
            raise ValueError()
    except ValueError:
        ia, limite = None, 20
        aviso = 'Configuración de Gemini inválida. Revisa el modelo y el límite (1–30).'
    entradas = [candidato(r) for r in resultados]
    necesidades = necesidades_ia(o)
    # Mantener también la huella local completa: cualquier cambio exige otro clic.
    firma = huella([o.necesidades.model_dump(mode='json'), entradas,
                   (ia.modelo, ia.version) if ia else None, limite])
    seleccion = entradas[:limite]
    claves = {c['id']: huella([(ia.modelo, ia.version), o.necesidades.model_dump(mode='json'), c]) for c in seleccion} if ia else {}
    evaluaciones, faltantes = {}, []
    for c in seleccion:
        cache = repo.cache(claves[c['id']]) if ia else None
        if cache:
            evaluaciones[c['id']] = cache
        else:
            faltantes.append(c)
    if not entradas:
        aviso = 'No hay candidatos elegibles para evaluar con Gemini.'
    elif ia and not ia.clave and faltantes:
        aviso = 'Gemini no está configurado. Se muestra el matching determinista.'
    return dict(ia=ia, firma=firma, necesidades=necesidades, entradas=entradas,
                limite=limite, seleccion=seleccion, claves=claves, evaluaciones=evaluaciones,
                faltantes=faltantes, aviso=aviso)


def solicitar_gemini(s, catalogo, identificador, solicitud, gemini=None, seguimiento=None, esperada=None):
    """Única puerta al proveedor, invocada por una solicitud manual explícita.

    Reserva antes de devolver la tarea: doble clic y concurrencia no crean una cola.
    El snapshot es inmutable durante la llamada. No se drenan tareas pendientes.
    """
    repo = seguimiento or SeguimientoSQLite(s.repositorio.ruta)
    o = s.oportunidad(identificador)
    if o.estado != 'abierta' or not repo.activo(o.cliente_id):
        raise ValueError('Activa el cliente y abre la oportunidad antes de evaluar.')
    # Validar identificador sin incluir información arbitraria en la auditoría.
    from uuid import UUID
    solicitud = str(UUID(solicitud))
    recalcular(s, catalogo, identificador, True, seguimiento=repo)
    o = s.oportunidad(identificador)
    plan = plan_gemini(o, buscar(o.necesidades, catalogo.listar()), repo, gemini)
    if esperada is not None and esperada != plan['firma']:
        raise ValueError('El catálogo o las necesidades cambiaron. Revisa la cantidad actual y solicita de nuevo la evaluación; no se llamó a Google.')
    datos = {'ejecucion': solicitud, 'huella': plan['firma'], 'total': len(plan['entradas']),
             'necesidades_huella': huella(o.necesidades.model_dump(mode='json')),
             'entradas': {c['id']: huella(c) for c in plan['seleccion']},
             'candidatos': len(plan['seleccion']), 'reutilizadas': len(plan['evaluaciones']),
             'enviados': 0, 'solicitudes': 0, 'modelo': plan['ia'].modelo if plan['ia'] else None,
             'evaluaciones': plan['evaluaciones'], 'aviso': plan['aviso']}
    if not repo.reservar_gemini(o.id, solicitud, datos):
        return None
    return lambda: ejecutar_gemini(repo, solicitud, plan, datos)


def ejecutar_gemini(repo, solicitud, plan, datos):
    inicio = time.monotonic()
    try:
        if datos['aviso']:
            datos['resultado'] = 'sin_candidatos' if not plan['entradas'] else 'configuracion'
        elif not plan['faltantes']:
            datos.update(resultado='cache', aviso='Se reutilizaron todas las evaluaciones vigentes sin nuevas llamadas a Google.')
        else:
            datos.update(enviados=len(plan['faltantes']), solicitudes=1)
            repo.actualizar_gemini(solicitud, datos)
            nuevas, aviso = plan['ia'].evaluar(plan['necesidades'], plan['faltantes'])
            datos.update(getattr(plan['ia'], 'reporte', {}))
            datos.update(aviso=aviso or 'Evaluación con Gemini terminada. Las explicaciones son orientativas.',
                         resultado=datos.get('resultado', 'error' if aviso else 'correcto'))
            for iid, evaluacion in nuevas.items():
                repo.guardar_cache(plan['claves'][iid], evaluacion)
            datos['evaluaciones'].update(nuevas)
    except Exception:
        # Nunca registrar excepciones del proveedor: podrían contener URL o clave.
        datos.update(resultado='interno', aviso='No se pudo completar la evaluación. Se conserva el matching determinista. Una nueva evaluación requiere otro clic explícito.')
    finally:
        datos['duracion_ms'] = round((time.monotonic() - inicio) * 1000)
        repo.terminar_gemini(solicitud, datos)


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
