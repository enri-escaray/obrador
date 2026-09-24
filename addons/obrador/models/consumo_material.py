from odoo import api, fields, models
from odoo.exceptions import ValidationError


class ObradorConsumoMaterial(models.Model):
    _name = 'obrador.consumo.material'
    _description = 'Consumo de material'
    _inherit = ['obrador.linea.parte']
    _order = 'parte_id, id'
    _check_company_auto = True

    product_id = fields.Many2one(
        'product.product',
        string='Material',
        required=True,
        check_company=True,
        domain=[('type', '=', 'consu')],
    )
    cantidad = fields.Float('Cantidad', required=True, default=1.0, digits='Product Unit')
    uom_id = fields.Many2one(related='product_id.uom_id', string='Unidad')
    notas = fields.Char('Notas')

    @api.constrains('cantidad')
    def _check_cantidad(self):
        if any(linea.cantidad <= 0 for linea in self):
            raise ValidationError(self.env._('La cantidad consumida debe ser mayor a cero.'))
