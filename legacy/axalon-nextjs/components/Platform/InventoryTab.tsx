'use client'

import { useCallback, useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import {
  Boxes,
  ExternalLink,
  PackagePlus,
  Plus,
  RefreshCw,
  ShoppingCart,
  Trash2,
  Wrench,
} from 'lucide-react'
import {
  api,
  type ComponentCategory,
  type ComponentOrder,
  type InventoryComponent,
  type OrderStatus,
  type Prototype,
  type PrototypeStatus,
} from '@/lib/api'
import {
  formatMoney,
  groupByCategory,
  lowStockComponents,
  orderCostByStatus,
  stockValue,
} from '@/lib/inventory'
import { useToast } from '@/components/Platform/Toast'
import { FieldError } from '@/components/Platform/FieldError'
import {
  addComponentSchema,
  addOrderSchema,
  addPrototypeSchema,
  assignComponentSchema,
  type AddComponentInput,
  type AddOrderInput,
  type AddPrototypeInput,
  type AssignComponentInput,
} from '@/lib/schemas/inventory'
import { queryKeys } from '@/lib/queryKeys'

const EMPTY_COMPONENTS: InventoryComponent[] = []
const EMPTY_PROTOTYPES: Prototype[] = []
const EMPTY_ORDERS: ComponentOrder[] = []

const CATEGORIES: ComponentCategory[] = [
  'flight-controller', 'motor', 'esc', 'battery', 'propeller', 'frame',
  'camera', 'sensor', 'companion-computer', 'radio', 'gps', 'wiring', 'other',
]
const PROTO_STATUSES: PrototypeStatus[] = ['planning', 'building', 'active', 'retired']
const ORDER_STATUSES: OrderStatus[] = ['planned', 'ordered', 'received', 'cancelled']

function Chip({ label, value, tone }: { label: string; value: string; tone: 'info' | 'ok' | 'crit' | 'muted' }) {
  return (
    <div className={`chip chip-${tone}`}>
      <span className="chip-label">{label}</span>
      <span className="chip-value">{value}</span>
    </div>
  )
}

function errMessage(err: unknown): string {
  if (err instanceof Error) {
    // Surface the API's JSON `detail` when present (e.g. availability errors)
    const m = err.message.match(/"detail"\s*:\s*"([^"]+)"/)
    if (m) return m[1]
    return err.message
  }
  return String(err)
}

// ── Components section ────────────────────────────────────────────────────────

const ADD_COMPONENT_DEFAULTS: AddComponentInput = {
  name: '', category: 'other', qty_total: '1', unit_cost: '', vendor: '', link: '',
}

const ADD_ORDER_DEFAULTS: AddOrderInput = {
  name: '', component_id: '', qty: '1', est_cost: '', needed_by: '',
}

function AddComponentForm({ onCreated }: { onCreated: () => void }) {
  const toast = useToast()
  const [isOpen, setIsOpen] = useState(false)
  const {
    register, handleSubmit, reset,
    formState: { errors, isSubmitting },
  } = useForm<AddComponentInput>({
    resolver: zodResolver(addComponentSchema),
    defaultValues: ADD_COMPONENT_DEFAULTS,
  })

  const onSubmit = handleSubmit(async (raw) => {
    const values = addComponentSchema.parse(raw)
    try {
      await api.createComponent(values)
      reset(ADD_COMPONENT_DEFAULTS)
      setIsOpen(false)
      onCreated()
    } catch (err) {
      toast.error(errMessage(err))
    }
  })

  if (!isOpen) {
    return (
      <button type="button" className="secondary" onClick={() => setIsOpen(true)}>
        <Plus size={15} /> Add component
      </button>
    )
  }
  return (
    <form className="inv-form" onSubmit={onSubmit} noValidate>
      <input placeholder="Part name *" {...register('name')} />
      <FieldError message={errors.name?.message} />
      <select {...register('category')}>
        {CATEGORIES.map((c) => <option key={c} value={c}>{c}</option>)}
      </select>
      <input type="number" min={0} placeholder="Qty" {...register('qty_total')} />
      <FieldError message={errors.qty_total?.message} />
      <input type="number" min={0} placeholder="Unit cost ₹" {...register('unit_cost')} />
      <FieldError message={errors.unit_cost?.message} />
      <input placeholder="Vendor" {...register('vendor')} />
      <input placeholder="Product link" {...register('link')} />
      <FieldError message={errors.link?.message} />
      <div className="inv-form-actions">
        <button type="submit" className="primary" disabled={isSubmitting}>Save</button>
        <button type="button" className="secondary" onClick={() => setIsOpen(false)}>Cancel</button>
      </div>
    </form>
  )
}

