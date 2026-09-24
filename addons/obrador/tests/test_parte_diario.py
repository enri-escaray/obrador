from datetime import timedelta

from psycopg2 import IntegrityError

from odoo import Command
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import tagged
from odoo.tools import mute_logger

from .common import ObradorCase


@tagged('post_install', '-at_install')
class TestParteDiario(ObradorCase):
    def test_crear_parte_con_materiales_y_equipos(self):
        parte = self._crear_parte(
            avance=12.5,
            consumo_ids=[self._linea_consumo(cantidad=12)],
            uso_equipo_ids=[self._linea_equipo(horas=6.5)],
        )
        self.assertTrue(parte.name.startswith('PD/'))
        self.assertEqual(parte.estado, 'borrador')
        self.assertEqual(parte.company_id, self.obra.company_id)

        consumo = parte.consumo_ids
        self.assertEqual(consumo.uom_id, self.cemento.uom_id)
        self.assertEqual(consumo.obra_id, self.obra)
        self.assertEqual(consumo.fecha, parte.fecha)

        uso = parte.uso_equipo_ids
        self.assertEqual(uso.costo_hora, 50.0)
        self.assertEqual(uso.costo, 325.0)
        self.assertEqual(parte.horas_equipo, 6.5)
        self.assertEqual(parte.costo_equipos, 325.0)

    def test_costo_hora_queda_fijado_al_cargar(self):
        parte = self._crear_parte(uso_equipo_ids=[self._linea_equipo(horas=2)])
        self.retro.costo_hora = 80.0
        self.assertEqual(parte.uso_equipo_ids.costo, 100.0)

    def test_avance_fuera_de_rango(self):
        for avance in (-1.0, 100.5):
            with self.subTest(avance=avance), self.assertRaises(ValidationError):
                self._crear_parte(avance=avance)

    def test_fecha_futura(self):
        with self.assertRaises(ValidationError):
            self._crear_parte(dias_atras=-2)

    def test_fecha_anterior_al_inicio_de_la_obra(self):
        dias_desde_el_inicio = (self.hoy - self.obra.fecha_inicio).days
        with self.assertRaises(ValidationError):
            self._crear_parte(dias_atras=dias_desde_el_inicio + 1)

    def test_solo_obras_en_curso(self):
        planificada = self._crear_obra('Obra sin iniciar', iniciar=False)
        with self.assertRaises(ValidationError):
            self._crear_parte(obra=planificada)

        self.obra.action_suspender()
        with self.assertRaises(ValidationError):
            self._crear_parte()

    def test_un_parte_por_obra_y_por_dia(self):
        self._crear_parte(dias_atras=3)
        with self.assertRaises(IntegrityError), mute_logger('odoo.sql_db'):
            self._crear_parte(dias_atras=3)
            self.env.flush_all()

    def test_cantidades_y_horas_invalidas(self):
        with self.assertRaises(ValidationError):
            self._crear_parte(consumo_ids=[self._linea_consumo(cantidad=0)])
        for horas in (0, 24.5):
            with self.subTest(horas=horas), self.assertRaises(ValidationError):
                self._crear_parte(uso_equipo_ids=[self._linea_equipo(horas=horas)])

    def test_parte_confirmado_queda_bloqueado(self):
        parte = self._crear_parte(consumo_ids=[self._linea_consumo()])
        parte.action_confirmar()
        self.assertEqual(parte.estado, 'confirmado')

        with self.assertRaises(UserError):
            parte.avance = 50.0
        with self.assertRaises(UserError):
            parte.consumo_ids = [self._linea_consumo(producto=self.arena)]
        with self.assertRaises(UserError):
            parte.consumo_ids.cantidad = 99
        with self.assertRaises(UserError):
            self.env['obrador.uso.equipo'].create(
                {'parte_id': parte.id, 'equipo_id': self.retro.id, 'horas': 1}
            )
        with self.assertRaises(UserError):
            parte.consumo_ids.unlink()
        with self.assertRaises(UserError):
            parte.unlink()
        with self.assertRaises(UserError):
            parte.action_confirmar()

        # El chatter sigue disponible para dejar comentarios.
        parte.message_post(body='Revisado en obra.')

    def test_volver_a_borrador_permite_corregir(self):
        parte = self._crear_parte(avance=40.0)
        parte.action_confirmar()
        parte.action_volver_borrador()
        parte.avance = 42.0
        self.assertEqual(parte.avance, 42.0)

    def test_solo_el_responsable_confirma_y_reabre(self):
        parte = self._crear_parte()
        with self.assertRaises(AccessError):
            parte.with_user(self.usuario).action_confirmar()

        parte.with_user(self.responsable).action_confirmar()
        self.assertEqual(parte.estado, 'confirmado')

        with self.assertRaises(AccessError):
            parte.with_user(self.usuario).action_volver_borrador()

    def test_usuario_carga_partes_pero_no_los_elimina(self):
        parte = (
            self.env['obrador.parte.diario']
            .with_user(self.usuario)
            .create(
                {
                    'obra_id': self.obra.id,
                    'fecha': self.hoy - timedelta(days=1),
                    'avance': 5.0,
                    'consumo_ids': [self._linea_consumo(cantidad=3)],
                    'uso_equipo_ids': [self._linea_equipo(horas=2)],
                }
            )
        )
        self.assertEqual(parte.create_uid, self.usuario)

        parte.write({'observaciones': 'Se corrigió la cantidad', 'consumo_ids': [Command.clear()]})
        self.assertFalse(parte.consumo_ids)

        with self.assertRaises(AccessError):
            parte.unlink()

    def test_duplicar_parte_no_copia_fecha_ni_estado(self):
        parte = self._crear_parte(dias_atras=4, consumo_ids=[self._linea_consumo()])
        parte.action_confirmar()
        copia = parte.copy()
        self.assertEqual(copia.estado, 'borrador')
        self.assertEqual(copia.fecha, self.hoy)
        self.assertNotEqual(copia.name, parte.name)
        self.assertEqual(len(copia.consumo_ids), 1)
