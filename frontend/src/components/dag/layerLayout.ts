/**
 * Layer-based DAG layout algorithm.
 * Direct port from generate_report.py → render_dag_svg().
 *
 * Nodes are placed in columns by layer index (left to right).
 * Within each column nodes are vertically centered in the canvas.
 */
import type { Node, Edge } from '@xyflow/react'
import type { DAGNodeSpec, DAGEdge, ExecutionResult } from '../../types/eval'

export const NODE_W = 220
export const NODE_H = 80
export const H_GAP = 80
export const V_GAP = 18
export const PAD = 32

export const LAYER_COLORS = [
  '#3b82f6', // blue
  '#0d9488', // teal
  '#7c3aed', // violet
  '#d97706', // amber
  '#dc2626', // red
]

export function layerColor(layer: number): string {
  return LAYER_COLORS[layer % LAYER_COLORS.length]
}

export interface DAGNodeData extends Record<string, unknown> {
  spec: DAGNodeSpec
  color: string
  isFinalAnswer: boolean
  executionResult: ReturnType<typeof getNodeResult>
  onClickNode: (nodeId: string) => void
}

function getNodeResult(nodeId: string, execResult: ExecutionResult | null) {
  if (!execResult) return null
  return execResult.node_results?.find((n) => n.node_id === nodeId) ?? null
}

export function buildFlowElements(
  nodes: DAGNodeSpec[],
  edges: DAGEdge[],
  finalAnswerNode: string,
  execResult: ExecutionResult | null,
  onClickNode: (nodeId: string) => void
): { nodes: Node[]; edges: Edge[] } {
  if (!nodes.length) return { nodes: [], edges: [] }

  // Group by layer
  const layerMap: Map<number, DAGNodeSpec[]> = new Map()
  for (const n of nodes) {
    if (!layerMap.has(n.layer)) layerMap.set(n.layer, [])
    layerMap.get(n.layer)!.push(n)
  }

  const maxLayer = Math.max(...nodes.map((n) => n.layer))

  // Compute canvas height (tallest column)
  const maxColHeight = Math.max(
    ...[...layerMap.values()].map(
      (col) => col.length * NODE_H + (col.length - 1) * V_GAP
    )
  )
  const canvasH = maxColHeight + PAD * 2

  // Build React Flow nodes
  const rfNodes: Node[] = []
  for (let layer = 0; layer <= maxLayer; layer++) {
    const col = layerMap.get(layer) ?? []
    const colH = col.length * NODE_H + (col.length - 1) * V_GAP
    const colStartY = PAD + (maxColHeight - colH) / 2
    const x = PAD + layer * (NODE_W + H_GAP)

    col.forEach((spec, i) => {
      const y = colStartY + i * (NODE_H + V_GAP)
      const nodeData: DAGNodeData = {
        spec,
        color: layerColor(layer),
        isFinalAnswer: spec.node_id === finalAnswerNode,
        executionResult: getNodeResult(spec.node_id, execResult),
        onClickNode,
      }
      rfNodes.push({
        id: spec.node_id,
        type: 'dagNode',
        position: { x, y },
        data: nodeData,
        draggable: true,
      })
    })
  }

  // Build React Flow edges
  const rfEdges: Edge[] = edges.map((e, idx) => ({
    id: `e-${e.source}-${e.target}-${idx}`,
    source: e.source,
    target: e.target,
    type: 'smoothstep',
    animated: false,
    style: { stroke: '#4b5563', strokeWidth: 1.5 },
  }))

  return { nodes: rfNodes, edges: rfEdges }
}

export function canvasHeight(nodes: DAGNodeSpec[]): number {
  if (!nodes.length) return 200
  const layerMap: Map<number, number> = new Map()
  for (const n of nodes) {
    layerMap.set(n.layer, (layerMap.get(n.layer) ?? 0) + 1)
  }
  const maxCol = Math.max(...layerMap.values())
  return maxCol * NODE_H + (maxCol - 1) * V_GAP + PAD * 2
}
