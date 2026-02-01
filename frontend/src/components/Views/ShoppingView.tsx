import { useEffect, useState, useRef } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { apiRequest } from '../../lib/api'
import { useUIChanges } from '../../context/ChatContext'
import { EntityFormModal } from '../Form/EntityForm'
import { IngredientSearchField } from '../Form/pickers'
import { getCategoryIcon, groupByCategory } from '../../lib/categoryUtils'

interface ShoppingItem {
  id: string
  name: string
  quantity: number | null
  unit: string | null
  category: string | null
  is_purchased: boolean
  ingredient_id: string | null
}

export function ShoppingView() {
  const [items, setItems] = useState<ShoppingItem[]>([])
  const [loading, setLoading] = useState(true)
  const [showAddModal, setShowAddModal] = useState(false)
  const [editingItem, setEditingItem] = useState<ShoppingItem | null>(null)
  const [expandedCategories, setExpandedCategories] = useState<Set<string>>(new Set())
  const [filterText, setFilterText] = useState('')
  const pendingRef = useRef<HTMLDivElement>(null)
  const purchasedRef = useRef<HTMLDivElement>(null)
  const scrollContainerRef = useRef<HTMLDivElement>(null)
  const { pushUIChange } = useUIChanges()

  useEffect(() => {
    fetchShopping()
  }, [])

  const fetchShopping = async () => {
    try {
      const data = await apiRequest('/api/entities/shopping_list')
      setItems(data.data || [])
    } catch (err) {
      console.error('Failed to fetch shopping list:', err)
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
      await apiRequest(`/api/entities/shopping_list/${item.id}`, {
        method: 'PATCH',
        body: JSON.stringify({ is_purchased: newValue }),
      })
      pushUIChange({
        action: 'updated:user',
        entity_type: 'shop',
        id: item.id,
        label: item.name,
        data: { ...item, is_purchased: newValue },
      })
    } catch (err) {
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

    setItems(prev => prev.filter(i => i.id !== item.id))

    try {
      await apiRequest(`/api/entities/shopping_list/${item.id}`, {
        method: 'DELETE',
      })
      pushUIChange({
        action: 'deleted:user',
        entity_type: 'shop',
        id: item.id,
        label: item.name,
      })
    } catch (err) {
      setItems(prev => [...prev, item])
      console.error('Failed to delete item:', err)
    }
  }

  const handleItemCreated = (data: any) => {
    setItems((prev) => [...prev, data])
    setShowAddModal(false)
    pushUIChange({
      action: 'created:user',
      entity_type: 'shop',
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
      entity_type: 'shop',
      id: data.id,
      label: data.name,
      data: data,
    })
  }

  const clearPurchased = async () => {
    const purchasedItems = items.filter(i => i.is_purchased)
    if (purchasedItems.length === 0) return
    if (!confirm(`Clear ${purchasedItems.length} purchased item(s)?`)) return

    setItems(prev => prev.filter(i => !i.is_purchased))

    try {
      await Promise.all(
        purchasedItems.map(item =>
          apiRequest(`/api/entities/shopping_list/${item.id}`, {
            method: 'DELETE',
          })
        )
      )
    } catch (err) {
      setItems(prev => [...prev, ...purchasedItems])
      console.error('Failed to clear purchased:', err)
    }
  }

  const scrollToSection = (ref: React.RefObject<HTMLDivElement | null>) => {
    const container = scrollContainerRef.current
    const target = ref.current
    if (container && target) {
      container.scrollTo({ top: target.offsetTop - container.offsetTop, behavior: 'smooth' })
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="text-[var(--color-text-muted)]">Loading shopping list...</div>
      </div>
    )
  }

  // Modal components
  const addItemModal = (
    <EntityFormModal
      title="Add Shopping Item"
      isOpen={showAddModal}
      onClose={() => setShowAddModal(false)}
      subdomain="shopping"
      table="shopping_list"
      mode="create"
      onSuccess={handleItemCreated}
      fieldOrder={['name', 'quantity', 'unit']}
      excludeFields={['id', 'user_id', 'created_at', 'updated_at', 'ingredient_id', 'is_purchased', 'source', 'category']}
      customRenderers={{ name: IngredientSearchField }}
    />
  )

  const editItemModal = editingItem && (
    <EntityFormModal
      title="Edit Shopping Item"
      isOpen={!!editingItem}
      onClose={() => setEditingItem(null)}
      subdomain="shopping"
      table="shopping_list"
      mode="edit"
      entityId={editingItem.id}
      initialData={editingItem}
      onSuccess={handleItemUpdated}
      fieldOrder={['name', 'quantity', 'unit']}
      excludeFields={['id', 'user_id', 'created_at', 'updated_at', 'ingredient_id', 'is_purchased', 'source', 'category']}
      customRenderers={{ name: IngredientSearchField }}
    />
  )

  if (items.length === 0) {
    return (
      <>
        <div className="flex flex-col items-center justify-center h-full text-center p-8">
          <span className="text-4xl mb-4">🛒</span>
          <h2 className="text-xl text-[var(--color-text-primary)] mb-2">Shopping list is empty</h2>
          <p className="text-[var(--color-text-muted)] mb-4">
            Ask Alfred to add items or create a list from a recipe!
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
  const pendingItems = items.filter((i) => !i.is_purchased && (!filter || i.name.toLowerCase().includes(filter)))
  const purchasedItems = items.filter((i) => i.is_purchased)
  const groupedPending = groupByCategory(pendingItems)
  const allCategories = groupedPending.map(([cat]) => cat)
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
              Shopping List
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
          <div className="relative mb-3">
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

          <div className="flex items-center gap-2">
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
            <button
              onClick={toggleAll}
              className="ml-auto text-xs text-[var(--color-text-muted)] hover:text-[var(--color-text-primary)] transition-colors"
            >
              {allExpanded ? 'Collapse All' : 'Expand All'}
            </button>
          </div>
        </div>

        {/* Scrollable content */}
        <div ref={scrollContainerRef} className="flex-1 overflow-y-auto p-6 space-y-8">
          {/* Pending items — grouped by collapsible category */}
          <div ref={pendingRef} className="space-y-2">
            <h2 className="text-sm font-medium text-[var(--color-text-muted)] mb-2">
              To Buy
            </h2>
            {pendingItems.length === 0 ? (
              <p className="text-[var(--color-text-muted)] text-sm italic">All done!</p>
            ) : (
              groupedPending.map(([category, categoryItems]) => {
                const isExpanded = !!filter || expandedCategories.has(category)
                return (
                  <div key={category} className="border border-[var(--color-border)] rounded-[var(--radius-md)] overflow-hidden">
                    {/* Collapsible category header */}
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

                    {/* Items */}
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
                                className="group flex items-center gap-2 p-4 hover:bg-[var(--color-bg-tertiary)] transition-colors"
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
                                  onClick={(e) => {
                                    e.stopPropagation()
                                    setEditingItem(item)
                                  }}
                                  className="md:opacity-0 md:group-hover:opacity-100 text-xs font-medium text-[var(--color-text-muted)] hover:text-[var(--color-accent)] transition-opacity px-2"
                                >
                                  Edit
                                </button>
                                <button
                                  onClick={(e) => deleteItem(e, item)}
                                  className="md:opacity-0 md:group-hover:opacity-100 text-xs font-medium text-[var(--color-text-muted)] hover:text-[var(--color-error)] transition-opacity px-2"
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
              })
            )}
          </div>

          {/* Purchased items — flat list */}
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
                    <span className="w-5 h-5 rounded border-2 border-[var(--color-success)] bg-[var(--color-success)] flex items-center justify-center text-white text-xs animate-checkbox">
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
      {addItemModal}
      {editItemModal}
    </>
  )
}
