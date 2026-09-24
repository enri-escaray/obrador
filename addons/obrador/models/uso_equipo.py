from odoo import api, fields, models
from odoo.exceptions import ValidationError


class ObradorUsoEquipo(models.Model):
    _name = 'obrador.uso.equipo'
    _description = 'Uso de equipo'
    _inherit = ['obrador.linea.parte']
    _order = 'parte_id, id'
    _check_company_auto = True

    equipo_id = fields.Many2one(
        'obrador.equipo', string='Equipo', required=True, index=True, check_company=True
    )
    horas = fields.Float('Horas', required=True, digits=(4, 2))
    operador = fields.Char('Operador')
    currency_id = fields.Many2one(related='company_id.currency_id')
    # Se copia del equipo al cargar la línea: si después cambia la tarifa del
    # equipo, los partes ya cargados conservan el costo de ese momento.
    costo_hora = fields.Monetary(
        'Costo por hora',
        compute='_compute_costo_hora',
        store=True,
        readonly=False,
        precompute=True,
    )
    costo = fields.Monetary('Costo', compute='_compute_costo', store=True)

    @api.depends('equipo_id')
    def _compute_costo_hora(self):
        for linea in self:
            linea.costo_hora = linea.equipo_id.costo_hora

    @api.depends('horas', 'costo_hora')
    def _compute_costo(self):
        for linea in self:
            linea.costo = linea.horas * linea.costo_hora

    @api.constrains('horas')
    def _check_horas(self):
        if any(not 0 < linea.horas <= 24 for linea in self):
            raise ValidationError(self.env._('Las horas de uso deben ser mayores a 0 y hasta 24.'))