function ComponentsPanel({
  components,
  onChanged,
}: {
  components: InventoryComponent[]
  onChanged: () => void
}) {
  const toast = useToast()

  async function adjustQty(c: InventoryComponent, delta: number) {
    const next = c.qty_total + delta
    if (next < c.qty_assigned) {
      toast.error(`${c.qty_assigned} unit(s) are installed in prototypes`)
      return
    }
    try {
      await api.updateComponent(c.id, { qty_total: next })
      onChanged()
    } catch (err) {
      toast.error(errMessage(err))
    }
  }

  async function remove(c: InventoryComponent) {
    if (!window.confirm(`Delete "${c.name}" from inventory?`)) return
    try {
      await api.deleteComponent(c.id)
      onChanged()
    } catch (err) {
      toast.error(errMessage(err))
    }
  }

  return (
    <section className="panel">
      <div className="panel-head">
        <div>
          <div className="panel-title"><Boxes size={15} /> Components</div>
          <p>{components.length} part type(s) · stock value {formatMoney(stockValue(components), 'INR')}</p>
        </div>
        <AddComponentForm onCreated={onChanged} />
      </div>

      {components.length === 0 && <div className="empty">No components yet — add your first part above.</div>}

      {groupByCategory(components).map(([category, items]) => (
        <div key={category} className="inv-group">
          <div className="inv-group-title">{category}</div>
          <div className="table">
            <div className="table-head inv-head">
              <span>Part</span>
              <span>Stock</span>
              <span>Installed</span>
              <span>Unit cost</span>
              <span />
            </div>
            {items.map((c) => (
              <div className="inv-row" key={c.id}>
                <span className="inv-part">
                  <strong>{c.name}</strong>
                  <small>
                    {c.vendor || '—'}
                    {c.link && (
                      <a href={c.link} target="_blank" rel="noopener noreferrer" title="Product page">
                        {' '}<ExternalLink size={11} />
                      </a>
                    )}
                  </small>
                </span>
                <span className={c.qty_available < 1 ? 'inv-stock low' : 'inv-stock'}>
                  <button type="button" className="inv-step" onClick={() => adjustQty(c, -1)} title="Remove one">−</button>
                  {c.qty_available} / {c.qty_total}
                  <button type="button" className="inv-step" onClick={() => adjustQty(c, +1)} title="Add one">+</button>
                </span>
                <span>{c.qty_assigned > 0 ? `${c.qty_assigned} installed` : '—'}</span>
                <span>{formatMoney(c.unit_cost, c.currency)}</span>
                <button type="button" className="inv-icon-btn" onClick={() => remove(c)} title="Delete">
                  <Trash2 size={14} />
                </button>
              </div>
            ))}
          </div>
        </div>
      ))}
    </section>
  )
}

// ── Prototypes section ────────────────────────────────────────────────────────

