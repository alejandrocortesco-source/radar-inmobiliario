"""Páginas Jinja2 que consumen el servicio común; no contienen consultas SQL."""

from pathlib import Path
import csv
from io import StringIO

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from pydantic import ValidationError

from catalogo.filtros import FiltrosCatalogo
from catalogo.modelos import TipoInmueble
from catalogo.consultas import seleccionar, paginar, ofertas_compatibles
from catalogo.persistencia.contrato import ErrorLecturaCatalogo
from catalogo.servicio import InmuebleNoEncontrado
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
templates.env.globals.update(enlace_publico=enlace_publico)


def crear_router(proveedor_servicio):
    router = APIRouter()
    router.include_router(crear_router_oportunidades(proveedor_servicio, templates))

    def render(request, nombre, status=200, **contexto):
        base = {'values': request.query_params, 'tipos': tuple(TipoInmueble),
                'ciudades': (), 'barrios': (), 'zonas': (), 'fuentes': (), 'busquedas_opciones': (),
                'error': None, 'total': 0, 'activos': (), 'ordenes': ORDENES}
        return templates.TemplateResponse(request=request, name=nombre,
                                          context={**base, **contexto}, status_code=status)

    @router.get('/consola', include_in_schema=False)
    def entrada(request: Request):
        return RedirectResponse('/consola/' + ('?' + request.url.query if request.url.query else ''),
                                status_code=307)

    @router.get('/consola/', response_class=HTMLResponse, include_in_schema=False)
    def catalogo(request: Request, servicio=Depends(proveedor_servicio)):
        try:
            todos = servicio.listar()
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
            captura = contexto_captura(request, todos)
        except NoEncontrado as exc:
            return render(request, 'estado.html', 404, titulo='No encontramos el registro',
                          mensaje=str(exc), reintentar='/consola/')
        except ErrorPersistencia:
            captura = {'error_crm': 'No se pudieron cargar clientes y oportunidades. El catálogo sigue disponible.'}
        return render(
            request, 'catalogo.html', ciudades=ciudades, barrios=barrios, filtros=filtros,
            zonas=zonas, fuentes=fuentes, busquedas_opciones=busquedas_opciones,
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
                        'Moneda', 'Área m²', 'Tipo de área', 'Habitaciones', 'Publicación'])
            for i in items:
                card = tarjeta(i, filtros, '/consola/')
                for oferta in ofertas_compatibles(i, filtros) or (None,):
                    yield fila([i.origen.id_original, i.origen.fuente, i.zona, i.barrio, i.ciudad,
                                i.tipo.value if i.tipo else None,
                                oferta.operacion.value if oferta else None,
                                oferta.precio if oferta else None, oferta.moneda if oferta else None,
                                card['area_valor'], card['area_tipo'], i.habitaciones,
                                enlace_publico(i.origen.url)])

        return StreamingResponse(contenido(), media_type='text/csv; charset=utf-8',
                                 headers={'Content-Disposition': 'attachment; filename="radar-catalogo.csv"'})

    @router.get('/consola/inmuebles/{id_interno}', response_class=HTMLResponse,
                include_in_schema=False)
    def ficha(request: Request, id_interno: str, volver: str | None = None,
              servicio=Depends(proveedor_servicio)):
        regreso = regreso_seguro(volver)
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
            historial = historial_visible(servicio.ficha_compatible(id_interno)['price_history'])
            error_historial = False
        except (FileNotFoundError, ErrorLecturaCatalogo, InmuebleNoEncontrado):
            historial, error_historial = (), True
        busquedas = [{
            'nombre': nombre_busqueda(p, n), 'url': enlace_publico(p.url),
            'estado': ESTADOS[p.disponibilidad][0], 'clase': ESTADOS[p.disponibilidad][1],
            'fecha': p.ultima_verificacion,
        } for n, p in enumerate(inmueble.origen.busquedas, 1)]
        return render(request, 'ficha.html', inmueble=inmueble, datos=datos,
                      ofertas=ofertas_visibles(inmueble), busquedas=busquedas, volver=regreso,
                      historial=historial, error_historial=error_historial)

    return router


ORDENES = (
    ('actualizacion_desc', 'Extracción: más reciente'), ('actualizacion_asc', 'Extracción: más antigua'),
    ('precio_asc', 'Precio: menor a mayor'), ('precio_desc', 'Precio: mayor a menor'),
    ('area_asc', 'Área: menor a mayor'), ('area_desc', 'Área: mayor a menor'),
    ('ultima_verificacion_desc', 'Presencia en búsquedas: reciente'), ('id', 'Identificador'),
)
ETIQUETAS = {
    'texto': 'Texto', 'ciudad': 'Ciudad', 'zonas': 'Zona', 'barrios': 'Barrio', 'tipos': 'Tipo',
    'operacion': 'Operación', 'moneda': 'Moneda', 'precio_min': 'Precio desde', 'precio_max': 'Precio hasta',
    'tipo_area': 'Área', 'area_min_m2': 'Área desde', 'area_max_m2': 'Área hasta',
    'habitaciones_min': 'Habitaciones mín.', 'habitaciones_max': 'Habitaciones máx.',
    'banos_min': 'Baños mín.', 'parqueaderos_min': 'Parqueaderos mín.', 'estratos': 'Estrato',
    'fuente': 'Fuente', 'id_busqueda': 'Búsqueda', 'disponibilidad': 'Estado', 'requiere_revision': 'Revisión',
}
