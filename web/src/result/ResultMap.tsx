import { useEffect, useRef } from "react";
import {
  Map as MapLibreMap,
  Marker,
  NavigationControl,
  setWorkerUrl,
  type GeoJSONSource,
  type ImageSource,
  type MapMouseEvent,
  type StyleSpecification,
} from "maplibre-gl";
import maplibreWorkerUrl from "maplibre-gl/dist/maplibre-gl-worker.mjs?url";
import "maplibre-gl/dist/maplibre-gl.css";

import type {
  FlowVectorFeatureCollection,
  FlowViewport,
  ResultMetadataResponse,
} from "../api/client";
import { resultBounds, resultImageCoordinates } from "./resultGeometry";

setWorkerUrl(maplibreWorkerUrl);

export type FlowRenderStats = {
  sourceFeatureCount: number;
  renderedFeatureCount: number;
  svgArrowCount: number;
  layerOrder: string[];
  featureBounds: [number, number, number, number] | null;
  mapBounds: [number, number, number, number];
};

type Props = {
  metadata: Pick<ResultMetadataResponse, "bounds">;
  imageUrl: string;
  flowVectorData: FlowVectorFeatureCollection | null;
  flowSpeedRange?: readonly [number, number];
  flowSpeedBreaks?: readonly number[];
  flowDisplayMode?: "vectors" | "particles" | null;
  backgroundOpacity: number;
  mapLabel: string;
  focusPoint?: { lon: number; lat: number } | null;
  onInspect?: (lon: number, lat: number) => void;
  onFlowRenderStats?: (stats: FlowRenderStats | null) => void;
  onViewportChange?: (viewport: FlowViewport, zoom: number) => void;
  onCaptureReady?: (capture: (() => Promise<HTMLCanvasElement>) | null) => void;
};

const EMPTY_FLOW = {
  type: "FeatureCollection" as const,
  features: [],
};

const FLOW_SOURCE_ID = "flow-vector-source";
const FLOW_HALO_LAYER_ID = "flow-vector-halo";
const FLOW_LINE_LAYER_ID = "flow-vector-lines";
const FLOW_ARROW_LENGTH_PX = 18;
const PARTICLE_TRAIL_LENGTH_PX = 75;
const PARTICLE_MIN_VECTOR_CROSSINGS = 15;
const PARTICLE_TRAIL_SAMPLE_PX = 3;
const PARTICLE_MAX_NEIGHBORS = 8;
const PARTICLES_PER_VECTOR = 2;
const PARTICLE_PHASE_GROUPS = 4;
const PARTICLE_SPEED_SCALE_PX_PER_METER = 36;
const PARTICLE_MIN_SPEED_PX_PER_SECOND = 1.5;
const PARTICLE_MAX_SPEED_PX_PER_SECOND = 96;
const GSI_SOURCE_MAX_ZOOM = 18;
const RESULT_MAX_ZOOM = 21;

type ScreenPoint = { x: number; y: number };

type ProjectedFlowNode = ScreenPoint & {
  dx: number;
  dy: number;
  speedMps: number;
  speedPxPerSecond: number;
};

type ProjectedFlowField = {
  nodes: ProjectedFlowNode[];
  buckets: Map<string, number[]>;
  spacingPx: number;
  cellSizePx: number;
};

type FlowParticle = ScreenPoint & {
  sourceIndex: number;
  copyIndex: number;
  travelledPx: number;
  targetDistancePx: number;
  trail: ScreenPoint[];
  generation: number;
};

function flowColor(speedMps: number, range: readonly [number, number], breaks?: readonly number[]): string {
  const colors = ["#2DC4B2", "#3BB2D0", "#3F51B5", "#8E44AD", "#E74C3C", "#A52A2A", "#7F0000"];
  if (breaks) {
    let index = 0;
    while (index < breaks.length - 2 && speedMps > breaks[index + 1]) index++;
    return colors[Math.min(index, colors.length - 1)];
  }
  const [minimum, maximum] = range;
  if (maximum <= minimum) return colors[colors.length - 1];
  return colors[Math.min(colors.length - 1, Math.floor(Math.max(0, Math.min(1, (speedMps - minimum) / (maximum - minimum))) * colors.length))];
}

export function particleSpeedPxPerSecond(speedMps: number): number {
  return Math.min(
    PARTICLE_MAX_SPEED_PX_PER_SECOND,
    Math.max(PARTICLE_MIN_SPEED_PX_PER_SECOND, Math.max(0, speedMps) * PARTICLE_SPEED_SCALE_PX_PER_METER),
  );
}

