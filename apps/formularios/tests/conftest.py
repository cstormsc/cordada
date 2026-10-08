import pytest

from apps.core.tenancy import tenant_context
from apps.formularios.models import Cuestionario, Opcion, Pregunta


@pytest.fixture
def make_cuestionario(acme, equipo):
    def make(n_preguntas=0, **kwargs):
        with tenant_context(acme):
            c = Cuestionario.objects.create(titulo="Nuevo flujo", creado_por=equipo, **kwargs)
            for i in range(n_preguntas):
                p = Pregunta.objects.create(cuestionario=c, orden=i + 1, texto=f"P{i + 1}")
                Opcion.objects.create(pregunta=p, texto="Bien", correcta=True, orden=1)
                Opcion.objects.create(pregunta=p, texto="Mal", orden=2)
            if n_preguntas:
                from apps.formularios.scoring import redistribute

                redistribute(c)
        return c

    return make
