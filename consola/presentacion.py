"""Formato y estado de navegación; las consultas pertenecen a catalogo."""

from dataclasses import fields
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from urllib.parse import urlencode, urlsplit

from pydantic import TypeAdapter, ValidationError

from catalogo.consultas import ofertas_compatibles
from catalogo.filtros import FiltrosCatalogo
from catalogo.modelos import Disponibilidad, TipoArea

ADAPTADOR = TypeAdapter(FiltrosCatalogo)
LISTAS = {'zonas', 'barrios', 'tipos', 'estratos'}
COLOMBIA = timezone(timedelta(hours=-5))
ESTADOS = {
    Disponibilidad.ACTIVO: ('Activo en búsquedas', 'activo'),
    Disponibilidad.POSIBLEMENTE_RETIRADO: ('Pendiente de confirmar', 'pendiente'),
    Disponibilidad.RETIRADO: ('Fuera de las búsquedas', 'retirado'),
    Disponibilidad.DESCONOCIDA: ('Sin verificación', 'desconocido'),
}


def leer_filtros(query):
    datos = {}
    for campo in fields(FiltrosCatalogo):
        if campo.name in ('limite', 'desplazamiento'):
            continue
        valores = [v.strip() for v in query.getlist(campo.name) if v.strip()]
        if valores:
            datos[campo.name] = tuple(valores) if campo.name in LISTAS else valores[-1]
    datos.setdefault('tipo_area', 'construida')
    datos.setdefault('orden', 'actualizacion_desc')
    datos['limite'] = query.get('limit') or 24
    datos['desplazamiento'] = query.get('offset') or 0
    return ADAPTADOR.validate_python(datos)


def mensaje_filtros(error: ValidationError):
    texto = str(error)
    if 'requiere operación y moneda' in texto:
        return 'Elige una operación y una moneda para filtrar u ordenar por precio.'
    if 'precio_min no puede superar' in texto:
        return 'El precio mínimo no puede superar el máximo.'
    if 'area_min_m2 no puede superar' in texto:
        return 'El área mínima no puede superar la máxima.'
    if 'habitaciones_min no puede superar' in texto:
        return 'El mínimo de habitaciones no puede superar el máximo.'
    return 'Revisa los filtros: usa valores válidos y números positivos o cero.'


def url_catalogo(query, **cambios):
    pares = [(k, v) for k, v in query.multi_items() if v.strip() and k not in cambios]
    pares.extend((k, str(v)) for k, v in cambios.items() if v is not None)
    return '/consola/' + ('?' + urlencode(pares) if pares else '')


def regreso_seguro(valor):
    if not valor or len(valor) > 4096 or any(ord(c) < 32 for c in valor):
        return '/consola/'
    try:
        partes = urlsplit(valor)
    except ValueError:
        return '/consola/'
    if partes.scheme or partes.netloc or partes.path not in ('/consola', '/consola/'):
        return '/consola/'
    return '/consola/' + ('?' + partes.query if partes.query else '')


def enlace_publico(valor):
    if not isinstance(valor, str):
        return None
    try:
        partes = urlsplit(valor)
        valido = (partes.scheme in ('https', 'http') and partes.hostname
                  and partes.username is None and partes.password is None)
    except ValueError:
        return None
    return valor if valido else None


def numero(valor):
    if valor is None:
        return 'Sin dato'
    entero, _, decimales = format(Decimal(valor), ',f').partition('.')
    return entero.replace(',', '.') + (',' + decimales.rstrip('0') if decimales.rstrip('0') else '')


def precio_cop(valor):
    """Convención visual local; conserva el importe y no convierte divisas."""
    return f'${numero(valor)}' if valor is not None else 'Precio no informado'


def fecha(valor):
    if isinstance(valor, str):
        try:
            valor = datetime.fromisoformat(valor.replace('Z', '+00:00'))
        except ValueError:
            return 'No registrada'
    if valor and valor.tzinfo is None:
        return 'No registrada'
    return valor.astimezone(COLOMBIA).strftime('%d/%m/%Y · %H:%M') if valor else 'No registrada'


def area_disponible(inmueble, tipo=None):
    """Prioridad visual; una comparación explícita nunca sustituye su tipo."""
    opciones = {
        TipoArea.CONSTRUIDA: (inmueble.area_construida_m2, 'construida'),
        TipoArea.PRIVADA: (inmueble.area_privada_m2, 'privada'),
        TipoArea.PUBLICADA: (inmueble.area_publicada_m2, 'no especifica'),
    }
    candidatos = (opciones[tipo],) if tipo is not None else opciones.values()
    return next(((v, e) for v, e in candidatos if v is not None and v.is_finite() and v > 0), (None, None))