function colorWithAlpha(hex: string, alpha: number): string {
  const red = Number.parseInt(hex.slice(1, 3), 16);
  const green = Number.parseInt(hex.slice(3, 5), 16);
  const blue = Number.parseInt(hex.slice(5, 7), 16);
  return `rgba(${red}, ${green}, ${blue}, ${alpha})`;
}

function particlePhase(row: number, column: number): number {
  // Stable pseudo-random phase keeps one-second lifetimes continuous while
  // the surrounding flow geometry is interpolated during timeline playback.
  const mixed = Math.imul(row + 1, 73856093) ^ Math.imul(column + 1, 19349663);
  return (mixed >>> 0) / 0x1_0000_0000;
}

function median(values: number[]): number {
  if (values.length === 0) return 24;
  const sorted = [...values].sort((left, right) => left - right);
  const middle = Math.floor(sorted.length / 2);
  return sorted.length % 2 === 0
    ? (sorted[middle - 1] + sorted[middle]) / 2
    : sorted[middle];
}

function estimateVectorSpacing(nodes: ProjectedFlowNode[]): number {
  if (nodes.length < 2) return 24;
  const nearestDistances = nodes.map((node, index) => {
    let nearest = Number.POSITIVE_INFINITY;
    nodes.forEach((candidate, candidateIndex) => {
      if (candidateIndex === index) return;
      nearest = Math.min(nearest, Math.hypot(candidate.x - node.x, candidate.y - node.y));
    });
    return nearest;
  }).filter(Number.isFinite);
  return Math.max(8, median(nearestDistances));
}

function bucketKey(x: number, y: number, cellSizePx: number): string {
  return `${Math.floor(x / cellSizePx)}:${Math.floor(y / cellSizePx)}`;
}

function createProjectedFlowField(nodes: ProjectedFlowNode[]): ProjectedFlowField {
  const spacingPx = estimateVectorSpacing(nodes);
  const cellSizePx = Math.max(8, spacingPx * 1.5);
  const buckets = new Map<string, number[]>();
  nodes.forEach((node, index) => {
    const key = bucketKey(node.x, node.y, cellSizePx);
    const bucket = buckets.get(key) ?? [];
    bucket.push(index);
    buckets.set(key, bucket);
  });
  return { nodes, buckets, spacingPx, cellSizePx };
}

function sampleProjectedFlow(
  field: ProjectedFlowField,
  x: number,
  y: number,
): Pick<ProjectedFlowNode, "dx" | "dy" | "speedMps" | "speedPxPerSecond"> | null {
  if (field.nodes.length === 0) return null;
  const cellX = Math.floor(x / field.cellSizePx);
  const cellY = Math.floor(y / field.cellSizePx);
  const searchRadius = 2;
  const maximumDistance = field.spacingPx * 3;
  const candidates: Array<{ node: ProjectedFlowNode; distance: number }> = [];
  for (let offsetY = -searchRadius; offsetY <= searchRadius; offsetY += 1) {
    for (let offsetX = -searchRadius; offsetX <= searchRadius; offsetX += 1) {
      const indices = field.buckets.get(`${cellX + offsetX}:${cellY + offsetY}`) ?? [];
      indices.forEach((index) => {
        const node = field.nodes[index];
        const distance = Math.hypot(node.x - x, node.y - y);
        if (distance <= maximumDistance) candidates.push({ node, distance });
      });
    }
  }
  if (candidates.length === 0) return null;
  candidates.sort((left, right) => left.distance - right.distance);

  let weightedDx = 0;
  let weightedDy = 0;
  let weightedSpeedMps = 0;
  let weightedSpeedPx = 0;
  let totalWeight = 0;
  candidates.slice(0, PARTICLE_MAX_NEIGHBORS).forEach(({ node, distance }) => {
    const normalizedDistance = distance / field.spacingPx;
    const weight = 1 / (0.15 + normalizedDistance * normalizedDistance);
    weightedDx += node.dx * weight;
    weightedDy += node.dy * weight;
    weightedSpeedMps += node.speedMps * weight;
    weightedSpeedPx += node.speedPxPerSecond * weight;
    totalWeight += weight;
  });
  const directionLength = Math.hypot(weightedDx, weightedDy);
  if (totalWeight <= 0 || directionLength <= 1e-6) return null;
  return {
    dx: weightedDx / directionLength,
    dy: weightedDy / directionLength,
    speedMps: weightedSpeedMps / totalWeight,
    speedPxPerSecond: weightedSpeedPx / totalWeight,
  };
}

