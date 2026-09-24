from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError

ESTADOS_OBRA = [
    ('planificada', 'Planificada'),
    ('en_curso', 'En curso'),
    ('suspendida', 'Suspendida'),
    ('finalizada', 'Finalizada'),
    ('cancelada', 'Cancelada'),
]


class ObradorObra(models.Model):
    _name = 'obrador.obra'
    _description = 'Obra'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'fecha_inicio desc, id desc'
    _rec_names_search = ['name', 'codigo']

    name = fields.Char('Nombre', required=True, tracking=True)
    codigo = fields.Char('Código', required=True, readonly=True, copy=False, default='Nuevo')
    active = fields.Boolean('Activa', default=True)
    estado = fields.Selection(
        ESTADOS_OBRA,
        string='Estado',
        required=True,
        default='planificada',
        copy=False,
        readonly=True,
        tracking=True,
    )
    cliente_id = fields.Many2one('res.partner', string='Cliente', tracking=True)
    responsable_id = fields.Many2one(
        'res.users', string='Jefe de obra', default=lambda self: self.env.user, tracking=True
    )
    direccion = fields.Char('Ubicación')
    fecha_inicio = fields.Date('Fecha de inicio', tracking=True)
    fecha_fin_prevista = fields.Date('Fin previsto', tracking=True)
    company_id = fields.Many2one(
        'res.company', string='Compañía', required=True, default=lambda self: self.env.company
    )
    currency_id = fields.Many2one(related='company_id.currency_id')
    presupuesto = fields.Monetary('Presupuesto')
    descripcion = fields.Html('Descripción')

    parte_ids = fields.One2many('obrador.parte.diario', 'obra_id', string='Partes diarios')
    parte_count = fields.Integer('Cantidad de partes', compute='_compute_parte_count')
    avance_actual = fields.Float(
        'Avance actual (%)',
        compute='_compute_avance_actual',
        store=True,
        aggregator='avg',
        help='Avance del último parte diario confirmado.',
    )
    fecha_ultimo_parte = fields.Date(
        'Último parte confirmado', compute='_compute_avance_actual', store=True
    )

    _codigo_unico = models.Constraint(
        'UNIQUE(codigo, company_id)',
        'Ya existe una obra con ese código.',
    )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('codigo', 'Nuevo') == 'Nuevo':
                vals['codigo'] = self.env['ir.sequence'].next_by_code('obrador.obra') or 'Nuevo'
        return super().create(vals_list)

    @api.depends('codigo', 'name')
    def _compute_display_name(self):
        for obra in self:
            obra.display_name = f'[{obra.codigo}] {obra.name}' if obra.codigo else obra.name

    def _compute_parte_count(self):
        grupos = self.env['obrador.parte.diario']._read_group(
            [('obra_id', 'in', self.ids)], ['obra_id'], ['__count']
        )
        cantidades = {obra.id: cantidad for obra, cantidad in grupos}
        for obra in self:
            obra.parte_count = cantidades.get(obra.id, 0)

    @api.depends('parte_ids.estado', 'parte_ids.avance', 'parte_ids.fecha')
    def _compute_avance_actual(self):
        for obra in self:
            confirmados = obra.parte_ids.filtered(lambda parte: parte.estado == 'confirmado')
            # Un parte por obra y por día: la fecha alcanza para encontrar el último.
            ultimo = confirmados.sorted('fecha')[-1:]
            obra.avance_actual = ultimo.avance
            obra.fecha_ultimo_parte = ultimo.fecha

    @api.constrains('fecha_inicio', 'fecha_fin_prevista')
    def _check_fechas(self):
        for obra in self:
            if (
                obra.fecha_inicio
                and obra.fecha_fin_prevista
                and obra.fecha_fin_prevista < obra.fecha_inicio
            ):
                raise ValidationError(
                    self.env._(
                        'La fecha de fin prevista no puede ser anterior al inicio de la obra.'
                    )
                )

    @api.ondelete(at_uninstall=False)
    def _unlink_excepto_con_partes(self):
        if self.parte_ids:
            raise UserError(
                self.env._(
                    'No se puede eliminar una obra con partes diarios. '
                    'Podés archivarla o cancelarla.'
                )
            )

    # ------------------------------------------------------------------
    # Ciclo de vida
    # ------------------------------------------------------------------

    def action_iniciar(self):
        self._cambiar_estado('en_curso', desde={'planificada'})
        for obra in self.filtered(lambda obra: not obra.fecha_inicio):
            obra.fecha_inicio = fields.Date.context_today(obra)

    def action_suspender(self):
        self._cambiar_estado('suspendida', desde={'en_curso'})

    def action_reanudar(self):
        self._cambiar_estado('en_curso', desde={'suspendida'})

    def action_finalizar(self):
        self._cambiar_estado('finalizada', desde={'en_curso', 'suspendida'})

    def action_cancelar(self):
        self._cambiar_estado('cancelada', desde={'planificada', 'en_curso', 'suspendida'})

    def _cambiar_estado(self, nuevo, desde):
        invalidas = self.filtered(lambda obra: obra.estado not in desde)
        if invalidas:
            raise UserError(
                self.env._(
                    'No se puede pasar a "%(estado)s" desde el estado actual: %(obras)s.',
                    estado=dict(ESTADOS_OBRA)[nuevo],
                    obras=', '.join(invalidas.mapped('display_name')),
                )
            )
        self.estado = nuevo

    def action_ver_partes(self):
        self.ensure_one()
        accion = self.env['ir.actions.act_window']._for_xml_id('obrador.action_parte_diario')
        accion['domain'] = [('obra_id', '=', self.id)]
        accion['context'] = {'default_obra_id': self.id}
        return accion
