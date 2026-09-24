from odoo import fields, models

TIPOS_EQUIPO = [
    ('excavadora', 'Excavadora'),
    ('retroexcavadora', 'Retroexcavadora'),
    ('grua', 'Grúa'),
    ('hormigonera', 'Hormigonera'),
    ('camion', 'Camión'),
    ('compactadora', 'Compactadora'),
    ('otro', 'Otro'),
]


class ObradorEquipo(models.Model):
    _name = 'obrador.equipo'
    _description = 'Equipo'
    _order = 'name'

    name = fields.Char('Nombre', required=True)
    codigo = fields.Char('Código interno')
    tipo = fields.Selection(TIPOS_EQUIPO, string='Tipo', required=True, default='otro')
    active = fields.Boolean('Activo', default=True)
    company_id = fields.Many2one(
        'res.company', string='Compañía', required=True, default=lambda self: self.env.company
    )
    currency_id = fields.Many2one(related='company_id.currency_id')
    costo_hora = fields.Monetary('Costo por hora')
    uso_ids = fields.One2many('obrador.uso.equipo', 'equipo_id', string='Usos')

    _codigo_unico = models.Constraint(
        'UNIQUE(codigo, company_id)',
        'Ya existe un equipo con ese código interno.',
    )
