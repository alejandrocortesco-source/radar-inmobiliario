"""Proyecciones pequeñas para el dashboard; sin SQL ni cambios al catálogo."""
from catalogo.modelos import CategoriaActualizacion, Disponibilidad
from oportunidades.matching import buscar


def indicadores(todos, ultima):
    return {'total': len(todos), 'ultima': ultima,
        'nuevos': sum(any(CategoriaActualizacion.NUEVOS in p.categorias_actualizacion for p in i.origen.busquedas) for i in todos),
        'actualizados': sum(any(CategoriaActualizacion.CAMBIO_PRECIO in p.categorias_actualizacion for p in i.origen.busquedas) for i in todos),
        'ausentes': sum(any(p.disponibilidad in (Disponibilidad.POSIBLEMENTE_RETIRADO, Disponibilidad.RETIRADO) for p in i.origen.busquedas) for i in todos)}


def resumen_clientes(s, seguimiento, todos):
    oportunidades = s.oportunidades()
    salida = []
    for c in s.clientes():
        propias = [o for o in oportunidades if o.cliente_id == c.id]
        abiertas = [o for o in propias if o.estado == 'abierta']
        pendientes, actividad = 0, c.actualizado_en.isoformat()
        for o in propias:
            decisiones = seguimiento.decisiones(o.id)
            ejecucion = seguimiento.leer(o.id)
            fechas = [o.actualizado_en.isoformat(), *(d['actualizado'] for d in decisiones.values())]
            if ejecucion:
                fechas.append(ejecucion['actualizado'])
            actividad = max(actividad, *fechas)
            if o.estado == 'abierta':
                pendientes += sum(decisiones.get(r.inmueble.id_interno, {}).get('estado', 'pendiente') == 'pendiente' for r in buscar(o.necesidades, todos))
        principal = abiertas[0] if abiertas else propias[0] if propias else None
        salida.append({'cliente': c, 'oportunidad': principal, 'abiertas': len(abiertas),
                       'pendientes': pendientes, 'actividad': actividad, 'activo': seguimiento.activo(c.id)})
    return sorted(salida, key=lambda r: (r['pendientes'] > 0, r['actividad']), reverse=True)
