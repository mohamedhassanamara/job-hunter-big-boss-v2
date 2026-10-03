import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api, apiUrl } from '@/lib/api'
import type { ChestOpen, Chests, GoalTile, MotivationSummary, Shop, Suggestion, TokenEntry, Wins, Woop, WinEntry } from '@/lib/types'

const root = ['motivation'] as const
export const motivationKeys = {
  summary: [...root, 'summary'] as const,
  chests: [...root, 'chests'] as const,
  tokens: [...root, 'tokens'] as const,
  shop: [...root, 'shop'] as const,
  goals: [...root, 'goals'] as const,
  woops: [...root, 'woops'] as const,
  wins: [...root, 'wins'] as const,
  suggestion: [...root, 'suggestion'] as const,
}

/** A file you uploaded (goal tile, shop image), as a URL an <img>/<video> can load. */
export const motivationFile = (name: string) => apiUrl(`/motivation/files/${name}`)

/** The top bar and Today: streak, today's progress, tokens, chests. Refreshed every few minutes
 * so the day rolls over at midnight without a reload. */
export function useMotivation() {
  return useQuery({
    queryKey: motivationKeys.summary,
    queryFn: () => api.get<MotivationSummary>('/motivation/summary'),
    refetchInterval: 5 * 60_000,
    retry: false,
  })
}

/** Hidden everywhere when Settings → Motivation is off (or the summary can't load). */
export function useMotivationEnabled() {
  return useMotivation().data?.enabled ?? false
}

function useInvalidateMotivation() {
  const qc = useQueryClient()
  return () => void qc.invalidateQueries({ queryKey: root })
}

export function useChestHistory() {
  return useQuery({ queryKey: motivationKeys.chests, queryFn: () => api.get<ChestOpen[]>('/motivation/chests') })
}

/** Open one chest. The badges refresh when the dialog closes (`useRefreshMotivation`), so the
 * top bar doesn't give the result away before the reveal. */
export function useOpenChest() {
  return useMutation({
    mutationFn: () => api.post<{ chest: ChestOpen; balance: number; chests: Chests }>('/motivation/chests/open'),
  })
}

export function useRefreshMotivation() {
  return useInvalidateMotivation()
}

export function useTokens() {
  return useQuery({ queryKey: motivationKeys.tokens, queryFn: () => api.get<{ balance: number; ledger: TokenEntry[] }>('/motivation/tokens') })
}

export function useShop() {
  return useQuery({ queryKey: motivationKeys.shop, queryFn: () => api.get<Shop>('/motivation/shop') })
}

export interface ShopItemInput {
  name: string
  price: number
  emoji: string | null
  image_name: string | null
}

export function useSaveShopItem() {
  const qc = useQueryClient()
  const invalidate = useInvalidateMotivation()
  return useMutation({
    mutationFn: ({ id, ...body }: Partial<ShopItemInput> & { id?: number; archived?: boolean }) =>
      id ? api.patch<Shop>(`/motivation/shop/${id}`, body) : api.post<Shop>('/motivation/shop', body),
    onSuccess: (shop) => qc.setQueryData(motivationKeys.shop, shop),
    onSettled: invalidate,
  })
}

export function useBuy() {
  const qc = useQueryClient()
  const invalidate = useInvalidateMotivation()
  return useMutation({
    mutationFn: (id: number) => api.post<Shop>(`/motivation/shop/${id}/buy`),
    onSuccess: (shop) => qc.setQueryData(motivationKeys.shop, shop),
    onSettled: invalidate,
  })
}

export function useRedeem() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, redeemed }: { id: number; redeemed: boolean }) => api.patch<Shop>(`/motivation/purchases/${id}`, { redeemed }),
    onSuccess: (shop) => qc.setQueryData(motivationKeys.shop, shop),
  })
}

export function useUploadImage() {
  return useMutation({
    mutationFn: (file: File) => {
      const form = new FormData()
      form.append('file', file)
      return api.post<{ name: string }>('/motivation/images', form)
    },
  })
}

export function useGoals() {
  return useQuery({ queryKey: motivationKeys.goals, queryFn: () => api.get<GoalTile[]>('/motivation/goals') })
}

export function useAddGoal() {
  const invalidate = useInvalidateMotivation()
  return useMutation({
    mutationFn: ({ file, caption }: { file: File; caption?: string }) => {
      const form = new FormData()
      form.append('file', file)
      form.append('caption', caption ?? '')
      return api.post<GoalTile>('/motivation/goals', form)
    },
    onSettled: invalidate,
  })
}

export function useEditGoal() {
  const invalidate = useInvalidateMotivation()
  return useMutation({
    mutationFn: ({ id, caption }: { id: number; caption: string }) => api.patch<GoalTile>(`/motivation/goals/${id}`, { caption }),
    onSettled: invalidate,
  })
}

export function useOrderGoals() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (ids: number[]) => api.put<GoalTile[]>('/motivation/goals/order', { ids }),
    onMutate: (ids) => {
      const tiles = qc.getQueryData<GoalTile[]>(motivationKeys.goals) ?? []
      qc.setQueryData(
        motivationKeys.goals,
        ids.map((id) => tiles.find((t) => t.id === id)).filter(Boolean),
      )
    },
    onSuccess: (tiles) => qc.setQueryData(motivationKeys.goals, tiles),
  })
}

export function useDeleteGoal() {
  const invalidate = useInvalidateMotivation()
  return useMutation({ mutationFn: (id: number) => api.del<null>(`/motivation/goals/${id}`), onSettled: invalidate })
}

export function useWoops() {
  return useQuery({ queryKey: motivationKeys.woops, queryFn: () => api.get<Woop[]>('/motivation/woops') })
}

export function useSaveWoop() {
  const invalidate = useInvalidateMotivation()
  return useMutation({
    mutationFn: (body: Omit<Woop, 'id' | 'created_at'>) => api.post<Woop>('/motivation/woops', body as unknown as Record<string, string>),
    onSettled: invalidate,
  })
}

export function useDeleteWoop() {
  const invalidate = useInvalidateMotivation()
  return useMutation({ mutationFn: (id: number) => api.del<null>(`/motivation/woops/${id}`), onSettled: invalidate })
}

export function useWins() {
  return useQuery({ queryKey: motivationKeys.wins, queryFn: () => api.get<Wins>('/motivation/wins') })
}

export function useAddWin() {
  const invalidate = useInvalidateMotivation()
  return useMutation({ mutationFn: (text: string) => api.post<WinEntry>('/motivation/journal', { text }), onSettled: invalidate })
}

export function useDeleteWin() {
  const invalidate = useInvalidateMotivation()
  return useMutation({ mutationFn: (id: number) => api.del<null>(`/motivation/journal/${id}`), onSettled: invalidate })
}

export function useSuggestion() {
  return useQuery({ queryKey: motivationKeys.suggestion, queryFn: () => api.get<Suggestion>('/motivation/suggestion') })
}
