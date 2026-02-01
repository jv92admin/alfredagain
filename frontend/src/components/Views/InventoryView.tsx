import { useEffect, useState, useRef, Fragment } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { apiRequest } from '../../lib/api'
import { useUIChanges } from '../../context/ChatContext'
import { EntityFormModal } from '../Form/EntityForm'
import { IngredientSearchField } from '../Form/pickers'
import { getCategoryIcon, groupByCategory } from '../../lib/categoryUtils'

interface InventoryItem {
  id: string
  name: string
  quantity: number | null
  unit: string | null
  location: string | null
  expiry_date: string | null
  category: string | null
  ingredient_id: string | null
}

export function InventoryView() {
  const [items, setItems] = useState<InventoryItem[]>([])
  const [loading, setLoading] = useState(true)
  const [editingId, setEditingId] = useState<string | null>(null)
  const [editValue, setEditValue] = useState('')
  const [showAddModal, setShowAddModal] = useState(false)
  const [editingItem, setEditingItem] = useState<InventoryItem | null>(null)
  const [expandedCategories, setExpandedCategories] = useState<Set<string>>(new Set())
  const [filterText, setFilterText] = useState('')
  const inputRef = useRef<HTMLInputElement>(null)
  const { pushUIChange } = useUIChanges()

  useEffect(() => {
    fetchInventory()
  }, [])

  useEffect(() => {
    if (editingId && inputRef.current) {
      inputRef.current.focus()
      inputRef.current.select()
    }
  }, [editingId])

  const fetchInventory = async () => {
    try {
      const data = await apiRequest('/api/entities/inventory')
      setItems(data.data || [])
    } catch (err) {
      console.error('Failed to fetch inventory:', err)
    } finally {
      setLoading(false)
    }
  }

  const toggleCategory = (category: string) => {
    setExpandedCategories(prev => {
      const next = new Set(prev)
      if (next.has(category)) {
        next.delete(category)
      } else {
        next.add(category)
      }
      return next
    })
  }

  const startEditing = (item: InventoryItem) => {
    setEditingId(item.id)
    setEditValue(item.quantity?.toString() || '')
  }

  const saveQuantity = async (item: InventoryItem) => {
    const newQuantity = parseFloat(editValue) || 0

    setItems(prev => prev.map(i =>
      i.id === item.id ? { ...i, quantity: newQuantity } : i
    ))
    setEditingId(null)

    try {
      await apiRequest(`/api/entities/inventory/${item.id}`, {
        method: 'PATCH',
        body: JSON.stringify({ quantity: newQuantity }),
      })
      pushUIChange({
        action: 'updated:user',
        entity_type: 'inv',
        id: item.id,
        label: item.name,
        data: { ...item, quantity: newQuantity },
      })
    } catch (err) {
      setItems(prev => prev.map(i =>
        i.id === item.id ? { ...i, quantity: item.quantity } : i
      ))
      console.error('Failed to update quantity:', err)
    }
  }

  const deleteItem = async (item: InventoryItem) => {
    if (!confirm(`Delete ${item.name}?`)) return

    setItems(prev => prev.filter(i => i.id !== item.id))

    try {
      await apiRequest(`/api/entities/inventory/${item.id}`, {
        method: 'DELETE',
      })
      pushUIChange({
        action: 'deleted:user',
        entity_type: 'inv',
        id: item.id,
        label: item.name,
      })
    } catch (err) {
      setItems(prev => [...prev, item])
      console.error('Failed to delete item:', err)
    }
  }

  const handleKeyDown = (e: React.KeyboardEvent, item: InventoryItem) => {
    if (e.key === 'Enter') {
      saveQuantity(item)
    } else if (e.key === 'Escape') {
      setEditingId(null)
    }
  }

  const handleItemCreated = (data: any) => {
    setItems((prev) => [...prev, data])
    setShowAddModal(false)
    pushUIChange({
      action: 'created:user',
      entity_type: 'inv',
      id: data.id,
      label: data.name,
      data: data,
    })
  }

  const handleItemUpdated = (data: any) => {
    setItems((prev) => prev.map((i) => (i.id === data.id ? data : i)))
    setEditingItem(null)
    pushUIChange({
      action: 'updated:user',
      entity_type: 'inv',
      id: data.id,
      label: data.name,
      data: data,
    })
  }

  // Modal components
  const addItemModal = (
    <EntityFormModal
      title="Add Inventory Item"
      isOpen={showAddModal}
      onClose={() => setShowAddModal(false)}
      subdomain="inventory"
      table="inventory"
      mode="create"
      onSuccess={handleItemCreated}
      fieldOrder={['name', 'quantity', 'unit', 'location', 'expiry_date']}
      excludeFields={['id', 'user_id', 'created_at', 'updated_at', 'ingredient_id', 'purchase_date', 'category']}
      customRenderers={{ name: IngredientSearchField }}
    />
  )

  const editItemModal = editingItem && (
    <EntityFormModal
      title="Edit Inventory Item"
      isOpen={!!editingItem}
      onClose={() => setEditingItem(null)}
      subdomain="inventory"
      table="inventory"
      mode="edit"
      entityId={editingItem.id}
      initialData={editingItem}
      onSuccess={handleItemUpdated}
      fieldOrder={['name', 'quantity', 'unit', 'location', 'expiry_date']}
      excludeFields={['id', 'user_id', 'created_at', 'updated_at', 'ingredient_id', 'purchase_date', 'category']}
      customRenderers={{ name: IngredientSearchField }}
    />
  )

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="text-[var(--color-text-muted)]">Loading inventory...</div>
      </div>
    )
  }

  if (items.length === 0) {
    return (
      <>
        <div className="flex flex-col items-center justify-center h-full text-center p-8">
          <span className="text-4xl mb-4">📦</span>
          <h2 className="text-xl text-[var(--color-text-primary)] mb-2">Pantry is empty</h2>
          <p className="text-[var(--color-text-muted)] mb-4">
            Tell Alfred what's in your kitchen!
          </p>
          <motion.button
            whileHover={{ scale: 1.02 }}
            whileTap={{ scale: 0.98 }}
            onClick={() => setShowAddModal(true)}
            className="px-4 py-2 bg-[var(--color-accent)] hover:bg-[var(--color-accent-hover)] text-[var(--color-text-inverse)] font-medium rounded-[var(--radius-md)]"
          >
            + Add Item
          </motion.button>
        </div>
        {addItemModal}
      </>
    )
  }

  const filter = filterText.toLowerCase().trim()
  const filteredItems = filter ? items.filter(i => i.name.toLowerCase().includes(filter)) : items
  const grouped = groupByCategory(filteredItems)
  const allCategories = grouped.map(([cat]) => cat)
  const allExpanded = allCategories.length > 0 && allCategories.every(cat => expandedCategories.has(cat))

  const toggleAll = () => {
    if (allExpanded) {
      setExpandedCategories(new Set())
    } else {
      setExpandedCategories(new Set(allCategories))
    }
  }

  return (
    <>
      <div className="h-full flex flex-col">
        {/* Sticky header */}
        <div className="sticky top-0 z-10 bg-[var(--color-bg-primary)] border-b border-[var(--color-border)] p-4">
          <div className="flex items-center justify-between mb-3">
            <h1 className="text-2xl font-semibold text-[var(--color-text-primary)]">
              Inventory
            </h1>
            <motion.button
              whileHover={{ scale: 1.02 }}
              whileTap={{ scale: 0.98 }}
              onClick={() => setShowAddModal(true)}
              className="px-4 py-2 bg-[var(--color-accent)] hover:bg-[var(--color-accent-hover)] text-[var(--color-text-inverse)] font-medium rounded-[var(--radius-md)] text-sm"
            >
              + Add Item
            </motion.button>
          </div>

          {/* Filter search bar */}
          <div className="relative">
            <input
              type="text"
              value={filterText}
              onChange={(e) => setFilterText(e.target.value)}
              placeholder="Filter items..."
              className="w-full px-4 py-2 pl-10 bg-[var(--color-bg-tertiary)] border border-[var(--color-border)] rounded-[var(--radius-md)] text-[var(--color-text-primary)] placeholder:text-[var(--color-text-muted)] focus:outline-none focus:border-[var(--color-accent)]"
            />
            <span className="absolute left-3 top-1/2 -translate-y-1/2 text-[var(--color-text-muted)] text-sm">
              🔍
            </span>
            {filterText && (
              <button
                onClick={() => setFilterText('')}
                className="absolute right-3 top-1/2 -translate-y-1/2 text-[var(--color-text-muted)] hover:text-[var(--color-text-primary)]"
              >
                ✕
              </button>
            )}
          </div>
          <div className="flex justify-end mt-2">
            <button
              onClick={toggleAll}
              className="text-xs text-[var(--color-text-muted)] hover:text-[var(--color-text-primary)] transition-colors"
            >
              {allExpanded ? 'Collapse All' : 'Expand All'}
            </button>
          </div>
        </div>

        {/* Scrollable content */}
        <div className="flex-1 overflow-y-auto p-6">
          {/* Mobile: Card layout grouped by collapsible category */}
          <div className="md:hidden space-y-2">
            {grouped.map(([category, categoryItems]) => {
              const isExpanded = !!filter || expandedCategories.has(category)
              return (
                <div key={category} className="border border-[var(--color-border)] rounded-[var(--radius-md)] overflow-hidden">
                  <button
                    onClick={() => toggleCategory(category)}
                    className="w-full flex items-center justify-between px-4 py-3 bg-[var(--color-bg-secondary)] hover:bg-[var(--color-bg-tertiary)] transition-colors"
                  >
                    <div className="flex items-center gap-2">
                      <span className="text-base">{getCategoryIcon(category)}</span>
                      <span className="text-sm font-medium text-[var(--color-text-primary)] capitalize">
                        {category}
                      </span>
                      <span className="text-xs text-[var(--color-text-muted)]">
                        ({categoryItems.length})
                      </span>
                    </div>
                    <span className={`text-[var(--color-text-muted)] transition-transform ${isExpanded ? 'rotate-180' : ''}`}>
                      ▼
                    </span>
                  </button>

                  <AnimatePresence>
                    {isExpanded && (
                      <motion.div
                        initial={{ height: 0, opacity: 0 }}
                        animate={{ height: 'auto', opacity: 1 }}
                        exit={{ height: 0, opacity: 0 }}
                        transition={{ duration: 0.2 }}
                        className="overflow-hidden"
                      >
                        <div className="divide-y divide-[var(--color-border)]">
                          {categoryItems.map((item) => (
                            <div
                              key={item.id}
                              className="group flex items-center gap-2 p-4"
                            >
                              <div className="flex-1 min-w-0">
                                <div className="font-medium text-[var(--color-text-primary)] truncate">
                                  {item.name}
                                </div>
                                <div className="flex flex-wrap items-center gap-2 mt-1 text-sm text-[var(--color-text-muted)]">
                                  {editingId === item.id ? (
                                    <input
                                      autoFocus
                                      type="number"
                                      value={editValue}
                                      onChange={(e) => setEditValue(e.target.value)}
                                      onBlur={() => saveQuantity(item)}
                                      onKeyDown={(e) => handleKeyDown(e, item)}
                                      className="w-20 px-2 py-1 bg-[var(--color-bg-primary)] border border-[var(--color-accent)] rounded text-[var(--color-text-primary)] text-sm focus:outline-none"
                                    />
                                  ) : (
                                    <button
                                      onClick={() => startEditing(item)}
                                      className="text-[var(--color-accent)] hover:underline"
                                    >
                                      {item.quantity} {item.unit || ''}
                                    </button>
                                  )}
                                  {item.location && <span>· {item.location}</span>}
                                  {item.expiry_date && <span>· Exp: {item.expiry_date}</span>}
                                </div>
                              </div>
                              <button
                                onClick={() => setEditingItem(item)}
                                className="text-xs font-medium text-[var(--color-text-muted)] hover:text-[var(--color-accent)] transition-opacity px-2"
                              >
                                Edit
                              </button>
                              <button
                                onClick={() => deleteItem(item)}
                                className="text-xs font-medium text-[var(--color-text-muted)] hover:text-[var(--color-error)] transition-opacity px-2"
                              >
                                Delete
                              </button>
                            </div>
                          ))}
                        </div>
                      </motion.div>
                    )}
                  </AnimatePresence>
                </div>
              )
            })}
          </div>

          {/* Desktop: Table layout grouped by collapsible category */}
          <div className="hidden md:block bg-[var(--color-bg-secondary)] border border-[var(--color-border)] rounded-[var(--radius-lg)] overflow-hidden">
            <table className="w-full">
              <thead>
                <tr className="border-b border-[var(--color-border)]">
                  <th className="text-left px-4 py-3 text-sm font-medium text-[var(--color-text-muted)]">
                    Item
                  </th>
                  <th className="text-left px-4 py-3 text-sm font-medium text-[var(--color-text-muted)]">
                    Quantity
                  </th>
                  <th className="text-left px-4 py-3 text-sm font-medium text-[var(--color-text-muted)]">
                    Location
                  </th>
                  <th className="text-left px-4 py-3 text-sm font-medium text-[var(--color-text-muted)]">
                    Expiry
                  </th>
                  <th className="w-12"></th>
                </tr>
              </thead>
              <tbody>
                {grouped.map(([category, categoryItems]) => {
                  const isExpanded = !!filter || expandedCategories.has(category)
                  return (
                    <Fragment key={category}>
                      {/* Collapsible category header row */}
                      <tr
                        className="bg-[var(--color-bg-tertiary)] cursor-pointer hover:bg-[var(--color-bg-elevated)] transition-colors"
                        onClick={() => toggleCategory(category)}
                      >
                        <td colSpan={5} className="px-4 py-2">
                          <div className="flex items-center justify-between">
                            <div className="flex items-center gap-2">
                              <span className="text-base">{getCategoryIcon(category)}</span>
                              <span className="text-sm font-medium text-[var(--color-text-secondary)] capitalize">
                                {category}
                              </span>
                              <span className="text-xs text-[var(--color-text-muted)]">
                                ({categoryItems.length})
                              </span>
                            </div>
                            <span className={`text-[var(--color-text-muted)] transition-transform text-xs ${isExpanded ? 'rotate-180' : ''}`}>
                              ▼
                            </span>
                          </div>
                        </td>
                      </tr>
                      {/* Items — only shown when expanded */}
                      {isExpanded && categoryItems.map((item) => (
                        <tr
                          key={item.id}
                          className="border-b border-[var(--color-border)] last:border-b-0 hover:bg-[var(--color-bg-tertiary)] group"
                        >
                          <td className="px-4 py-3 text-[var(--color-text-primary)]">
                            {item.name}
                          </td>
                          <td className="px-4 py-3">
                            {editingId === item.id ? (
                              <input
                                ref={inputRef}
                                type="number"
                                value={editValue}
                                onChange={(e) => setEditValue(e.target.value)}
                                onBlur={() => saveQuantity(item)}
                                onKeyDown={(e) => handleKeyDown(e, item)}
                                className="w-20 px-2 py-1 bg-[var(--color-bg-primary)] border border-[var(--color-accent)] rounded text-[var(--color-text-primary)] text-sm focus:outline-none"
                              />
                            ) : (
                              <button
                                onClick={() => startEditing(item)}
                                className="text-[var(--color-text-secondary)] hover:text-[var(--color-accent)] hover:underline cursor-pointer"
                              >
                                {item.quantity} {item.unit || ''}
                              </button>
                            )}
                          </td>
                          <td className="px-4 py-3 text-[var(--color-text-secondary)]">
                            {item.location || '-'}
                          </td>
                          <td className="px-4 py-3 text-[var(--color-text-secondary)]">
                            {item.expiry_date || '-'}
                          </td>
                          <td className="px-4 py-3 flex gap-2">
                            <button
                              onClick={() => setEditingItem(item)}
                              className="md:opacity-0 md:group-hover:opacity-100 text-xs font-medium text-[var(--color-text-muted)] hover:text-[var(--color-accent)] transition-opacity"
                            >
                              Edit
                            </button>
                            <button
                              onClick={() => deleteItem(item)}
                              className="md:opacity-0 md:group-hover:opacity-100 text-xs font-medium text-[var(--color-text-muted)] hover:text-[var(--color-error)] transition-opacity"
                            >
                              Delete
                            </button>
                          </td>
                        </tr>
                      ))}
                    </Fragment>
                  )
                })}
              </tbody>
            </table>
          </div>

          <p className="mt-4 text-sm text-[var(--color-text-muted)]">
            Click quantity to quick-edit.
          </p>
        </div>
      </div>
      {addItemModal}
      {editItemModal}
    </>
  )
}
