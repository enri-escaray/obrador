from datetime import timedelta

from odoo import Command, fields
from odoo.tests import TransactionCase, new_test_user


class ObradorDatosMixin:
    """Datos base compartidos por los tests de modelos y de la API."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.hoy = fields.Date.context_today(cls.env.user)
        cls.usuario = new_test_user(
            cls.env, login='capataz_obrador', groups='obrador.group_obrador_usuario'
        )
        cls.responsable = new_test_user(
            cls.env, login='jefe_obrador', groups='obrador.group_obrador_responsable'
        )
        cls.cemento = cls.env['product.product'].create({'name': 'Cemento (test)', 'type': 'consu'})
        cls.arena = cls.env['product.product'].create({'name': 'Arena (test)', 'type': 'consu'})
        cls.retro = cls.env['obrador.equipo'].create(
            {'name': 'Retroexcavadora (test)', 'tipo': 'retroexcavadora', 'costo_hora': 50.0}
        )
        cls.obra = cls._crear_obra('Obra de prueba')

    @classmethod
    def _crear_obra(cls, nombre, iniciar=True):
        obra = cls.env['obrador.obra'].create(
            {'name': nombre, 'fecha_inicio': cls.hoy - timedelta(days=60)}
        )
        if iniciar:
            obra.action_iniciar()
        return obra

    def _crear_parte(self, dias_atras=5, obra=None, **valores):
        valores.setdefault('avance', 10.0)
        return self.env['obrador.parte.diario'].create(
            {
                'obra_id': (obra or self.obra).id,
                'fecha': self.hoy - timedelta(days=dias_atras),
                **valores,
            }
        )

    def _linea_consumo(self, producto=None, cantidad=1.0):
        return Command.create({'product_id': (producto or self.cemento).id, 'cantidad': cantidad})

    def _linea_equipo(self, horas=1.0, equipo=None):
        return Command.create({'equipo_id': (equipo or self.retro).id, 'horas': horas})


class ObradorCase(ObradorDatosMixin, TransactionCase):
    pass
