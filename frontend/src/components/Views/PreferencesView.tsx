import { useState, useEffect } from 'react'
import { apiRequest } from '../../lib/api'

interface Preferences {
  cooking_skill_level: string
  household_adults: number
  household_kids: number
  household_babies: number
  dietary_restrictions: string[]
  allergies: string[]
  available_equipment: string[]
  favorite_cuisines: string[]
  subdomain_guidance: Record<string, string>
}

interface FlavorPreference {
  ingredient_id: string
  preference_score: number
  ingredients?: { name: string }
}

function formatHousehold(prefs: Preferences): string {
  const parts: string[] = []
  if (prefs.household_adults) parts.push(`${prefs.household_adults} adult${prefs.household_adults !== 1 ? 's' : ''}`)
  if (prefs.household_kids) parts.push(`${prefs.household_kids} kid${prefs.household_kids !== 1 ? 's' : ''}`)
  if (prefs.household_babies) parts.push(`${prefs.household_babies} ${prefs.household_babies !== 1 ? 'babies' : 'baby'}`)
  return parts.join(', ') || '1 adult'
}

export function PreferencesView() {
  const [preferences, setPreferences] = useState<Preferences | null>(null)
  const [flavorPrefs, setFlavorPrefs] = useState<FlavorPreference[]>([])
  const [loading, setLoading] = useState(true)
  const [activeTab, setActiveTab] = useState<'profile' | 'guidance' | 'ingredients'>('profile')

  useEffect(() => {
    loadPreferences()
  }, [])

  const loadPreferences = async () => {
    try {
      const [prefsRes, flavorRes] = await Promise.all([
        apiRequest<{ data: Preferences[] }>('/api/tables/preferences'),
        apiRequest<{ data: FlavorPreference[] }>('/api/tables/flavor_preferences'),
      ])
      
      if (prefsRes.data?.[0]) {
        setPreferences(prefsRes.data[0])
      }
      setFlavorPrefs(flavorRes.data || [])
    } catch (error) {
      console.error('Failed to load preferences:', error)
    } finally {
      setLoading(false)
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="text-[var(--color-text-muted)]">Loading preferences...</div>
      </div>
    )
  }

  if (!preferences) {
    return (
      <div className="flex flex-col items-center justify-center h-64">
        <p className="text-[var(--color-text-muted)] mb-4">No preferences found</p>
        <p className="text-[var(--color-text-secondary)] text-sm">Complete onboarding to set up your preferences</p>
      </div>
    )
  }

  const likes = flavorPrefs.filter(f => f.preference_score > 0)
  const dislikes = flavorPrefs.filter(f => f.preference_score < 0)

  return (
    <div className="max-w-4xl mx-auto p-6">
      <h1 className="text-2xl font-semibold text-[var(--color-text-primary)] mb-6">
        Your Preferences
      </h1>

      {/* Tabs */}
      <div className="flex gap-2 mb-6 border-b border-[var(--color-border)]">
        {[
          { id: 'profile', label: 'Profile' },
          { id: 'guidance', label: 'Style Guidance' },
          { id: 'ingredients', label: 'Ingredients' },
        ].map(tab => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id as typeof activeTab)}
            className={`px-4 py-2 text-sm font-medium transition-colors border-b-2 -mb-px ${
              activeTab === tab.id
                ? 'text-[var(--color-accent)] border-[var(--color-accent)]'
                : 'text-[var(--color-text-muted)] border-transparent hover:text-[var(--color-text-primary)]'
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* Profile Tab */}
      {activeTab === 'profile' && (
        <div className="space-y-6">
          {/* Cooking Profile */}
          <Section title="Cooking Profile">
            <div className="grid grid-cols-2 gap-4">
              <InfoItem label="Skill Level" value={preferences.cooking_skill_level} />
              <InfoItem label="Household" value={formatHousehold(preferences)} />
            </div>
          </Section>

          {/* Dietary Info */}
          <Section title="Dietary Information">
            <div className="space-y-3">
              <TagList label="Dietary Restrictions" items={preferences.dietary_restrictions} emptyText="None" />
              <TagList label="Allergies" items={preferences.allergies} emptyText="None" />
            </div>
          </Section>

          {/* Equipment */}
          <Section title="Kitchen Equipment">
            <TagList items={preferences.available_equipment} emptyText="No equipment specified" />
          </Section>

          {/* Cuisines */}
          <Section title="Favorite Cuisines">
            <TagList items={preferences.favorite_cuisines} emptyText="No cuisines selected" />
          </Section>
        </div>
      )}

      {/* Guidance Tab */}
      {activeTab === 'guidance' && (
        <div className="space-y-4">
          {preferences.subdomain_guidance && Object.keys(preferences.subdomain_guidance).length > 0 ? (
            Object.entries(preferences.subdomain_guidance).map(([domain, guidance]) => (
              <div key={domain} className="bg-[var(--color-bg-secondary)] rounded-[var(--radius-lg)] p-4">
                <h3 className="text-sm font-medium text-[var(--color-accent)] uppercase tracking-wide mb-2">
                  {domain.replace(/_/g, ' ')}
                </h3>
                <p className="text-[var(--color-text-primary)] text-sm leading-relaxed whitespace-pre-wrap">
                  {guidance}
                </p>
              </div>
            ))
          ) : (
            <p className="text-[var(--color-text-muted)] text-center py-8">
              No style guidance set. Complete the onboarding interview to personalize Alfred's responses.
            </p>
          )}
        </div>
      )}

      {/* Ingredients Tab */}
      {activeTab === 'ingredients' && (
        <div className="space-y-6">
          <Section title={`Liked Ingredients (${likes.length})`}>
            {likes.length > 0 ? (
              <div className="flex flex-wrap gap-2">
                {likes.map(f => (
                  <span
                    key={f.ingredient_id}
                    className="px-3 py-1 bg-green-500/10 text-green-400 rounded-full text-sm"
                  >
                    👍 {f.ingredients?.name || f.ingredient_id}
                  </span>
                ))}
              </div>
            ) : (
              <p className="text-[var(--color-text-muted)]">No liked ingredients</p>
            )}
          </Section>

          <Section title={`Disliked Ingredients (${dislikes.length})`}>
            {dislikes.length > 0 ? (
              <div className="flex flex-wrap gap-2">
                {dislikes.map(f => (
                  <span
                    key={f.ingredient_id}
                    className="px-3 py-1 bg-red-500/10 text-red-400 rounded-full text-sm"
                  >
                    👎 {f.ingredients?.name || f.ingredient_id}
                  </span>
                ))}
              </div>
            ) : (
              <p className="text-[var(--color-text-muted)]">No disliked ingredients</p>
            )}
          </Section>
        </div>
      )}
    </div>
  )
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="bg-[var(--color-bg-secondary)] rounded-[var(--radius-lg)] p-4">
      <h3 className="text-sm font-medium text-[var(--color-text-secondary)] mb-3">{title}</h3>
      {children}
    </div>
  )
}

function InfoItem({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <span className="text-xs text-[var(--color-text-muted)] uppercase tracking-wide">{label}</span>
      <p className="text-[var(--color-text-primary)] font-medium capitalize">{value}</p>
    </div>
  )
}

function TagList({ label, items, emptyText }: { label?: string; items: string[]; emptyText: string }) {
  return (
    <div>
      {label && <span className="text-xs text-[var(--color-text-muted)] uppercase tracking-wide">{label}</span>}
      {items.length > 0 ? (
        <div className="flex flex-wrap gap-2 mt-1">
          {items.map(item => (
            <span
              key={item}
              className="px-3 py-1 bg-[var(--color-bg-tertiary)] text-[var(--color-text-primary)] rounded-full text-sm capitalize"
            >
              {item.replace(/-/g, ' ')}
            </span>
          ))}
        </div>
      ) : (
        <p className="text-[var(--color-text-muted)] text-sm mt-1">{emptyText}</p>
      )}
    </div>
  )
}