function appendTrailPoint(particle: FlowParticle, point: ScreenPoint): void {
  const last = particle.trail[particle.trail.length - 1];
  if (last && Math.hypot(point.x - last.x, point.y - last.y) < PARTICLE_TRAIL_SAMPLE_PX) return;
  particle.trail.push(point);
  let trailLength = 0;
  for (let index = particle.trail.length - 1; index > 0; index -= 1) {
    const current = particle.trail[index];
    const previous = particle.trail[index - 1];
    trailLength += Math.hypot(current.x - previous.x, current.y - previous.y);
    if (trailLength > PARTICLE_TRAIL_LENGTH_PX) {
      particle.trail.splice(0, index - 1);
      break;
    }
  }
}

function drawFadingTrail(
  context: CanvasRenderingContext2D,
  trail: ScreenPoint[],
  particleColor: string,
): void {
  if (trail.length < 2) return;
  const tail = trail[0];
  const head = trail[trail.length - 1];
  context.beginPath();
  context.moveTo(tail.x, tail.y);
  trail.slice(1).forEach((point) => context.lineTo(point.x, point.y));
  context.lineCap = "round";

  const haloGradient = context.createLinearGradient(tail.x, tail.y, head.x, head.y);
  haloGradient.addColorStop(0, "rgba(255, 255, 255, 0)");
  haloGradient.addColorStop(1, "rgba(255, 255, 255, 0.9)");
  context.strokeStyle = haloGradient;
  context.lineWidth = 5.5;
  context.stroke();

  const trailGradient = context.createLinearGradient(tail.x, tail.y, head.x, head.y);
  trailGradient.addColorStop(0, colorWithAlpha(particleColor, 0));
  trailGradient.addColorStop(1, particleColor);
  context.strokeStyle = trailGradient;
  context.lineWidth = 2.5;
  context.stroke();
}

function overlayStyle(
  metadata: Pick<ResultMetadataResponse, "bounds">,
  imageUrl: string,
): StyleSpecification {
  const coordinates = resultImageCoordinates(metadata.bounds);
  const boundaryCoordinates = [
    [metadata.bounds.west_deg, metadata.bounds.south_deg],
    [metadata.bounds.east_deg, metadata.bounds.south_deg],
    [metadata.bounds.east_deg, metadata.bounds.north_deg],
    [metadata.bounds.west_deg, metadata.bounds.north_deg],
    [metadata.bounds.west_deg, metadata.bounds.south_deg],
  ];

  return {
    version: 8,
    sources: {
      "result-overlay": {
        type: "image",
        url: imageUrl,
        coordinates,
      },
      [FLOW_SOURCE_ID]: {
        type: "geojson",
        data: EMPTY_FLOW,
      },
      "analysis-boundary": {
        type: "geojson",
        data: {
          type: "Feature",
          properties: {},
          geometry: {
            type: "LineString",
            coordinates: boundaryCoordinates,
          },
        },
      },
    },
    layers: [
      {
        id: "result-overlay",
        type: "raster",
        source: "result-overlay",
        paint: {
          "raster-opacity": 1,
          "raster-fade-duration": 0,
        },
      },
      {
        id: FLOW_HALO_LAYER_ID,
        type: "line",
        source: FLOW_SOURCE_ID,
        layout: {
          visibility: "none",
          "line-cap": "round",
          "line-join": "round",
        },
        paint: {
          "line-color": "#FFFFFF",
          "line-width": [
            "interpolate",
            ["linear"],
            ["get", "speed_mps"],
            0.001, 5.0,
            0.50, 6.0,
            2.00, 7.5,
          ],
          "line-opacity": 0.9,
        },
      },
      {
        id: FLOW_LINE_LAYER_ID,
        type: "line",
        source: FLOW_SOURCE_ID,
        layout: {
          visibility: "none",
          "line-cap": "round",
          "line-join": "round",
        },
        paint: {
          "line-color": [
            "step",
            ["get", "speed_mps"],
            "#2DC4B2",
            0.10, "#3BB2D0",
            0.30, "#3F51B5",
            0.50, "#8E44AD",
            1.00, "#E74C3C",
            2.00, "#7F0000",
          ],
          "line-width": [
            "interpolate",
            ["linear"],
            ["get", "speed_mps"],
            0.001, 2.8,
            0.50, 3.6,
            2.00, 4.8,
          ],
          "line-opacity": 1,
        },
      },
      {
        id: "analysis-boundary-casing",
        type: "line",
        source: "analysis-boundary",
        layout: {
          visibility: "visible",
          "line-cap": "round",
          "line-join": "round",
        },
        paint: {
          "line-color": "#FFFFFF",
          "line-width": 8,
          "line-opacity": 0.95,
        },
      },
      {
        id: "analysis-boundary-outline",
        type: "line",
        source: "analysis-boundary",
        layout: {
          visibility: "visible",
          "line-cap": "round",
          "line-join": "round",
        },
        paint: {
          "line-color": "#DC2626",
          "line-width": 4,
          "line-opacity": 1,
        },
      },
    ],
  };
}