function AssignForm({
  prototype,
  components,
  onChanged,
}: {
  prototype: Prototype
  components: InventoryComponent[]
  onChanged: () => void
}) {
  const toast = useToast()
  const available = components.filter((c) => c.qty_available > 0)
  const {
    register, handleSubmit, reset, watch,
    formState: { errors, isSubmitting },
  } = useForm<AssignComponentInput>({
    resolver: zodResolver(assignComponentSchema),
    defaultValues: { component_id: '', qty: '1' },
  })

  const onSubmit = handleSubmit(async (raw) => {
    const values = assignComponentSchema.parse(raw)
    try {
      await api.createAssignment({
        component_id: Number(values.component_id),
        prototype_id: prototype.id,
        qty: values.qty,
      })
      reset({ component_id: '', qty: '1' })
      onChanged()
    } catch (err) {
      toast.error(errMessage(err))
    }
  })

  if (available.length === 0) return null
  return (
    <form className="inv-assign-form" onSubmit={onSubmit} noValidate>
      <select {...register('component_id')}>
        <option value="">Install a component…</option>
        {available.map((c) => (
          <option key={c.id} value={c.id}>{c.name} ({c.qty_available} avail.)</option>
        ))}
      </select>
      <input type="number" min={1} {...register('qty')} />
      <button type="submit" className="secondary" disabled={!watch('component_id') || isSubmitting}>
        <Wrench size={13} /> Install
      </button>
      <FieldError message={errors.component_id?.message ?? errors.qty?.message} />
    </form>
  )
}

function PrototypeCard({
  prototype,
  components,
  onChanged,
}: {
  prototype: Prototype
  components: InventoryComponent[]
  onChanged: () => void
}) {
  const toast = useToast()

  async function setStatus(status: PrototypeStatus) {
    try {
      await api.updatePrototype(prototype.id, { status })
      onChanged()
    } catch (err) {
      toast.error(errMessage(err))
    }
  }

  async function unassign(assignmentId: number) {
    try {
      await api.deleteAssignment(assignmentId)
      onChanged()
    } catch (err) {
      toast.error(errMessage(err))
    }
  }

  async function remove() {
    if (!window.confirm(`Delete prototype "${prototype.name}"? Its components return to stock.`)) return
    try {
      await api.deletePrototype(prototype.id)
      onChanged()
    } catch (err) {
      toast.error(errMessage(err))
    }
  }

  return (
    <div className="inv-proto-card">
      <div className="inv-proto-head">
        <div>
          <strong>{prototype.name}</strong>
          {prototype.description && <p>{prototype.description}</p>}
        </div>
        <div className="inv-proto-controls">
          <select
            value={prototype.status}
            className={`inv-status inv-status-${prototype.status}`}
            onChange={(e) => setStatus(e.target.value as PrototypeStatus)}
          >
            {PROTO_STATUSES.map((s) => <option key={s} value={s}>{s}</option>)}
          </select>
          <button type="button" className="inv-icon-btn" onClick={remove} title="Delete prototype">
            <Trash2 size={14} />
          </button>
        </div>
      </div>

      {prototype.assignments.length === 0 && (
        <div className="inv-bom-empty">No components installed yet.</div>
      )}
      {prototype.assignments.length > 0 && (
        <ul className="inv-bom">
          {prototype.assignments.map((a) => (
            <li key={a.id}>
              <span className="inv-bom-cat">{a.component_category || 'part'}</span>
              <span className="inv-bom-name">{a.component_name}</span>
              <span className="inv-bom-qty">×{a.qty}</span>
              <button type="button" className="inv-icon-btn" onClick={() => unassign(a.id)} title="Return to stock">
                <Trash2 size={12} />
              </button>
            </li>
          ))}
        </ul>
      )}

      <AssignForm prototype={prototype} components={components} onChanged={onChanged} />
    </div>
  )
}

