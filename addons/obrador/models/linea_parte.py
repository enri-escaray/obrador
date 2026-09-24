from odoo import api, fields, models


class ObradorLineaParte(models.AbstractModel):
    """Base común de las líneas de un parte diario (materiales y equipos).

    Replica en las líneas el bloqueo del parte: si el parte está confirmado,
    sus líneas no se pueden crear, modificar ni eliminar.
    """

    _name = 'obrador.linea.parte'
    _description = 'Línea de parte diario'

    parte_id = fields.Many2one(
        'obrador.parte.diario',
        string='Parte diario',
        required=True,
        index=True,
        ondelete='cascade',
    )
    obra_id = fields.Many2one(related='parte_id.obra_id', store=True, index=True)
    fecha = fields.Date(related='parte_id.fecha', store=True)
    company_id = fields.Many2one(related='parte_id.company_id', store=True, index=True)

    @api.model_create_multi
    def create(self, vals_list):
        partes_ids = {vals['parte_id'] for vals in vals_list if vals.get('parte_id')}
        self.env['obrador.parte.diario'].browse(partes_ids)._check_editable()
        return super().create(vals_list)

    def write(self, vals):
        self.parte_id._check_editable()
        resultado = super().write(vals)
        if 'parte_id' in vals:
            self.parte_id._check_editable()
        return resultado

    @api.ondelete(at_uninstall=False)
    def _unlink_excepto_parte_confirmado(self):
        self.parte_id._check_editable()
