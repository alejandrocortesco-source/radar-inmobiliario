"""Coordinación de reservas, selección autoritativa y consulta sin SQLite ocupado."""
import os
import tempfile
from pathlib import Path
from google.api_core.exceptions import PreconditionFailed, NotFound
from catalogo.persistencia.busquedas import BusquedasSQLite
from wasi.durable import EstadoGCS
from .control import ControlGCS, ACTIVE, Conflict, now, projection, select, reserve
from .cloud_run import reconcile, cloud_configurado


class ServicioEjecuciones:
    def __init__(self, control=None, cloud=None, state_factory=None, data_dir=None):
        self.control = control or ControlGCS()
        self.cloud = cloud or cloud_configurado(os.getenv('RADAR_EXECUTION_JOB', 'radar-manual'))
        self.state_factory = state_factory or (lambda: EstadoGCS(os.environ['RADAR_STATE_BUCKET'], os.getenv('RADAR_STATE_OBJECT', 'radar/state.tar.gz')))
        self.data_dir = data_dir or os.getenv('RADAR_DATA_DIR', '/data')

    def unlock(self, generation=None, token=None):
        # Solo generación anotada por el trabajador y tras Cloud Run terminal.
        state = self.state_factory()
        try:
            if generation is None:
                if not token:
                    return
                state.lock.reload(timeout=10)
                generation = int(state.lock.generation)
                if state.lock.download_as_bytes(if_generation_match=generation, timeout=10) != token.encode():
                    return
            state.bucket.blob(state.objeto + ".lock").delete(if_generation_match=int(generation), timeout=10)
        except (NotFound, PreconditionFailed):
            pass

    def snapshot_searches(self, action):
        Path(self.data_dir).mkdir(parents=True, exist_ok=True)
        try:
            with self.state_factory() as state, tempfile.TemporaryDirectory(prefix='execution-read-', dir=self.data_dir) as folder:
                state.cargar(folder)
                return action(projection(BusquedasSQLite(Path(folder) / 'metro-consola.sqlite'), Path(folder)))
        except PreconditionFailed:
            raise Conflict('El catálogo está ocupado por otra operación o Job. Puedes consultar el seguimiento y volver a intentar después.') from None

    def overview(self, refresh=False):
        doc = reconcile(self.control, self.cloud, self.unlock)
        warning = None
        if not any(r['status'] in ACTIVE for r in doc['runs']):
            self.control.change(lambda d: None, idle_only=True)  # Retención cuando no hay ejecutor escribiendo.
        if refresh and not any(r['status'] in ACTIVE for r in doc['runs']):
            def sync(rows):
                def mutate(d):
                    if d['searches'] != rows:
                        d.update(searches=rows, catalog_updated=now())
                self.control.change(mutate, idle_only=True)
            try:
                self.snapshot_searches(sync)
            except Conflict as exc:
                warning = str(exc)
            doc = self.control.read()[0]
        return doc, warning

    def start(self, keys, request_id):
        # Reenvío de la misma solicitud devuelve la reserva existente y no llama al Job.
        prior = next((r for r in self.control.read()[0]['runs'] if r['request_id'] == request_id), None)
        if prior:
            canonical = list(dict.fromkeys(tuple(k) for k in keys))
            if [(b['fuente'], b['id_busqueda']) for b in prior['searches']] != canonical:
                raise Conflict('Esta solicitud ya se utilizó para otra selección.')
            return prior
        reconcile(self.control, self.cloud, self.unlock)
        def validated(rows):
            selected = select(rows, keys)
            return reserve(self.control, request_id, selected)
        run, created = self.snapshot_searches(validated)
        if not created:
            return run
        try:
            self.cloud.launch(run['id'])
        except Exception:
            # La reserva ya es durable. No reintentar ni escribir sobre la reclamación
            # concurrente del ejecutor; consultar su UUID en Cloud Run en la siguiente visita.
            pass
        return self.control.get(run['id'])
