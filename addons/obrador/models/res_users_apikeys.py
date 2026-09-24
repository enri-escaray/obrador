from odoo import fields, models

# Scope de las API keys que habilitan la API REST del módulo. Una key con este
# scope solo sirve para /api/obrador/*: no da acceso a XML-RPC ni a JSON-2.
API_SCOPE = 'obrador'


class ResUsersApikeysDescription(models.TransientModel):
    _inherit = 'res.users.apikeys.description'

    scope = fields.Selection(
        selection_add=[(API_SCOPE, 'Obrador (API de partes diarios)')],
        ondelete={API_SCOPE: 'cascade'},
    )
