import { useEffect, useState, useRef } from 'react'
import { apiRequest } from '../../lib/api'

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
  const inputRef = useRef<HTMLInputElement>(null)

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
      const data = await apiRequest('/api/tables/inventory')
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
      await apiRequest(`/api/tables/inventory/${item.id}`, {
        method: 'PATCH',
        body: JSON.stringify({ quantity: newQuantity }),
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
      await apiRequest(`/api/tables/inventory/${item.id}`, {
        method: 'DELETE',
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

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="text-[var(--color-text-muted)]">Loading inventory...</div>
      </div>
    )
  }

  if (items.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center h-full text-center p-8">
        <span className="text-4xl mb-4">📦</span>
        <h2 className="text-xl text-[var(--color-text-primary)] mb-2">Pantry is empty</h2>
        <p className="text-[var(--color-text-muted)]">
          Tell Alfred what's in your kitchen!
        </p>
      </div>
    )
  }

  return (
    <div className="h-full overflow-y-auto p-6">
      <h1 className="text-2xl font-semibold text-[var(--color-text-primary)] mb-6">
        Inventory
      </h1>

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
                <td className="px-4 py-3">
                  <button
                    onClick={() => deleteItem(item)}
                    className="opacity-0 group-hover:opacity-100 text-[var(--color-text-muted)] hover:text-[var(--color-error)] transition-opacity"
                    title="Delete"
                  >
                    🗑️
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <p className="mt-4 text-sm text-[var(--color-text-muted)]">
        💡 Click a quantity to edit. Hover to see delete button.
      </p>
    </div>
  )
}
