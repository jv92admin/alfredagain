import { useEffect, useState, useRef } from 'react'
import { motion } from 'framer-motion'
import { apiRequest } from '../../lib/api'
import { useUIChanges } from '../../context/ChatContext'
import { EntityFormModal } from '../Form/EntityForm'

interface InventoryItem {
  id: string
  name: string
  quantity: number | null
  unit: string | null
  location: string | null
  expiry_date: string | null
}

export function InventoryView() {
  const [items, setItems] = useState<InventoryItem[]>([])
  const [loading, setLoading] = useState(true)
  const [editingId, setEditingId] = useState<string | null>(null)
  const [editValue, setEditValue] = useState('')
  const [showAddModal, setShowAddModal] = useState(false)
  const [editingItem, setEditingItem] = useState<InventoryItem | null>(null)
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

  const startEditing = (item: InventoryItem) => {
    setEditingId(item.id)
    setEditValue(item.quantity?.toString() || '')
  }

  const saveQuantity = async (item: InventoryItem) => {
    const newQuantity = parseFloat(editValue) || 0

    // Optimistic update
    setItems(prev => prev.map(i =>
      i.id === item.id ? { ...i, quantity: newQuantity } : i
    ))
    setEditingId(null)

    try {
      await apiRequest(`/api/entities/inventory/${item.id}`, {
        method: 'PATCH',
        body: JSON.stringify({ quantity: newQuantity }),
      })
      // Track UI change for AI context
      pushUIChange({
        action: 'updated:user',
        entity_type: 'inv',
        id: item.id,
        label: item.name,
        data: { ...item, quantity: newQuantity },
      })
    } catch (err) {
      // Revert on error
      setItems(prev => prev.map(i =>
        i.id === item.id ? { ...i, quantity: item.quantity } : i
      ))
      console.error('Failed to update quantity:', err)
    }
  }

  const deleteItem = async (item: InventoryItem) => {
    if (!confirm(`Delete ${item.name}?`)) return

    // Optimistic update
    setItems(prev => prev.filter(i => i.id !== item.id))

    try {
      await apiRequest(`/api/entities/inventory/${item.id}`, {
        method: 'DELETE',
      })
      // Track UI change for AI context
      pushUIChange({
        action: 'deleted:user',
        entity_type: 'inv',
        id: item.id,
        label: item.name,
      })
    } catch (err) {
      // Revert on error
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
    // Track UI change for AI context
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
    // Track UI change for AI context
    pushUIChange({
      action: 'updated:user',
      entity_type: 'inv',
      id: data.id,
      label: data.name,
      data: data,
    })
  }

  // Modal components - rendered once at the end
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
      excludeFields={['id', 'user_id', 'created_at', 'updated_at', 'ingredient_id', 'purchase_date']}
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
      excludeFields={['id', 'user_id', 'created_at', 'updated_at', 'ingredient_id', 'purchase_date']}
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

  return (
    <>
      <div className="h-full overflow-y-auto p-6">
        <div className="flex items-center justify-between mb-6">
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

        <div className="bg-[var(--color-bg-secondary)] border border-[var(--color-border)] rounded-[var(--radius-lg)] overflow-hidden">
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
              {items.map((item) => (
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
            </tbody>
          </table>
        </div>

        <p className="mt-4 text-sm text-[var(--color-text-muted)] hidden md:block">
          Click quantity to quick-edit.
        </p>
      </div>
      {addItemModal}
      {editItemModal}
    </>
  )
}
