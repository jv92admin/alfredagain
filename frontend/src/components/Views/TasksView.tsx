import { useEffect, useState } from 'react'
import { motion } from 'framer-motion'
import { apiRequest } from '../../lib/api'
import { useUIChanges } from '../../context/ChatContext'
import { EntityFormModal } from '../Form/EntityForm'
import { RecipePicker, MealPlanPicker } from '../Form/pickers'

interface Task {
  id: string
  title: string
  due_date: string | null
  category: string | null
  completed: boolean
  recipe_id: string | null
  meal_plan_id: string | null
}

export function TasksView() {
  const [tasks, setTasks] = useState<Task[]>([])
  const [loading, setLoading] = useState(true)
  const [showAddModal, setShowAddModal] = useState(false)
  const [editingTask, setEditingTask] = useState<Task | null>(null)
  const { pushUIChange } = useUIChanges()

  useEffect(() => {
    fetchTasks()
  }, [])

  const fetchTasks = async () => {
    try {
      const data = await apiRequest('/api/entities/tasks')
      setTasks(data.data || [])
    } catch (err) {
      console.error('Failed to fetch tasks:', err)
    } finally {
      setLoading(false)
    }
  }

  const toggleCompleted = async (task: Task) => {
    const newValue = !task.completed

    // Optimistic update
    setTasks((prev) =>
      prev.map((t) =>
        t.id === task.id ? { ...t, completed: newValue } : t
      )
    )

    // Persist to backend
    try {
      await apiRequest(`/api/entities/tasks/${task.id}`, {
        method: 'PATCH',
        body: JSON.stringify({ completed: newValue }),
      })
      // Track UI change for AI context
      pushUIChange({
        action: 'updated:user',
        entity_type: 'task',
        id: task.id,
        label: task.title,
      })
    } catch (err) {
      // Revert on error
      setTasks((prev) =>
        prev.map((t) =>
          t.id === task.id ? { ...t, completed: !newValue } : t
        )
      )
      console.error('Failed to update task:', err)
    }
  }

  const deleteTask = async (e: React.MouseEvent, task: Task) => {
    e.stopPropagation()

    // Optimistic update
    setTasks(prev => prev.filter(t => t.id !== task.id))

    try {
      await apiRequest(`/api/entities/tasks/${task.id}`, {
        method: 'DELETE',
      })
      // Track UI change for AI context
      pushUIChange({
        action: 'deleted:user',
        entity_type: 'task',
        id: task.id,
        label: task.title,
      })
    } catch (err) {
      // Revert on error
      setTasks(prev => [...prev, task])
      console.error('Failed to delete task:', err)
    }
  }

  const handleTaskCreated = (data: any) => {
    setTasks((prev) => [...prev, data])
    setShowAddModal(false)
    // Track UI change for AI context
    pushUIChange({
      action: 'created:user',
      entity_type: 'task',
      id: data.id,
      label: data.title,
    })
  }

  const handleTaskUpdated = (data: any) => {
    setTasks((prev) => prev.map((t) => (t.id === data.id ? data : t)))
    setEditingTask(null)
    // Track UI change for AI context
    pushUIChange({
      action: 'updated:user',
      entity_type: 'task',
      id: data.id,
      label: data.title,
    })
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="text-[var(--color-text-muted)]">Loading tasks...</div>
      </div>
    )
  }

  // Modal components - rendered once at the end
  const addTaskModal = (
    <EntityFormModal
      title="Add Task"
      isOpen={showAddModal}
      onClose={() => setShowAddModal(false)}
      subdomain="tasks"
      table="tasks"
      mode="create"
      onSuccess={handleTaskCreated}
      fieldOrder={['title', 'due_date', 'category', 'recipe_id', 'meal_plan_id']}
      excludeFields={['id', 'user_id', 'created_at', 'updated_at', 'completed']}
      customRenderers={{
        recipe_id: RecipePicker,
        meal_plan_id: MealPlanPicker,
      }}
    />
  )

  const editTaskModal = editingTask && (
    <EntityFormModal
      title="Edit Task"
      isOpen={!!editingTask}
      onClose={() => setEditingTask(null)}
      subdomain="tasks"
      table="tasks"
      mode="edit"
      entityId={editingTask.id}
      initialData={editingTask}
      onSuccess={handleTaskUpdated}
      fieldOrder={['title', 'due_date', 'category', 'recipe_id', 'meal_plan_id']}
      excludeFields={['id', 'user_id', 'created_at', 'updated_at', 'completed']}
      customRenderers={{
        recipe_id: RecipePicker,
        meal_plan_id: MealPlanPicker,
      }}
    />
  )

  if (tasks.length === 0) {
    return (
      <>
        <div className="flex flex-col items-center justify-center h-full text-center p-8">
          <span className="text-4xl mb-4">✅</span>
          <h2 className="text-xl text-[var(--color-text-primary)] mb-2">No tasks</h2>
          <p className="text-[var(--color-text-muted)] mb-4">
            Ask Alfred to create reminders for you!
          </p>
          <motion.button
            whileHover={{ scale: 1.02 }}
            whileTap={{ scale: 0.98 }}
            onClick={() => setShowAddModal(true)}
            className="px-4 py-2 bg-[var(--color-accent)] hover:bg-[var(--color-accent-hover)] text-[var(--color-text-inverse)] font-medium rounded-[var(--radius-md)]"
          >
            + Add Task
          </motion.button>
        </div>
        {addTaskModal}
      </>
    )
  }

  const pendingTasks = tasks.filter((t) => !t.completed)
  const completedTasks = tasks.filter((t) => t.completed)

  return (
    <>
      <div className="h-full overflow-y-auto p-6">
        <div className="flex items-center justify-between mb-6">
          <h1 className="text-2xl font-semibold text-[var(--color-text-primary)]">
            Tasks
          </h1>
          <motion.button
            whileHover={{ scale: 1.02 }}
            whileTap={{ scale: 0.98 }}
            onClick={() => setShowAddModal(true)}
            className="px-4 py-2 bg-[var(--color-accent)] hover:bg-[var(--color-accent-hover)] text-[var(--color-text-inverse)] font-medium rounded-[var(--radius-md)] text-sm"
          >
            + Add Task
          </motion.button>
        </div>

      <div className="space-y-6">
        {/* Pending tasks */}
        {pendingTasks.length > 0 && (
          <div className="space-y-2">
            {pendingTasks.map((task) => (
              <div
                key={task.id}
                className="group flex items-center gap-2 bg-[var(--color-bg-secondary)] border border-[var(--color-border)] rounded-[var(--radius-md)] p-4 hover:border-[var(--color-accent)] transition-colors"
              >
                <button
                  onClick={() => toggleCompleted(task)}
                  className="flex-1 flex items-center gap-3 text-left"
                >
                  <span className="w-5 h-5 rounded border-2 border-[var(--color-border)] flex items-center justify-center flex-shrink-0" />
                  <div className="flex-1">
                    <div className="text-[var(--color-text-primary)]">{task.title}</div>
                    <div className="flex gap-2 mt-1">
                      {task.due_date && (
                        <span className="text-xs text-[var(--color-text-muted)]">
                          Due: {new Date(task.due_date).toLocaleDateString()}
                        </span>
                      )}
                      {task.category && (
                        <span className="text-xs px-2 py-0.5 bg-[var(--color-bg-tertiary)] text-[var(--color-text-muted)] rounded-[var(--radius-sm)]">
                          {task.category}
                        </span>
                      )}
                    </div>
                  </div>
                </button>
                <button
                  onClick={(e) => {
                    e.stopPropagation()
                    setEditingTask(task)
                  }}
                  className="opacity-0 group-hover:opacity-100 text-[var(--color-text-muted)] hover:text-[var(--color-accent)] transition-opacity px-2"
                  title="Edit"
                >
                  ✏️
                </button>
                <button
                  onClick={(e) => deleteTask(e, task)}
                  className="opacity-0 group-hover:opacity-100 text-[var(--color-text-muted)] hover:text-[var(--color-error)] transition-opacity px-2"
                  title="Delete"
                >
                  🗑️
                </button>
              </div>
            ))}
          </div>
        )}

        {/* Completed tasks */}
        {completedTasks.length > 0 && (
          <div>
            <h2 className="text-sm font-medium text-[var(--color-text-muted)] mb-2">
              Completed ({completedTasks.length})
            </h2>
            <div className="space-y-2">
              {completedTasks.map((task) => (
                <button
                  key={task.id}
                  onClick={() => toggleCompleted(task)}
                  className="w-full text-left flex items-center gap-3 bg-[var(--color-bg-secondary)] border border-[var(--color-border)] rounded-[var(--radius-md)] p-4 opacity-60"
                >
                  <span className="w-5 h-5 rounded border-2 border-[var(--color-success)] bg-[var(--color-success)] flex items-center justify-center text-white text-xs">
                    ✓
                  </span>
                  <span className="text-[var(--color-text-primary)] line-through">
                    {task.title}
                  </span>
                </button>
              ))}
            </div>
          </div>
        )}
      </div>
      </div>
      {addTaskModal}
      {editTaskModal}
    </>
  )
}

