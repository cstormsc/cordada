import pytest

from apps.aprendizaje.models import Bloque, Curso, Leccion
from apps.core.tenancy import tenant_context
from apps.formularios.models import Cuestionario, EstadoCuestionario


@pytest.fixture
def make_curso(acme, equipo):
    def make(n_lecciones=0, **kwargs):
        with tenant_context(acme):
            c = Curso.objects.create(titulo="Nuevo flujo de cobranza", creado_por=equipo, **kwargs)
            for i in range(n_lecciones):
                leccion = Leccion.objects.create(curso=c, orden=i + 1, titulo=f"L{i + 1}")
                Bloque.objects.create(
                    leccion=leccion, orden=1, tipo="texto", texto=f"Texto {i + 1}"
                )
        return c

    return make


@pytest.fixture
def make_evaluacion(acme, equipo):
    def make(estado=EstadoCuestionario.PUBLICADO):
        with tenant_context(acme):
            return Cuestionario.objects.create(titulo="Prueba", creado_por=equipo, estado=estado)

    return make
