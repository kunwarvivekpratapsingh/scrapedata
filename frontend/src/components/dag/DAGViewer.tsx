import { useState, useCallback, useMemo } from 'react'
import {
  ReactFlow,
  Background,
  Controls,
  MiniMap,
  BackgroundVariant,
} from '@xyflow/react'
import '@xyflow/react/dist/style.css'

import type { GeneratedDAG, ExecutionResult, DAGNodeSpec, NodeExecutionResult } from '../../types/eval'
import { DAGNodeCard } from './DAGNodeCard'
import { NodeDetailDrawer } from './NodeDetailDrawer'
import { buildFlowElements, canvasHeight } from './layerLayout'

// eslint-disable-next-line @typescript-eslint/no-explicit-any
const nodeTypes: Record<string, any> = {
  dagNode: DAGNodeCard,
}

interface DAGViewerProps {
  dag: GeneratedDAG
  execResult: ExecutionResult | null
}

export function DAGViewer({ dag, execResult }: DAGViewerProps) {
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null)

  const handleClickNode = useCallback((nodeId: string) => {
    setSelectedNodeId((prev) => (prev === nodeId ? null : nodeId))
  }, [])

  const { nodes: rfNodes, edges: rfEdges } = useMemo(
    () =>
      buildFlowElements(
        dag.nodes,
        dag.edges,
        dag.final_answer_node,
        execResult,
        handleClickNode
      ),
    [dag, execResult, handleClickNode]
  )

  const selectedNode: DAGNodeSpec | null =
    selectedNodeId ? dag.nodes.find((n) => n.node_id === selectedNodeId) ?? null : null

  const selectedExecResult: NodeExecutionResult | null =
    selectedNode && execResult
      ? execResult.node_results?.find((r) => r.node_id === selectedNodeId) ?? null
      : null

  const height = canvasHeight(dag.nodes)

  return (
    <div className="relative">
      <div
        className="w-full rounded-xl overflow-hidden border border-gray-800"
        style={{ height: Math.max(height, 220) }}
      >
        <ReactFlow
          nodes={rfNodes}
          edges={rfEdges}
          nodeTypes={nodeTypes}
          fitView
          fitViewOptions={{ padding: 0.15 }}
          minZoom={0.3}
          maxZoom={2}
          proOptions={{ hideAttribution: true }}
        >
          <Background
            variant={BackgroundVariant.Dots}
            gap={20}
            size={1}
            color="#374151"
          />
          <Controls
            showInteractive={false}
            style={{ background: '#111827', border: '1px solid #374151' }}
          />
          <MiniMap
            nodeColor={(n) => {
              const d = n.data as { color?: string }
              return d.color ?? '#374151'
            }}
            style={{ background: '#111827', border: '1px solid #374151' }}
            maskColor="rgba(0,0,0,0.5)"
          />
        </ReactFlow>
      </div>

      <NodeDetailDrawer
        node={selectedNode}
        execResult={selectedExecResult}
        onClose={() => setSelectedNodeId(null)}
      />
    </div>
  )
}
