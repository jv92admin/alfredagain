import { useEffect, useState, useRef } from 'react'
import { apiRequest } from '../../lib/api'

interface ShoppingItem {
  id: string
  name: string
  quantity: number | null
  unit: string | null
  category: string | null
  is_purchased: boolean
}

export function ShoppingView() {
  const [items, setItems] = useState<ShoppingItem[]>([])
  const [loading, setLoading] = useState(true)
  const pendingRef = useRef<HTMLDivElement>(null)
  const purchasedRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    fetchShopping()
  }, [])

  const fetchShopping = async () => {
    try {
      const data = await apiRequest('/api/tables/shopping')
      setItems(data.data || [])
    } catch (err) {
      console.error('Failed to fetch shopping list:', err)
    } finally {
      setLoading(false)
    }
  }

  const togglePurchased = async (item: ShoppingItem) => {
    const newValue = !item.is_purchased
    
    // Optimistic update
    setItems((prev) =>
      prev.map((i) =>
        i.id === item.id ? { ...i, is_purchased: newValue } : i
      )
    )

    // Persist to backend
    try {
      await apiRequest(`/api/tables/shopping_list/${item.id}`, {
        method: 'PATCH',
        body: JSON.stringify({ is_purchased: newValue }),
      })
    } catch (err) {
      // Revert on error
      setItems((prev) =>
        prev.map((i) =>
          i.id === item.id ? { ...i, is_purchased: !newValue } : i
        )
      )
      console.error('Failed to update item:', err)
    }
  }

  const deleteItem = async (e: React.MouseEvent, item: ShoppingItem) => {
    e.stopPropagation()
    e.preventDefault()
    
    if (!confirm(`Delete "${item.name}"?`)) return
    
    // Optimistic update
    setItems(prev => prev.filter(i => i.id !== item.id))

    try {
      await apiRequest(`/api/tables/shopping_list/${item.id}`, {
        method: 'DELETE',
      })
    } catch (err) {
      // Revert on error
      setItems(prev => [...prev, item])
      console.error('Failed to delete item:', err)
    }
  }

  const clearPurchased = async () => {
    const purchasedItems = items.filter(i => i.is_purchased)
    if (purchasedItems.length === 0) return
    if (!confirm(`Clear ${purchasedItems.length} purchased item(s)?`)) return
    
    // Optimistic update
    setItems(prev => prev.filter(i => !i.is_purchased))

    try {
      await Promise.all(
        purchasedItems.map(item =>
          apiRequest(`/api/tables/shopping_list/${item.id}`, {
            method: 'DELETE',
          })
        )
      )
    } catch (err) {
      // Revert on error
      setItems(prev => [...prev, ...purchasedItems])
      console.error('Failed to clear purchased:', err)
    }
  }

  const scrollToSection = (ref: React.RefObject<HTMLDivElement | null>) => {
    ref.current?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="text-[var(--color-text-muted)]">Loading shopping list...</div>
      </div>
    )
  }

  if (items.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center h-full text-center p-8">
        <span className="text-4xl mb-4">🛒</span>
        <h2 className="text-xl text-[var(--color-text-primary)] mb-2">Shopping list is empty</h2>
        <p className="text-[var(--color-text-muted)]">
          Ask Alfred to add items or create a list from a recipe!
        </p>
      </div>
    )
  }

  const pendingItems = items.filter((i) => !i.is_purchased)
  const purchasedItems = items.filter((i) => i.is_purchased)

  return (
    <div className="h-full flex flex-col">
      {/* Sticky header with tabs */}
      <div className="sticky top-0 z-10 bg-[var(--color-bg-primary)] border-b border-[var(--color-border)] p-4">
        <h1 className="text-2xl font-semibold text-[var(--color-text-primary)] mb-4">
          Shopping List
        </h1>
        <div className="flex gap-2">
          <button
            onClick={() => scrollToSection(pendingRef)}
            className="px-4 py-2 rounded-full text-sm font-medium bg-[var(--color-accent)] text-white"
          >
            Pending ({pendingItems.length})
          </button>
          <button
            onClick={() => scrollToSection(purchasedRef)}
            className="px-4 py-2 rounded-full text-sm font-medium bg-[var(--color-bg-tertiary)] text-[var(--color-text-secondary)] hover:bg-[var(--color-bg-secondary)] transition-colors"
          >
            Purchased ({purchasedItems.length})
          </button>
        </div>
      </div>

      {/* Scrollable content */}
      <div className="flex-1 overflow-y-auto p-6 space-y-8">
        {/* Pending items */}
        <div ref={pendingRef} className="space-y-2">
          <h2 className="text-sm font-medium text-[var(--color-text-muted)] mb-3">
            To Buy
          </h2>
          {pendingItems.length === 0 ? (
            <p className="text-[var(--color-text-muted)] text-sm italic">All done! 🎉</p>
          ) : (
            pendingItems.map((item) => (
              <div
                key={item.id}
                className="group flex items-center gap-2 bg-[var(--color-bg-secondary)] border border-[var(--color-border)] rounded-[var(--radius-md)] p-4 hover:border-[var(--color-accent)] transition-colors"
              >
                <button
                  onClick={() => togglePurchased(item)}
                  className="flex-1 flex items-center gap-3 text-left"
                >
                  <span className="w-5 h-5 rounded border-2 border-[var(--color-border)] flex items-center justify-center flex-shrink-0" />
                  <span className="flex-1 text-[var(--color-text-primary)]">
                    {item.name}
                  </span>
                  {item.quantity && (
                    <span className="text-sm text-[var(--color-text-muted)]">
                      {item.quantity} {item.unit || ''}
                    </span>
                  )}
                </button>
                <button
                  onClick={(e) => deleteItem(e, item)}
                  className="opacity-0 group-hover:opacity-100 text-[var(--color-text-muted)] hover:text-[var(--color-error)] transition-opacity px-2"
                  title="Delete"
                >
                  🗑️
                </button>
              </div>
            ))
          )}
        </div>

        {/* Purchased items */}
        <div ref={purchasedRef} className="space-y-2">
          <div className="flex items-center justify-between mb-3">
            <h2 className="text-sm font-medium text-[var(--color-text-muted)]">
              Purchased
            </h2>
            {purchasedItems.length > 0 && (
              <button
                onClick={clearPurchased}
                className="text-xs px-3 py-1 rounded-full bg-[var(--color-error)]/10 text-[var(--color-error)] hover:bg-[var(--color-error)]/20 transition-colors"
              >
                Clear All
              </button>
            )}
          </div>
          {purchasedItems.length === 0 ? (
            <p className="text-[var(--color-text-muted)] text-sm italic">No purchased items</p>
          ) : (
            <div className="space-y-2">
              {purchasedItems.map((item) => (
                <button
                  key={item.id}
                  onClick={() => togglePurchased(item)}
                  className="w-full text-left flex items-center gap-3 bg-[var(--color-bg-secondary)] border border-[var(--color-border)] rounded-[var(--radius-md)] p-4 opacity-60 hover:opacity-80 transition-opacity"
                >
                  <span className="w-5 h-5 rounded border-2 border-[var(--color-success)] bg-[var(--color-success)] flex items-center justify-center text-white text-xs">
                    ✓
                  </span>
                  <span className="flex-1 text-[var(--color-text-primary)] line-through">
                    {item.name}
                  </span>
                  <span className="text-xs text-[var(--color-text-muted)]">
                    tap to uncheck
                  </span>
                </button>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

