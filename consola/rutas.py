"""Páginas Jinja2 que consumen el servicio común; no contienen consultas SQL."""

from pathlib import Path
import csv
from io import StringIO
from urllib.parse import parse_qs

from fastapi import APIRouter, Depends, Request, HTTPException, Query
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from pydantic import ValidationError

from catalogo.filtros import FiltrosCatalogo
from catalogo.modelos import TipoInmueble
from catalogo.consultas import seleccionar, paginar, ofertas_compatibles, contar_categorias
from catalogo.persistencia.contrato import ErrorLecturaCatalogo
from catalogo.servicio import InmuebleNoEncontrado, ConsultaInvalida
from .anunciantes import url_anunciante, contactos
from catalogo.consultas import inmuebles_anunciante
from urllib.parse import urlencode
from .presentacion import (
    ESTADOS, enlace_publico, fecha, leer_filtros, mensaje_filtros, nombre_busqueda,
    numero, ofertas_visibles, regreso_seguro, tarjeta, url_catalogo, historial_visible,
)
from .oportunidades import crear_router as crear_router_oportunidades, contexto_captura
from oportunidades.persistencia import ErrorPersistencia, NoEncontrado

RAIZ = Path(__file__).resolve().parent
ESTATICOS = RAIZ / 'static'
templates = Jinja2Templates(directory=str(RAIZ / 'templates'))
templates.env.filters.update(numero=numero, fecha=fecha)
templates.env.globals.update(enlace_publico=enlace_publico, url_anunciante=url_anunciante)