function PrototypesPanel({
  prototypes,
  components,
  onChanged,
}: {
  prototypes: Prototype[]
  components: InventoryComponent[]
  onChanged: () => void
}) {
  const toast = useToast()
  const {
    register, handleSubmit, reset,
    formState: { errors, isSubmitting },
  } = useForm<AddPrototypeInput>({
    resolver: zodResolver(addPrototypeSchema),
    defaultValues: { name: '', description: '' },
  })

  const onSubmit = handleSubmit(async (raw) => {
    const values = addPrototypeSchema.parse(raw)
    try {
      await api.createPrototype(values)
      reset({ name: '', description: '' })
      onChanged()
    } catch (err) {
      toast.error(errMessage(err))
    }
  })

  return (
    <section className="panel">
      <div className="panel-head">
        <div>
          <div className="panel-title"><Wrench size={15} /> Prototypes & builds</div>
          <p>{prototypes.length} build(s) — each card lists exactly which components it contains</p>
        </div>
      </div>

      <form className="inv-form" onSubmit={onSubmit} noValidate>
        <input placeholder="New prototype name *" {...register('name')} />
        <FieldError message={errors.name?.message} />
        <input placeholder="Description (e.g. thermal quad, 7-inch frame)" {...register('description')} />
        <div className="inv-form-actions">
          <button type="submit" className="primary" disabled={isSubmitting}><Plus size={14} /> Create</button>
        </div>
      </form>

      {prototypes.length === 0 && <div className="empty">No prototypes yet.</div>}
      <div className="inv-proto-grid">
        {prototypes.map((p) => (
          <PrototypeCard key={p.id} prototype={p} components={components} onChanged={onChanged} />
        ))}
      </div>
    </section>
  )
}

// ── Orders section ────────────────────────────────────────────────────────────

