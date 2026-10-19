// Import G6's core and only the extensions used by the knowledge graph page.
// The package root imports `preset`, which eagerly registers every built-in.
import { Graph } from '@antv/g6/esm/runtime/graph';
import { ExtensionCategory } from '@antv/g6/esm/constants/registry';
import { register } from '@antv/g6/esm/registry/register';
import { Circle } from '@antv/g6/esm/elements/nodes/circle';
import { Line } from '@antv/g6/esm/elements/edges/line';
import { DragCanvas } from '@antv/g6/esm/behaviors/drag-canvas';
import { DragElement } from '@antv/g6/esm/behaviors/drag-element';
import { HoverActivate } from '@antv/g6/esm/behaviors/hover-activate';
import { ZoomCanvas } from '@antv/g6/esm/behaviors/zoom-canvas';
import { Minimap } from '@antv/g6/esm/plugins/minimap';
import { D3ForceLayout } from '@antv/layout/lib/algorithm/d3-force/index.js';
import { DagreLayout } from '@antv/layout/lib/algorithm/dagre/index.js';
import { RadialLayout } from '@antv/layout/lib/algorithm/radial/index.js';

register(ExtensionCategory.NODE, 'circle', Circle);
register(ExtensionCategory.EDGE, 'line', Line);
register(ExtensionCategory.LAYOUT, 'd3-force', D3ForceLayout);
register(ExtensionCategory.LAYOUT, 'dagre', DagreLayout);
register(ExtensionCategory.LAYOUT, 'radial', RadialLayout);
register(ExtensionCategory.BEHAVIOR, 'drag-canvas', DragCanvas);
register(ExtensionCategory.BEHAVIOR, 'drag-element', DragElement);
register(ExtensionCategory.BEHAVIOR, 'hover-activate', HoverActivate);
register(ExtensionCategory.BEHAVIOR, 'zoom-canvas', ZoomCanvas);
register(ExtensionCategory.PLUGIN, 'minimap', Minimap);

export { Graph };