def crear_router(proveedor_servicio, plantillas=None):
    templates = plantillas or globals()['templates']
    router = APIRouter()
    router.include_router(crear_router_oportunidades(proveedor_servicio, templates))

    def render(request, nombre, status=200, **contexto):
        base = {'values': request.query_params, 'tipos': tuple(TipoInmueble),
                'ciudades': (), 'barrios': (), 'zonas': (), 'fuentes': (), 'busquedas_opciones': (),
                'error': None, 'total': 0, 'activos': (), 'ordenes': ORDENES}
        return templates.TemplateResponse(request=request, name=nombre,
                                          context={**base, **contexto}, status_code=status)

    @router.get('/consola/anunciante', response_class=HTMLResponse, include_in_schema=False)
    def anunciante(request: Request, inmueble: str, pagina: int = Query(1, ge=1),
                   servicio=Depends(proveedor_servicio)):
        try:
            todos = servicio.listar()
        except (FileNotFoundError, ErrorLecturaCatalogo):
            raise HTTPException(503, 'El catálogo no está disponible. Vuelve a intentar.')
        origen = next((i for i in todos if i.id_interno == inmueble), None)
        if origen is None or not origen.anunciante or not origen.anunciante.strip():
            raise HTTPException(404, 'Anunciante no disponible')
        grupo = inmuebles_anunciante(todos, origen.anunciante)
        otros = [i for i in grupo if i.id_interno != inmueble]
        paginas = max(1, (len(otros) + 11) // 12)
        pagina = min(pagina, paginas)
        def url(p):
            return '/consola/anunciante?' + urlencode({'inmueble': inmueble, 'pagina': p})
        return render(request, 'anunciante.html', anunciante_nombre=origen.anunciante,
                      contactos=contactos(grupo), origen=origen, cantidad=len(otros),
                      otros=otros[(pagina-1)*12:pagina*12], pagina=pagina, paginas=paginas,
                      anterior=url(pagina-1) if pagina > 1 else None,
                      siguiente=url(pagina+1) if pagina < paginas else None)

    @router.get('/consola', include_in_schema=False)
    def entrada(request: Request):
        return RedirectResponse('/consola/' + ('?' + request.url.query if request.url.query else ''),
                                status_code=307)

    @router.get('/consola/', response_class=HTMLResponse, include_in_schema=False)
    def catalogo(request: Request, servicio=Depends(proveedor_servicio)):
        try:
            todos = servicio.listar()
            ultima_actualizacion = servicio.ultima_actualizacion()
            busquedas_registradas = {(b['fuente'], b['id_busqueda']): b
                                     for b in servicio.listar_busquedas()}
            for i in todos:
                for n, p in enumerate(i.origen.busquedas, 1):
                    busquedas_registradas.setdefault((i.origen.fuente, p.id_busqueda), {
                        'fuente': i.origen.fuente, 'id_busqueda': p.id_busqueda,
                        'url': p.url or p.id_busqueda, 'nombre': nombre_busqueda(p, n)})
            ciudades = sorted({i.ciudad for i in todos if i.ciudad})
            barrios = sorted({i.barrio for i in todos if i.barrio})
            zonas = sorted({i.zona for i in todos if i.zona})
            fuentes = sorted({i.origen.fuente for i in todos})
            busquedas_opciones = sorted({(i.origen.fuente, p.id_busqueda) for i in todos for p in i.origen.busquedas})
            seleccionada = request.query_params.get('ciudad')
            if seleccionada and seleccionada not in ciudades:
                ciudades.append(seleccionada)
        except (FileNotFoundError, ErrorLecturaCatalogo):
            return render(request, 'estado.html', 503, titulo='El catálogo no está disponible',
                          mensaje='No encontramos la información de los inmuebles. Revisa que los datos estén disponibles y vuelve a intentar.',
                          reintentar='/consola/')
        try:
            filtros = leer_filtros(request.query_params)
        except ValidationError as exc:
            return render(request, 'catalogo.html', 422, error=mensaje_filtros(exc),
                          ciudades=ciudades, barrios=barrios, tarjetas=(), resultado=None)
        try:
            # Una sola lectura por solicitud, también para las opciones del formulario.
            resultado = paginar(seleccionar(todos, filtros), filtros.limite, filtros.desplazamiento)
        except (FileNotFoundError, ErrorLecturaCatalogo):
            return render(request, 'estado.html', 503, titulo='El catálogo no está disponible',
                          mensaje='No pudimos consultar los inmuebles en este momento. Inténtalo de nuevo.',
                          reintentar=url_catalogo(request.query_params))
        volver = url_catalogo(request.query_params)
        limite, offset, total = resultado['limit'], resultado['offset'], resultado['total']
        try:
            captura = getattr(templates, 'contexto_captura', contexto_captura)(request, todos)
        except NoEncontrado as exc:
            return render(request, 'estado.html', 404, titulo='No encontramos el registro',
                          mensaje=str(exc), reintentar='/consola/')
        except ErrorPersistencia:
            captura = {'error_crm': 'No se pudieron cargar clientes y oportunidades. El catálogo sigue disponible.'}
        return render(
            request, 'catalogo.html', ciudades=ciudades, barrios=barrios, filtros=filtros,
            zonas=zonas, fuentes=fuentes, busquedas_opciones=busquedas_opciones,
            ultima_actualizacion=ultima_actualizacion,
            busquedas_registradas=sorted(busquedas_registradas.values(), key=lambda b: (b['fuente'], b['nombre'])),
            nombres_busquedas={k: b['nombre'] for k, b in busquedas_registradas.items()},
            categorias=[{'clave': clave, 'nombre': CATEGORIAS[clave], 'cantidad': cantidad,
                         'url': url_catalogo(request.query_params, categoria=clave, offset=0)}
                        for clave, cantidad in contar_categorias(todos, filtros).items()],
            activos=[(ETIQUETAS[k], v) for k, v in request.query_params.multi_items()
                     if k in ETIQUETAS and v.strip()],
            exportar='/consola/exportar.csv' + ('?' + request.url.query if request.url.query else ''),
            orden_url=lambda valor: url_catalogo(request.query_params, orden=valor, offset=0),
            tarjetas=[tarjeta(i, filtros, volver) for i in resultado['items']],
            resultado=resultado, total=total, primero=min(offset + 1, total) if resultado['items'] else 0,
            ultimo=min(offset + limite, total), pagina=offset // limite + 1,
            paginas=max(1, (total + limite - 1) // limite),
            anterior=url_catalogo(request.query_params, offset=max(0, offset - limite)) if offset else None,
            siguiente=url_catalogo(request.query_params, offset=offset + limite) if offset + limite < total else None,
            primera=url_catalogo(request.query_params, offset=0),
            **captura,
        )

    @router.post('/consola/busquedas', include_in_schema=False)
    async def guardar_busqueda(request: Request, servicio=Depends(proveedor_servicio)):
        valores = parse_qs((await request.body()).decode('utf-8'), keep_blank_values=True)
        datos = {k: v[-1] for k, v in valores.items()}
        volver = getattr(templates, 'regreso_seguro', regreso_seguro)(datos.get('volver'))
        try:
            servicio.guardar_busqueda(datos.get('fuente'), datos.get('url'), datos.get('nombre'))
        except (ConsultaInvalida, ValueError, TypeError) as exc:
            return render(request, 'estado.html', 422, titulo='Revisa la búsqueda',
                          mensaje=str(exc), reintentar=volver)
        except (ErrorLecturaCatalogo, OSError):
            return render(request, 'estado.html', 503, titulo='No se pudo guardar la búsqueda',
                          mensaje='Vuelve a intentar. Los inmuebles y sus búsquedas de origen se conservan.', reintentar=volver)
        return RedirectResponse(volver + '#busquedas-origen', status_code=303)

    @router.get('/consola/exportar.csv', include_in_schema=False)
    def exportar(request: Request, servicio=Depends(proveedor_servicio)):
        try:
            filtros = leer_filtros(request.query_params)
            items = seleccionar(servicio.listar(), filtros)
        except ValidationError as exc:
            return render(request, 'estado.html', 422, titulo='Revisa los filtros de exportación',
                          mensaje=mensaje_filtros(exc), reintentar=url_catalogo(request.query_params))
        except (FileNotFoundError, ErrorLecturaCatalogo):
            return render(request, 'estado.html', 503, titulo='El catálogo no está disponible',
                          mensaje='No pudimos exportar los inmuebles.', reintentar='/consola/')

        def contenido():
            buffer = StringIO()
            writer = csv.writer(buffer, delimiter=';')
            yield '\ufeff'  # Excel reconoce UTF-8 y conserva tildes.

            def fila(valores):
                buffer.seek(0)
                buffer.truncate(0)
                # Evita interpretar texto de la fuente como fórmulas en una hoja de cálculo.
                writer.writerow(["'" + v if isinstance(v, str) and v.lstrip().startswith(('=', '+', '-', '@'))
                                 else v for v in valores])
                return buffer.getvalue()

            yield fila(['ID', 'Fuente', 'Zona', 'Barrio', 'Ciudad', 'Tipo', 'Operación', 'Precio',
                        'Moneda', 'Área m²', 'Tipo de área', 'Habitaciones', 'Publicación', 'Búsquedas de origen',
                        'Anunciante', 'Teléfono móvil', 'Teléfono fijo', 'WhatsApp', 'Dirección del anunciante'])
            for i in items:
                card = tarjeta(i, filtros, '/consola/')
                for oferta in ofertas_compatibles(i, filtros) or (None,):
                    yield fila([i.origen.id_original, i.origen.fuente, i.zona, i.barrio, i.ciudad,
                                i.tipo.value if i.tipo else None,
                                oferta.operacion.value if oferta else None,
                                oferta.precio if oferta else None, 'COP',
                                card['area_valor'], card['area_tipo'], i.habitaciones,
                                enlace_publico(i.origen.url), ' | '.join(b['nombre'] for b in card['busquedas']),
                                i.anunciante, i.telefono, i.telefono_fijo, i.whatsapp, i.anunciante_direccion])

        return StreamingResponse(contenido(), media_type='text/csv; charset=utf-8',
                                 headers={'Content-Disposition': 'attachment; filename="radar-catalogo.csv"'})

    @router.get('/consola/inmuebles/{id_interno}', response_class=HTMLResponse,
                include_in_schema=False)
    def ficha(request: Request, id_interno: str, volver: str | None = None,
              servicio=Depends(proveedor_servicio)):
        regreso = getattr(templates, 'regreso_seguro', regreso_seguro)(volver)
        try:
            inmueble = servicio.obtener(id_interno)
        except (FileNotFoundError, ErrorLecturaCatalogo):
            return render(request, 'estado.html', 503, titulo='No pudimos abrir esta ficha',
                          mensaje='La información del catálogo no está disponible en este momento.',
                          reintentar=regreso)
        if inmueble is None:
            return render(request, 'estado.html', 404, titulo='No encontramos este inmueble',
                          mensaje='El enlace puede haber cambiado. Regresa al catálogo para continuar.',
                          reintentar=regreso)
        datos = tarjeta(inmueble, FiltrosCatalogo(), regreso)
        try:
            revision = servicio.ficha_compatible(id_interno)
            historial = historial_visible(revision['price_history'])
            datos_fuente = revision.get('catalog_data') or {}
            campos_fuente = datos_fuente.get('fields') or {}
            error_historial = False
        except (FileNotFoundError, ErrorLecturaCatalogo, InmuebleNoEncontrado):
            historial, error_historial, campos_fuente, datos_fuente = (), True, {}, {}
        busquedas = [{
            'nombre': nombre_busqueda(p, n), 'url': enlace_publico(p.url),
            'estado': ESTADOS[p.disponibilidad][0], 'clase': ESTADOS[p.disponibilidad][1],
            'fecha': p.ultima_verificacion,
        } for n, p in enumerate(inmueble.origen.busquedas, 1)]
        return render(request, 'ficha.html', inmueble=inmueble, datos=datos,
                      ofertas=ofertas_visibles(inmueble), busquedas=busquedas, volver=regreso,
                      historial=historial, error_historial=error_historial, campos_fuente=campos_fuente, datos_fuente=datos_fuente)

    return router


ORDENES = (
    ('actualizacion_desc', 'Extracción: más reciente'), ('actualizacion_asc', 'Extracción: más antigua'),
    ('precio_asc', 'Precio: menor a mayor'), ('precio_desc', 'Precio: mayor a menor'),
    ('area_asc', 'Área: menor a mayor'), ('area_desc', 'Área: mayor a menor'),
    ('ultima_verificacion_desc', 'Presencia en búsquedas: reciente'), ('id', 'Identificador'),
)
ETIQUETAS = {
    'texto': 'Texto', 'ciudad': 'Ciudad', 'zonas': 'Zona', 'barrios': 'Barrio', 'tipos': 'Tipo',
    'operacion': 'Operación', 'precio_min': 'Precio desde', 'precio_max': 'Precio hasta',
    'tipo_area': 'Área', 'area_min_m2': 'Área desde', 'area_max_m2': 'Área hasta',
    'habitaciones_min': 'Habitaciones mín.', 'habitaciones_max': 'Habitaciones máx.',
    'banos_min': 'Baños mín.', 'parqueaderos_min': 'Parqueaderos mín.', 'estratos': 'Estrato',
    'fuente': 'Fuente', 'id_busqueda': 'Búsqueda', 'disponibilidad': 'Estado', 'requiere_revision': 'Revisión',
}

CATEGORIAS = {'todos': 'Todos', 'nuevos': 'Nuevos', 'cambio_precio': 'Cambio de precio',
              'revision_conservadora': 'Revisión conservadora'}