function OrdersPanel({
  orders,
  components,
  onChanged,
}: {
  orders: ComponentOrder[]
  components: InventoryComponent[]
  onChanged: () => void
}) {
  const toast = useToast()
  const totals = orderCostByStatus(orders)
  const {
    register, handleSubmit, reset,
    formState: { errors, isSubmitting },
  } = useForm<AddOrderInput>({
    resolver: zodResolver(addOrderSchema),
    defaultValues: ADD_ORDER_DEFAULTS,
  })

  const onSubmit = handleSubmit(async (raw) => {
    const values = addOrderSchema.parse(raw)
    try {
      await api.createOrder({
        name: values.name || undefined,
        component_id: values.component_id ? Number(values.component_id) : null,
        qty: values.qty,
        est_unit_cost: values.est_cost,
        needed_by: values.needed_by,
      })
      reset(ADD_ORDER_DEFAULTS)
      onChanged()
    } catch (err) {
      toast.error(errMessage(err))
    }
  })

  async function setStatus(o: ComponentOrder, status: OrderStatus) {
    try {
      await api.updateOrder(o.id, { status })
      onChanged()
    } catch (err) {
      toast.error(errMessage(err))
    }
  }

  async function remove(o: ComponentOrder) {
    try {
      await api.deleteOrder(o.id)
      onChanged()
    } catch (err) {
      toast.error(errMessage(err))
    }
  }

  return (
    <section className="panel">
      <div className="panel-head">
        <div>
          <div className="panel-title"><ShoppingCart size={15} /> Order planning</div>
          <p>
            Planned {formatMoney(totals.planned, 'INR')} · Ordered {formatMoney(totals.ordered, 'INR')}
            {' '}· Committed {formatMoney(totals.total, 'INR')}
          </p>
        </div>
      </div>

      <form className="inv-form" onSubmit={onSubmit} noValidate>
        <input placeholder="Item to order *" {...register('name')} />
        <FieldError message={errors.name?.message} />
        <select {...register('component_id')}>
          <option value="">Restock existing part…</option>
          {components.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
        </select>
        <input type="number" min={1} placeholder="Qty" {...register('qty')} />
        <FieldError message={errors.qty?.message} />
        <input type="number" min={0} placeholder="Est. unit cost ₹" {...register('est_cost')} />
        <FieldError message={errors.est_cost?.message} />
        <input type="date" {...register('needed_by')} title="Needed by" />
        <div className="inv-form-actions">
          <button type="submit" className="primary" disabled={isSubmitting}><PackagePlus size={14} /> Plan order</button>
        </div>
      </form>

      {orders.length === 0 && <div className="empty">Nothing in the order queue.</div>}
      {orders.length > 0 && (
        <div className="table">
          <div className="table-head inv-order-head">
            <span>Item</span>
            <span>Qty</span>
            <span>Est. cost</span>
            <span>Needed by</span>
            <span>Status</span>
            <span />
          </div>
          {orders.map((o) => (
            <div className="inv-order-row" key={o.id}>
              <span className="inv-part">
                <strong>{o.name}</strong>
                {o.component_id != null && <small>restock → stocks in on receive</small>}
              </span>
              <span>×{o.qty}</span>
              <span>{formatMoney(o.est_unit_cost != null ? o.est_unit_cost * o.qty : null, 'INR')}</span>
              <span>{o.needed_by || '—'}</span>
              <span>
                <select
                  value={o.status}
                  className={`inv-status inv-status-${o.status}`}
                  onChange={(e) => setStatus(o, e.target.value as OrderStatus)}
                >
                  {ORDER_STATUSES.map((s) => <option key={s} value={s}>{s}</option>)}
                </select>
              </span>
              <button type="button" className="inv-icon-btn" onClick={() => remove(o)} title="Delete order">
                <Trash2 size={14} />
              </button>
            </div>
          ))}
        </div>
      )}
    </section>
  )
}

// ── Tab root ──────────────────────────────────────────────────────────────────

export function InventoryTab() {
  const queryClient = useQueryClient()

  // The three lists load in parallel and are cached independently, so a
  // mutation touching only orders no longer refetches components too.
  const componentsQuery = useQuery({
    queryKey: queryKeys.inventory.components,
    queryFn: () => api.inventoryComponents(),
  })
  const prototypesQuery = useQuery({
    queryKey: queryKeys.inventory.prototypes,
    queryFn: () => api.prototypes(),
  })
  const ordersQuery = useQuery({
    queryKey: queryKeys.inventory.orders,
    queryFn: () => api.orders(),
  })

  const components = componentsQuery.data ?? EMPTY_COMPONENTS
  const prototypes = prototypesQuery.data ?? EMPTY_PROTOTYPES
  const orders = ordersQuery.data ?? EMPTY_ORDERS
  const isLoading = componentsQuery.isPending || prototypesQuery.isPending || ordersQuery.isPending
  const loadError = componentsQuery.error ?? prototypesQuery.error ?? ordersQuery.error

  const reload = useCallback(() => {
    void queryClient.invalidateQueries({ queryKey: queryKeys.inventory.all })
  }, [queryClient])

  const low = lowStockComponents(components)
  const openOrders = orders.filter((o) => o.status === 'planned' || o.status === 'ordered')

  return (
    <section className="tab-section">
      <header className="cmdbar">
        <div className="cmdbar-titles">
          <div className="eyebrow">
            <Boxes size={13} />
            hardware tracking
          </div>
          <h1>Inventory</h1>
        </div>
        <div className="chips">
          <Chip label="Parts" value={String(components.length)} tone="info" />
          <Chip label="Prototypes" value={String(prototypes.length)} tone="info" />
          <Chip label="Stock value" value={formatMoney(stockValue(components), 'INR')} tone="ok" />
          <Chip label="Out of stock" value={String(low.length)} tone={low.length ? 'crit' : 'muted'} />
          <Chip label="Open orders" value={String(openOrders.length)} tone="muted" />
          <button type="button" className="inv-icon-btn" onClick={reload} title="Refresh">
            <RefreshCw size={14} />
          </button>
        </div>
      </header>

      {isLoading && <div className="empty">Loading inventory…</div>}
      {!isLoading && loadError && (
        <div className="empty">Could not load inventory — {errMessage(loadError)}</div>
      )}
      {!isLoading && !loadError && (
        <div className="inv-layout">
          <ComponentsPanel components={components} onChanged={reload} />
          <PrototypesPanel prototypes={prototypes} components={components} onChanged={reload} />
          <OrdersPanel orders={orders} components={components} onChanged={reload} />
        </div>
      )}
    </section>
  )
}