export default function ResultMap({
  metadata,
  imageUrl,
  flowVectorData,
  flowSpeedRange = [0.001, 1] as const,
  flowSpeedBreaks,
  flowDisplayMode = flowVectorData ? "vectors" : null,
  backgroundOpacity,
  mapLabel,
  focusPoint,
  onInspect,
  onFlowRenderStats,
  onViewportChange,
  onCaptureReady,
}: Props) {
  const baseContainerRef = useRef<HTMLDivElement | null>(null);
  const overlayContainerRef = useRef<HTMLDivElement | null>(null);
  const baseMapRef = useRef<MapLibreMap | null>(null);
  const overlayMapRef = useRef<MapLibreMap | null>(null);
  const markerRef = useRef<Marker | null>(null);
  const flowSvgRef = useRef<SVGSVGElement | null>(null);
  const flowCanvasRef = useRef<HTMLCanvasElement | null>(null);
  const inspectRef = useRef(onInspect);
  const viewportRef = useRef(onViewportChange);
  const initialImageUrlRef = useRef(imageUrl);

  useEffect(() => {
    const map = overlayMapRef.current;
    if (!map || !focusPoint) return;
    map.jumpTo({ center: [focusPoint.lon, focusPoint.lat] });
    markerRef.current?.remove();
    markerRef.current = new Marker({ color: "#1f2937" })
      .setLngLat([focusPoint.lon, focusPoint.lat])
      .addTo(map);
  }, [focusPoint]);

  useEffect(() => {
    inspectRef.current = onInspect;
  }, [onInspect]);

  useEffect(() => {
    viewportRef.current = onViewportChange;
  }, [onViewportChange]);


  useEffect(() => {
    const baseContainer = baseContainerRef.current;
    const overlayContainer = overlayContainerRef.current;
    if (!baseContainer || !overlayContainer) return;

    const bounds = resultBounds(metadata.bounds);
    const baseMap = new MapLibreMap({
      container: baseContainer,
      style: {
        version: 8,
        sources: {
          gsi: {
            type: "raster",
            tiles: ["https://cyberjapandata.gsi.go.jp/xyz/std/{z}/{x}/{y}.png"],
            tileSize: 256,
            maxzoom: GSI_SOURCE_MAX_ZOOM,
            attribution: "国土地理院",
          },
        },
        layers: [{ id: "gsi", type: "raster", source: "gsi" }],
      },
      bounds,
      fitBoundsOptions: { padding: 32, maxZoom: 18 },
      maxZoom: RESULT_MAX_ZOOM,
      interactive: false,
    });
    baseMapRef.current = baseMap;

    const overlayMap = new MapLibreMap({
      container: overlayContainer,
      style: overlayStyle(metadata, initialImageUrlRef.current),
      bounds,
      fitBoundsOptions: { padding: 32, maxZoom: 18 },
      maxZoom: RESULT_MAX_ZOOM,
      attributionControl: false,
    });
    overlayMapRef.current = overlayMap;
    onCaptureReady?.(async () => {
      const source = overlayMap.getCanvas();
      const output = document.createElement("canvas");
      output.width = source.width;
      output.height = source.height;
      const context = output.getContext("2d");
      if (!context) throw new Error("Canvas 2D context is unavailable");
      context.drawImage(source, 0, 0);
      const particles = flowCanvasRef.current;
      if (particles) context.drawImage(particles, 0, 0, output.width, output.height);
      const svg = flowSvgRef.current;
      if (svg && svg.childElementCount > 0) {
        const markup = new XMLSerializer().serializeToString(svg);
        const blobUrl = URL.createObjectURL(new Blob([markup], { type: "image/svg+xml" }));
        try {
          const image = new Image();
          await new Promise<void>((resolve, reject) => {
            image.onload = () => resolve();
            image.onerror = () => reject(new Error("SVG capture failed"));
            image.src = blobUrl;
          });
          context.drawImage(image, 0, 0, output.width, output.height);
        } finally {
          URL.revokeObjectURL(blobUrl);
        }
      }
      return output;
    });
    overlayMap.addControl(new NavigationControl({ showCompass: false }), "top-right");

    const syncBase = () => {
      const center = overlayMap.getCenter();
      baseMap.jumpTo({
        center: [center.lng, center.lat],
        zoom: overlayMap.getZoom(),
        bearing: overlayMap.getBearing(),
        pitch: overlayMap.getPitch(),
      });
    };

    const emitViewport = () => {
      const b = overlayMap.getBounds();
      viewportRef.current?.({ west: b.getWest(), south: b.getSouth(), east: b.getEast(), north: b.getNorth() }, overlayMap.getZoom());
    };

    const handleClick = (event: MapMouseEvent) => {
      if (!inspectRef.current) return;
      markerRef.current?.remove();
      markerRef.current = new Marker({ color: "#1f2937" })
        .setLngLat(event.lngLat)
        .addTo(overlayMap);
      inspectRef.current(event.lngLat.lng, event.lngLat.lat);
    };

    overlayMap.on("move", syncBase);
    overlayMap.on("zoomend", emitViewport);
    overlayMap.on("moveend", emitViewport);
    overlayMap.on("click", handleClick);
    emitViewport();
    overlayMap.once("load", () => {
      syncBase();
      emitViewport();
      overlayMap.setLayoutProperty("analysis-boundary-casing", "visibility", "visible");
      overlayMap.setLayoutProperty("analysis-boundary-outline", "visibility", "visible");
      overlayMap.triggerRepaint();
    });

    return () => {
      markerRef.current?.remove();
      markerRef.current = null;
      onCaptureReady?.(null);
      overlayMap.off("move", syncBase);
      overlayMap.off("zoomend", emitViewport);
      overlayMap.off("moveend", emitViewport);
      overlayMap.off("click", handleClick);
      overlayMap.remove();
      baseMap.remove();
      overlayMapRef.current = null;
      baseMapRef.current = null;
    };
  }, [metadata]);

  useEffect(() => {
    const map = overlayMapRef.current;
    if (!map) return;

    const update = () => {
      const source = map.getSource("result-overlay") as ImageSource | undefined;
      source?.updateImage({
        url: imageUrl,
        coordinates: resultImageCoordinates(metadata.bounds),
      });
      map.triggerRepaint();
    };

    if (map.getSource("result-overlay")) {
      update();
      return;
    }
    map.once("load", update);
    return () => {
      map.off("load", update);
    };
  }, [imageUrl, metadata.bounds]);

  useEffect(() => {
    const map = overlayMapRef.current;
    const svg = flowSvgRef.current;
    if (!map || !svg) return;

    let idleReporter: (() => void) | null = null;

    const featureBounds = (): [number, number, number, number] | null => {
      if (!flowVectorData || flowVectorData.features.length === 0) return null;
      const points = flowVectorData.features.flatMap((feature) =>
        feature.geometry.coordinates.flatMap((line) => line),
      );
      if (points.length === 0) return null;
      const lons = points.map((point) => point[0]);
      const lats = points.map((point) => point[1]);
      return [
        Math.min(...lons),
        Math.min(...lats),
        Math.max(...lons),
        Math.max(...lats),
      ];
    };

    const renderSvg = (displayFlow: FlowVectorFeatureCollection | null) => {
      svg.replaceChildren();
      const width = Math.max(1, svg.clientWidth);
      const height = Math.max(1, svg.clientHeight);
      svg.setAttribute("viewBox", `0 0 ${width} ${height}`);

      if (!displayFlow || displayFlow.features.length === 0) {
        svg.dataset.flowSvgArrows = "0";
        return;
      }

      const namespace = "http://www.w3.org/2000/svg";
      for (const feature of displayFlow.features) {
        const shaft = feature.geometry.coordinates[0];
        if (!shaft || shaft.length < 2) continue;
        const projectedTail = map.project([shaft[0][0], shaft[0][1]]);
        const projectedTip = map.project([
          shaft[shaft.length - 1][0],
          shaft[shaft.length - 1][1],
        ]);
        let dx = projectedTip.x - projectedTail.x;
        let dy = projectedTip.y - projectedTail.y;
        const rawLength = Math.hypot(dx, dy);
        if (rawLength <= 1e-6) continue;
        dx /= rawLength;
        dy /= rawLength;

        // Keep the accepted screen-space vector rendering from d749d5:
        // geometry supplies direction while the visible shaft stays stable.
        const shaftLength = FLOW_ARROW_LENGTH_PX;
        const tailX = projectedTail.x;
        const tailY = projectedTail.y;
        const tipX = tailX + dx * shaftLength;
        const tipY = tailY + dy * shaftLength;
        const headLength = shaftLength * 0.28;
        const headWidth = headLength * 0.58;
        const baseX = tipX - dx * headLength;
        const baseY = tipY - dy * headLength;
        const leftX = baseX - dy * headWidth;
        const leftY = baseY + dx * headWidth;
        const rightX = baseX + dy * headWidth;
        const rightY = baseY - dx * headWidth;
        const d = [
          `M ${tailX.toFixed(2)} ${tailY.toFixed(2)} L ${tipX.toFixed(2)} ${tipY.toFixed(2)}`,
          `M ${tipX.toFixed(2)} ${tipY.toFixed(2)} L ${leftX.toFixed(2)} ${leftY.toFixed(2)}`,
          `M ${tipX.toFixed(2)} ${tipY.toFixed(2)} L ${rightX.toFixed(2)} ${rightY.toFixed(2)}`,
        ].join(" ");

        const halo = document.createElementNS(namespace, "path");
        halo.setAttribute("d", d);
        halo.setAttribute("fill", "none");
        halo.setAttribute("stroke", "#FFFFFF");
        halo.setAttribute("stroke-width", "7");
        halo.setAttribute("stroke-linecap", "round");
        halo.setAttribute("stroke-linejoin", "round");
        halo.setAttribute("stroke-opacity", "0.96");
        svg.appendChild(halo);

        const line = document.createElementNS(namespace, "path");
        line.setAttribute("d", d);
        line.setAttribute("fill", "none");
        line.setAttribute("stroke", flowColor(feature.properties.speed_mps, flowSpeedRange, flowSpeedBreaks));
        line.setAttribute("stroke-width", "4");
        line.setAttribute("stroke-linecap", "round");
        line.setAttribute("stroke-linejoin", "round");
        line.setAttribute("stroke-opacity", "1");
        svg.appendChild(line);
      }
      svg.dataset.flowSvgArrows = String(displayFlow.features.length);
    };

    const report = () => {
      const bounds = map.getBounds();
      onFlowRenderStats?.({
        sourceFeatureCount: map.querySourceFeatures(FLOW_SOURCE_ID).length,
        renderedFeatureCount: map.queryRenderedFeatures({
          layers: [FLOW_LINE_LAYER_ID],
        }).length,
        svgArrowCount: Number(svg.dataset.flowSvgArrows ?? "0"),
        layerOrder: (map.getStyle().layers ?? []).map((layer) => layer.id),
        featureBounds: featureBounds(),
        mapBounds: [
          bounds.getWest(),
          bounds.getSouth(),
          bounds.getEast(),
          bounds.getNorth(),
        ],
      });
    };

    const update = () => {
      const displayFlow = flowDisplayMode === "vectors" ? flowVectorData : null;
      const source = map.getSource(FLOW_SOURCE_ID) as GeoJSONSource | undefined;
      source?.setData(flowVectorData ?? EMPTY_FLOW);
      const visibility = displayFlow && displayFlow.features.length > 0
        ? "visible"
        : "none";
      map.setLayoutProperty(FLOW_HALO_LAYER_ID, "visibility", visibility);
      map.setLayoutProperty(FLOW_LINE_LAYER_ID, "visibility", visibility);

      // Keep an explicit deterministic stack after any source/image update.
      // Result raster < MapLibre vector layers < analysis boundary.
      map.moveLayer(FLOW_HALO_LAYER_ID);
      map.moveLayer(FLOW_LINE_LAYER_ID);
      map.moveLayer("analysis-boundary-casing");
      map.moveLayer("analysis-boundary-outline");
      map.setLayoutProperty("analysis-boundary-casing", "visibility", "visible");
      map.setLayoutProperty("analysis-boundary-outline", "visibility", "visible");

      // Independent SVG rendering is the visible fallback/guarantee. It uses
      // the same GeoJSON but bypasses MapLibre line-layer rendering entirely.
      renderSvg(displayFlow);

      if (visibility === "none") {
        onFlowRenderStats?.(null);
      } else {
        idleReporter = report;
        map.once("idle", report);
      }
      map.triggerRepaint();
    };

    map.on("moveend", update);
    map.on("resize", update);

    if (map.getSource(FLOW_SOURCE_ID)) {
      update();
    } else {
      map.once("load", update);
    }
    return () => {
      map.off("load", update);
      map.off("moveend", update);
      map.off("resize", update);
      if (idleReporter) map.off("idle", idleReporter);
      svg.replaceChildren();
      svg.dataset.flowSvgArrows = "0";
    };
  }, [flowDisplayMode, flowVectorData, flowSpeedRange, flowSpeedBreaks, onFlowRenderStats]);

  useEffect(() => {
    const map = overlayMapRef.current;
    const canvas = flowCanvasRef.current;
    if (!map || !canvas) return;
    if (flowDisplayMode !== "particles" || !flowVectorData) {
      canvas.dataset.flowParticles = "0";
      return;
    }

    const context = canvas.getContext("2d");
    if (!context) return;
    const buildField = () => createProjectedFlowField(flowVectorData.features.flatMap((feature) => {
      const shaft = feature.geometry.coordinates[0];
      if (!shaft || shaft.length < 2) return [];
      const tail = map.project([shaft[0][0], shaft[0][1]]);
      const tip = map.project([shaft[shaft.length - 1][0], shaft[shaft.length - 1][1]]);
      const length = Math.hypot(tip.x - tail.x, tip.y - tail.y);
      if (length <= 1e-6) return [];
      return [{
        x: tail.x,
        y: tail.y,
        dx: (tip.x - tail.x) / length,
        dy: (tip.y - tail.y) / length,
        speedMps: feature.properties.speed_mps,
        speedPxPerSecond: particleSpeedPxPerSecond(feature.properties.speed_mps),
      }];
    }));

    let field = buildField();
    const resetParticle = (
      particle: FlowParticle,
      index: number,
      staggerInitialLifetime = false,
    ) => {
      if (field.nodes.length === 0) return;
      particle.generation += 1;
      const seedIndex = particle.sourceIndex % field.nodes.length;
      const seed = field.nodes[seedIndex];
      const sourceFeature = flowVectorData.features[seedIndex % flowVectorData.features.length];
      const phase = particlePhase(
        (sourceFeature?.properties.row ?? seedIndex) + particle.copyIndex * 1009,
        (sourceFeature?.properties.column ?? seedIndex) + particle.generation,
      );
      const offset = (phase - 0.5) * field.spacingPx;
      particle.x = seed.x + seed.dx * offset;
      particle.y = seed.y + seed.dy * offset;
      particle.targetDistancePx = field.spacingPx * PARTICLE_MIN_VECTOR_CROSSINGS;
      particle.travelledPx = staggerInitialLifetime
        ? particle.targetDistancePx * (index % PARTICLE_PHASE_GROUPS) / PARTICLE_PHASE_GROUPS
        : 0;
      particle.trail = [{ x: particle.x, y: particle.y }];
    };
    const createParticles = () => field.nodes.flatMap((node, sourceIndex) => (
      Array.from({ length: PARTICLES_PER_VECTOR }, (_, copyIndex) => {
        const particleIndex = sourceIndex * PARTICLES_PER_VECTOR + copyIndex;
        const particle: FlowParticle = {
          sourceIndex,
          copyIndex,
          x: node.x,
          y: node.y,
          travelledPx: 0,
          targetDistancePx: field.spacingPx * PARTICLE_MIN_VECTOR_CROSSINGS,
          trail: [{ x: node.x, y: node.y }],
          generation: -1,
        };
        resetParticle(particle, particleIndex, true);
        return particle;
      })
    ));
    let particles: FlowParticle[] = createParticles();
    const rebuildField = () => {
      field = buildField();
      particles = createParticles();
      canvas.dataset.flowParticleSpacingPx = field.spacingPx.toFixed(1);
      canvas.dataset.flowParticleTargetDistancePx = (
        field.spacingPx * PARTICLE_MIN_VECTOR_CROSSINGS
      ).toFixed(1);
    };
    canvas.dataset.flowParticleMinCrossings = String(PARTICLE_MIN_VECTOR_CROSSINGS);
    canvas.dataset.flowParticlesPerVector = String(PARTICLES_PER_VECTOR);
    canvas.dataset.flowParticlePhaseGroups = String(PARTICLE_PHASE_GROUPS);
    canvas.dataset.flowParticleSeedPolicy = "fixed-source";
    canvas.dataset.flowParticlePhaseMode = "lifetime-offset";
    canvas.dataset.flowParticleTrailLengthPx = String(PARTICLE_TRAIL_LENGTH_PX);
    canvas.dataset.flowParticleSpacingPx = field.spacingPx.toFixed(1);
    canvas.dataset.flowParticleTargetDistancePx = (
      field.spacingPx * PARTICLE_MIN_VECTOR_CROSSINGS
    ).toFixed(1);
    map.on("moveend", rebuildField);
    map.on("resize", rebuildField);

    let frame = 0;
    let disposed = false;
    let previousFrameMs: number | null = null;

    const render = (now: number) => {
      if (disposed) return;
      const ratio = window.devicePixelRatio || 1;
      const width = Math.max(1, canvas.clientWidth);
      const height = Math.max(1, canvas.clientHeight);
      const pixelWidth = Math.round(width * ratio);
      const pixelHeight = Math.round(height * ratio);
      if (canvas.width !== pixelWidth || canvas.height !== pixelHeight) {
        canvas.width = pixelWidth;
        canvas.height = pixelHeight;
      }
      context.setTransform(ratio, 0, 0, ratio, 0, 0);
      context.clearRect(0, 0, width, height);
      const elapsedSeconds = previousFrameMs === null
        ? 1 / 60
        : Math.min(0.05, Math.max(0, (now - previousFrameMs) / 1000));
      previousFrameMs = now;

      let rendered = 0;
      particles.forEach((particle, index) => {
        let flow = sampleProjectedFlow(field, particle.x, particle.y);
        if (!flow) {
          resetParticle(particle, index);
          flow = sampleProjectedFlow(field, particle.x, particle.y);
        }
        if (!flow) return;
        const distance = flow.speedPxPerSecond * elapsedSeconds;
        particle.x += flow.dx * distance;
        particle.y += flow.dy * distance;
        particle.travelledPx += distance;
        appendTrailPoint(particle, { x: particle.x, y: particle.y });

        const outsideViewport = particle.x < -6
          || particle.y < -6
          || particle.x > width + 6
          || particle.y > height + 6;
        if (outsideViewport || particle.travelledPx >= particle.targetDistancePx) {
          resetParticle(particle, index);
          flow = sampleProjectedFlow(field, particle.x, particle.y);
          if (!flow) return;
        }

        const particleColor = flowColor(flow.speedMps, flowSpeedRange, flowSpeedBreaks);
        drawFadingTrail(context, particle.trail, particleColor);

        // The particle itself is a zero-length point; only its fading history
        // forms a line behind it.
        context.beginPath();
        context.arc(particle.x, particle.y, 3.2, 0, Math.PI * 2);
        context.fillStyle = "rgba(255, 255, 255, 0.92)";
        context.fill();
        context.beginPath();
        context.arc(particle.x, particle.y, 1.8, 0, Math.PI * 2);
        context.fillStyle = particleColor;
        context.fill();
        rendered += 1;
      });
      canvas.dataset.flowParticles = String(rendered);
      frame = window.requestAnimationFrame(render);
    };

    frame = window.requestAnimationFrame(render);
    return () => {
      disposed = true;
      window.cancelAnimationFrame(frame);
      map.off("moveend", rebuildField);
      map.off("resize", rebuildField);
      context.clearRect(0, 0, canvas.width, canvas.height);
      canvas.dataset.flowParticles = "0";
    };
  }, [flowDisplayMode, flowVectorData, flowSpeedRange, flowSpeedBreaks]);

  return (
    <div className="result-map-stack" role="region" aria-label={mapLabel}>
      <div
        ref={baseContainerRef}
        className="result-map result-map-base"
        style={{ opacity: Math.max(0, Math.min(1, backgroundOpacity)) }}
        aria-hidden="true"
      />
      <div
        ref={overlayContainerRef}
        className="result-map result-map-overlay"
      />
      <svg
        ref={flowSvgRef}
        className="result-flow-svg"
        aria-hidden="true"
        data-flow-svg-arrows="0"
      />
      <canvas
        ref={flowCanvasRef}
        className="result-flow-canvas"
        aria-hidden="true"
        data-flow-particles="0"
      />
    </div>
  );
}
