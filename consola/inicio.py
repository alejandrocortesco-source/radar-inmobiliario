"""Proyecciones pequeñas para el dashboard; sin SQL ni cambios al catálogo."""
from catalogo.modelos import CategoriaActualizacion, Disponibilidad
from oportunidades.matching import buscar


def indicadores(todos, ultima):
    def contar(condicion):
        return len({i.inmueble_id or i.id_interno for i in todos if condicion(i)})
    return {'total': contar(lambda i: True), 'publicaciones': len(todos), 'ultima': ultima,
        'nuevos': contar(lambda i: any(CategoriaActualizacion.NUEVOS in p.categorias_actualizacion for p in i.origen.busquedas)),
        'actualizados': contar(lambda i: any(CategoriaActualizacion.CAMBIO_PRECIO in p.categorias_actualizacion for p in i.origen.busquedas)),
        'ausentes': contar(lambda i: any(p.disponibilidad in (Disponibilidad.POSIBLEMENTE_RETIRADO, Disponibilidad.RETIRADO) for p in i.origen.busquedas))}


def resumen_clientes(s, seguimiento, todos):
    oportunidades = s.oportunidades()
    salida = []
    for c in s.clientes():
        propias = [o for o in oportunidades if o.cliente_id == c.id]
        abiertas = [o for o in propias if o.estado == 'abierta']
        pendientes, actividad = 0, c.actualizado_en.isoformat()
        actividad_tipo = 'Cliente actualizado'
        for o in propias:
            decisiones = seguimiento.decisiones(o.id)
            ejecucion = seguimiento.leer(o.id)
            eventos = [(o.actualizado_en.isoformat(), 'Necesidades actualizadas'),
                       *((d['actualizado'], 'Decisión guardada') for d in decisiones.values())]
            if ejecucion:
                eventos.append((ejecucion['actualizado'], 'Coincidencias actualizadas' if ejecucion['estado'] == 'listo' else 'Matching en curso'))
            ultima, tipo = max(eventos)
            if ultima >= actividad:
                actividad, actividad_tipo = ultima, tipo
            if o.estado == 'abierta':
                pendientes += sum(decisiones.get(r.inmueble.id_interno, {}).get('estado', 'pendiente') == 'pendiente' for r in buscar(o.necesidades, todos))
        principal = abiertas[0] if abiertas else propias[0] if propias else None
        salida.append({'cliente': c, 'oportunidad': principal, 'abiertas': len(abiertas),
                       'pendientes': pendientes, 'actividad': actividad, 'actividad_tipo': actividad_tipo,
                       'activo': seguimiento.activo(c.id)})
    return sorted(salida, key=lambda r: (r['pendientes'] > 0, r['actividad']), reverse=True)