def area_principal(inmueble, tipo=None):
    valor, etiqueta = area_disponible(inmueble, tipo)
    return f'{numero(valor)} m² ({etiqueta})' if valor is not None else 'No especifica'


def ofertas_visibles(inmueble, filtros=None):
    ofertas = ofertas_compatibles(inmueble, filtros) if filtros else inmueble.ofertas
    return [{
        'operacion': 'Venta' if o.operacion.value == 'venta' else 'Arriendo',
        'precio': precio_cop(o.precio),
        'moneda': 'COP',
        'con_precio': o.precio is not None,
    } for o in ofertas]


def tarjeta(inmueble, filtros, volver):
    etiqueta, clase = ESTADOS[inmueble.disponibilidad]
    ofertas = ofertas_visibles(inmueble, filtros)
    principal = next((o for o in ofertas if o['operacion'] == 'Venta'), ofertas[0] if ofertas else None)
    area_valor, area_tipo = area_disponible(inmueble)
    return {
        'inmueble': inmueble, 'estado': etiqueta, 'clase_estado': clase,
        'ubicacion': ' · '.join(dict.fromkeys(
            v for v in (inmueble.barrio, inmueble.zona, inmueble.ciudad) if v
        )) or 'Ubicación no informada',
        'ofertas': ofertas, 'oferta_principal': principal,
        'area': area_principal(inmueble), 'area_valor': area_valor, 'area_tipo': area_tipo,
        'area_comparacion': area_principal(inmueble, filtros.tipo_area),
        'mapa': enlace_mapa(inmueble),
        'fotos': tuple(f for f in inmueble.fotos if enlace_publico(f)),
        'fuente': 'Metrocuadrado' if inmueble.origen.fuente == 'metrocuadrado' else inmueble.origen.fuente.title(),
        'url': '/consola/inmuebles/' + inmueble.id_interno + '?' + urlencode({'volver': volver}),
    }


def enlace_mapa(inmueble):
    """Solo el enlace almacenado a la sección del mapa del mismo anuncio."""
    mapa = enlace_publico(inmueble.portal_map_url)
    publicacion = enlace_publico(inmueble.origen.url)
    if not mapa or not publicacion or inmueble.origen.fuente != 'metrocuadrado':
        return None
    try:
        destino, original = urlsplit(mapa), urlsplit(publicacion)
        if (destino.hostname not in ('www.metrocuadrado.com', 'metrocuadrado.com')
                or destino.hostname != original.hostname or destino.port != original.port
                or not destino.path.startswith('/inmueble/') or destino.path != original.path
                or destino.fragment != 'location-section'):
            return None
    except ValueError:
        return None
    return mapa


def precio_historico(valor):
    if not isinstance(valor, dict):
        return 'Sin dato'
    if valor.get('status') != 'valid' or valor.get('amount') is None:
        return 'No comparable'
    operacion = {'venta': 'Venta', 'arriendo': 'Arriendo'}.get(valor.get('operation'), 'Operación desconocida')
    return f"{operacion} · {precio_cop(valor['amount'])}"


def historial_visible(cambios):
    verificaciones = {
        'confirmed': 'Confirmado en ficha', 'pending': 'Pendiente de verificar',
        'price_confirmed_partial_detail': 'Precio confirmado; ficha parcial',
        'disagreement_or_uncomparable': 'Diferencia o dato no comparable',
        'detail_failed': 'No se pudo verificar la ficha',
    }
    return [{
        'fecha': fecha(c.get('detected_at')),
        'anterior': precio_historico(c.get('previous_price')),
        'nuevo': precio_historico(c.get('new_price')),
        'detalle': precio_historico(c.get('detail_price')),
        'estado': verificaciones.get(c.get('verification'), 'Sin verificación'),
    } for c in reversed(cambios)]


def nombre_busqueda(presencia, indice):
    if presencia.nombre:
        return presencia.nombre
    try:
        path = urlsplit(presencia.url or '').path.rstrip('/')
    except ValueError:
        path = ''
    ultimo = path.rsplit('/', 1)[-1].replace('-', ' ').strip()
    return ultimo.title() if ultimo else f'Búsqueda {indice}'
