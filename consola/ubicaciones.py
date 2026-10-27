"""Opciones reales por ciudad, normalizadas con las mismas claves del matching."""
from oportunidades.normalizacion import normalizar, normalizar_ciudad
from catalogo.geografia import resolver_barrio


def opciones_ubicacion(todos, valores):
    ciudades, opciones = {}, {}
    for i in sorted(todos, key=lambda i: (i.ciudad or '', i.id_interno)):
        if not i.ciudad:
            continue
        ciudad = normalizar_ciudad(i.ciudad)
        ciudades.setdefault(ciudad, ' '.join(i.ciudad.split()))
        for tipo in ('barrio', 'zona'):
            nombre = getattr(i, tipo)
            if nombre:
                clave = tipo + ':' + normalizar(nombre)
                opciones.setdefault((ciudad, clave), dict(ciudad=ciudad, clave=clave, tipo=tipo,
                    nombre=' '.join(nombre.split()), valor=tipo + ':' + nombre, legado=False))
    actual = normalizar_ciudad(valores.get('ciudad', ''))
    if not actual and len(ciudades) == 1:
        actual = next(iter(ciudades))
    if actual in ciudades:
        valores['ciudad'] = ciudades[actual]
    seleccionadas = set()
    for tipo, campo in (('barrio', 'barrios'), ('zona', 'zonas')):
        for nombre in valores.get(campo, []):
            if tipo == 'barrio':
                entrada = resolver_barrio(valores.get('ciudad'), nombre)[0]
                if entrada:
                    nombre = entrada['nombre']
            clave = tipo + ':' + normalizar(nombre)
            seleccionadas.add((actual, clave))
            if (actual, clave) not in opciones:
                # Valor previo: se conserva como etiqueta histórica, no como opción del buscador.
                opciones[(actual, clave)] = dict(ciudad=actual, clave=clave, tipo=tipo, nombre=nombre,
                                                valor=tipo + ':' + nombre, legado=True)
    lista = sorted(opciones.values(), key=lambda o: (o['ciudad'], o['tipo'], o['clave']))
    for opcion in lista:
        opcion['seleccionada'] = (opcion['ciudad'], opcion['clave']) in seleccionadas
    return dict(ciudades_crm=[{'clave': k, 'valor': v} for k, v in sorted(ciudades.items())],
                ciudad_clave_crm=actual, ciudad_historica_crm=bool(actual and actual not in ciudades),
                ciudad_unica_crm=len(ciudades) == 1 and actual in ciudades,
                ubicaciones_crm=lista)


def actualizar_ciudad(todos, valores):
    """Fallback sin JavaScript: conserva el borrador y elimina selecciones ajenas."""
    opciones = opciones_ubicacion(todos, dict(valores))['ubicaciones_crm']
    ciudad = normalizar_ciudad(valores.get('ciudad', ''))
    validas = {(o['tipo'], normalizar(o['nombre'])): o['nombre'] for o in opciones
               if o['ciudad'] == ciudad and not o['legado']}
    quitadas = []
    for tipo, campo in (('barrio', 'barrios'), ('zona', 'zonas')):
        previas = valores.get(campo, [])
        quitadas.extend(v for v in previas if (tipo, normalizar(v)) not in validas)
        valores[campo] = [validas[(tipo, normalizar(v))] for v in previas if (tipo, normalizar(v)) in validas]
    return quitadas
