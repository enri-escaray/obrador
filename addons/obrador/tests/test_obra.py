from datetime import timedelta

from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import tagged

from .common import ObradorCase


@tagged('post_install', '-at_install')
class TestObra(ObradorCase):
    def test_codigo_secuencial_y_nombre_visible(self):
        otra = self.env['obrador.obra'].create({'name': 'Otra obra'})
        self.assertTrue(otra.codigo.startswith('OB-'))
        self.assertNotEqual(otra.codigo, self.obra.codigo)
        self.assertEqual(otra.display_name, f'[{otra.codigo}] Otra obra')

    def test_busqueda_por_codigo(self):
        encontradas = self.env['obrador.obra'].name_search(self.obra.codigo)
        self.assertIn(self.obra.id, [obra_id for obra_id, _nombre in encontradas])

    def test_ciclo_de_vida(self):
        obra = self.env['obrador.obra'].create({'name': 'Obra nueva'})
        self.assertEqual(obra.estado, 'planificada')

        obra.action_iniciar()
        self.assertEqual(obra.estado, 'en_curso')
        self.assertTrue(obra.fecha_inicio, 'Iniciar la obra completa la fecha de inicio')

        obra.action_suspender()
        self.assertEqual(obra.estado, 'suspendida')
        obra.action_reanudar()
        self.assertEqual(obra.estado, 'en_curso')
        obra.action_finalizar()
        self.assertEqual(obra.estado, 'finalizada')

    def test_transiciones_invalidas(self):
        obra = self.env['obrador.obra'].create({'name': 'Obra planificada'})
        with self.assertRaises(UserError):
            obra.action_suspender()
        with self.assertRaises(UserError):
            obra.action_finalizar()

        obra.action_cancelar()
        with self.assertRaises(UserError):
            obra.action_iniciar()
        with self.assertRaises(UserError):
            obra.action_cancelar()

    def test_iniciar_respeta_fecha_de_inicio_cargada(self):
        inicio = self.hoy - timedelta(days=90)
        obra = self.env['obrador.obra'].create({'name': 'Obra', 'fecha_inicio': inicio})
        obra.action_iniciar()
        self.assertEqual(obra.fecha_inicio, inicio)

    def test_fin_previsto_anterior_al_inicio(self):
        with self.assertRaises(ValidationError):
            self.env['obrador.obra'].create(
                {
                    'name': 'Obra con fechas invertidas',
                    'fecha_inicio': self.hoy,
                    'fecha_fin_prevista': self.hoy - timedelta(days=1),
                }
            )

    def test_avance_actual_toma_el_ultimo_parte_confirmado(self):
        primero = self._crear_parte(dias_atras=3, avance=10.0)
        segundo = self._crear_parte(dias_atras=2, avance=25.0)
        borrador = self._crear_parte(dias_atras=1, avance=30.0)
        self.assertEqual(self.obra.avance_actual, 0.0, 'Los borradores no mueven el avance')

        (primero | segundo).action_confirmar()
        self.assertEqual(self.obra.avance_actual, 25.0)
        self.assertEqual(self.obra.fecha_ultimo_parte, segundo.fecha)

        borrador.action_confirmar()
        self.assertEqual(self.obra.avance_actual, 30.0)

        borrador.action_volver_borrador()
        self.assertEqual(self.obra.avance_actual, 25.0)

    def test_cantidad_de_partes_y_accion(self):
        self._crear_parte(dias_atras=2)
        self._crear_parte(dias_atras=1)
        self.assertEqual(self.obra.parte_count, 2)

        accion = self.obra.action_ver_partes()
        self.assertEqual(accion['res_model'], 'obrador.parte.diario')
        self.assertEqual(accion['domain'], [('obra_id', '=', self.obra.id)])
        self.assertEqual(accion['context'], {'default_obra_id': self.obra.id})

    def test_no_se_elimina_una_obra_con_partes(self):
        self._crear_parte()
        with self.assertRaises(UserError):
            self.obra.unlink()

    def test_obra_sin_partes_se_puede_eliminar(self):
        obra = self.env['obrador.obra'].create({'name': 'Obra descartada'})
        obra.unlink()
        self.assertFalse(obra.exists())

    def test_usuario_consulta_pero_no_gestiona_obras(self):
        obra_como_usuario = self.obra.with_user(self.usuario)
        self.assertEqual(obra_como_usuario.name, 'Obra de prueba')
        with self.assertRaises(AccessError):
            self.env['obrador.obra'].with_user(self.usuario).create({'name': 'No autorizada'})
        with self.assertRaises(AccessError):
            obra_como_usuario.name = 'Cambio no autorizado'

    def test_responsable_gestiona_obras(self):
        obra = self.env['obrador.obra'].with_user(self.responsable).create({'name': 'Obra propia'})
        obra.action_iniciar()
        self.assertEqual(obra.estado, 'en_curso')
        self.assertEqual(obra.responsable_id, self.responsable)
