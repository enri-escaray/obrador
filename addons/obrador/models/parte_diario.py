from odoo import api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError

ESTADOS_PARTE = [
    ('borrador', 'Borrador'),
    ('confirmado', 'Confirmado'),
]

CLIMAS = [
    ('soleado', 'Soleado'),
    ('nublado', 'Nublado'),
    ('lluvia', 'Lluvia'),
    ('tormenta', 'Tormenta'),
    ('viento', 'Viento fuerte'),
]

# Campos que no se pueden modificar una vez confirmado el parte.
CAMPOS_BLOQUEADOS = frozenset(
    {'obra_id', 'fecha', 'avance', 'clima', 'observaciones', 'consumo_ids', 'uso_equipo_ids'}
)


class ObradorParteDiario(models.Model):
    _name = 'obrador.parte.diario'
    _description = 'Parte diario de obra'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'fecha desc, id desc'

    name = fields.Char('Referencia', required=True, readonly=True, copy=False, default='Nuevo')
    obra_id = fields.Many2one(
        'obrador.obra',
        string='Obra',
        required=True,
        index=True,
        ondelete='restrict',
        tracking=True,
        domain="[('estado', '=', 'en_curso')]",
    )
    fecha = fields.Date(
        'Fecha', required=True, default=fields.Date.context_today, copy=False, tracking=True
    )
    avance = fields.Float(
        'Avance (%)',
        digits=(5, 2),
        aggregator='max',
        tracking=True,
        help='Avance físico acumulado de la obra a la fecha del parte, de 0 a 100.',
    )
    clima = fields.Selection(CLIMAS, string='Clima')
    observaciones = fields.Text('Observaciones')
    estado = fields.Selection(
        ESTADOS_PARTE,
        string='Estado',
        required=True,
        default='borrador',
        copy=False,
        readonly=True,
        tracking=True,
    )
    consumo_ids = fields.One2many(
        'obrador.consumo.material', 'parte_id', string='Consumo de materiales', copy=True
    )
    uso_equipo_ids = fields.One2many(
        'obrador.uso.equipo', 'parte_id', string='Uso de equipos', copy=True
    )
    company_id = fields.Many2one(related='obra_id.company_id', store=True, index=True)
    currency_id = fields.Many2one(related='company_id.currency_id')
    horas_equipo = fields.Float('Horas de equipo', compute='_compute_totales_equipos', store=True)
    costo_equipos = fields.Monetary(
        'Costo de equipos', compute='_compute_totales_equipos', store=True
    )

    _parte_unico_por_dia = models.Constraint(
        'UNIQUE(obra_id, fecha)',
        'Ya existe un parte diario para esa obra en esa fecha.',
    )

    @api.model_create_multi
    def create(self, vals_list):
        secuencias = self.env['ir.sequence']
        for vals in vals_list:
            if vals.get('name', 'Nuevo') == 'Nuevo':
                vals['name'] = (
                    secuencias.next_by_code('obrador.parte.diario', sequence_date=vals.get('fecha'))
                    or 'Nuevo'
                )
        return super().create(vals_list)

    def write(self, vals):
        if not CAMPOS_BLOQUEADOS.isdisjoint(vals):
            self._check_editable()
        return super().write(vals)

    @api.ondelete(at_uninstall=False)
    def _unlink_excepto_confirmado(self):
        self._check_editable()

    @api.depends('uso_equipo_ids.horas', 'uso_equipo_ids.costo')
    def _compute_totales_equipos(self):
        for parte in self:
            parte.horas_equipo = sum(parte.uso_equipo_ids.mapped('horas'))
            parte.costo_equipos = sum(parte.uso_equipo_ids.mapped('costo'))

    @api.constrains('avance')
    def _check_avance(self):
        for parte in self:
            if not 0 <= parte.avance <= 100:
                raise ValidationError(self.env._('El avance debe estar entre 0 y 100.'))

    @api.constrains('fecha', 'obra_id')
    def _check_fecha(self):
        for parte in self:
            if parte.fecha > fields.Date.context_today(parte):
                raise ValidationError(self.env._('La fecha del parte no puede ser futura.'))
            if parte.obra_id.fecha_inicio and parte.fecha < parte.obra_id.fecha_inicio:
                raise ValidationError(
                    self.env._('La fecha del parte no puede ser anterior al inicio de la obra.')
                )

    @api.constrains('obra_id')
    def _check_obra_en_curso(self):
        for parte in self:
            if parte.obra_id.estado != 'en_curso':
                raise ValidationError(
                    self.env._(
                        'Solo se pueden cargar partes diarios en obras en curso '
                        '(%(obra)s no lo está).',
                        obra=parte.obra_id.display_name,
                    )
                )

    def _check_editable(self):
        if any(parte.estado == 'confirmado' for parte in self):
            raise UserError(
                self.env._(
                    'Un parte diario confirmado no se puede modificar ni eliminar. '
                    'Si hace falta corregirlo, un responsable debe volverlo a borrador.'
                )
            )

    def _check_responsable(self):
        if not (self.env.su or self.env.user.has_group('obrador.group_obrador_responsable')):
            raise AccessError(
                self.env._('Solo un responsable de obra puede confirmar o reabrir partes diarios.')
            )

    def action_confirmar(self):
        self._check_responsable()
        if any(parte.estado != 'borrador' for parte in self):
            raise UserError(self.env._('Solo se pueden confirmar partes en borrador.'))
        self.estado = 'confirmado'

    def action_volver_borrador(self):
        self._check_responsable()
        self.estado = 'borrador'
