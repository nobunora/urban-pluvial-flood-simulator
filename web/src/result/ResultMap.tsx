import { useEffect, useRef } from "react";
import {
  Map as MapLibreMap,
  Marker,
  NavigationControl,
  type GeoJSONSource,
  type ImageSource,
  type MapMouseEvent,
  type StyleSpecification,
} from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";

import type {
  FlowVectorFeatureCollection,
  FlowViewport,
  ResultMetadataResponse,
} from "../api/client";
import { resultBounds, resultImageCoordinates } from "./resultGeometry";

export type FlowRenderStats = {
  sourceFeatureCount: number;
  renderedFeatureCount: number;
  svgArrowCount: number;
  layerOrder: string[];
  featureBounds: [number, number, number, number] | null;
  mapBounds: [number, number, number, number];
};

type Props = {
  metadata: ResultMetadataResponse;
  imageUrl: string;
  flowVectorData: FlowVectorFeatureCollection | null;
  backgroundOpacity: number;
  mapLabel: string;
  onInspect: (lon: number, lat: number) => void;
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

function flowColor(speedMps: number): string {
  if (speedMps >= 2.0) return "#7F0000";
  if (speedMps >= 1.0) return "#E74C3C";
  if (speedMps >= 0.5) return "#8E44AD";
  if (speedMps >= 0.3) return "#3F51B5";
  if (speedMps >= 0.1) return "#3BB2D0";
  return "#2DC4B2";
}

function overlayStyle(
  metadata: ResultMetadataResponse,
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
  backgroundOpacity,
  mapLabel,
  onInspect,
  onFlowRenderStats,
}: Props) {
  const baseContainerRef = useRef<HTMLDivElement | null>(null);
  const overlayContainerRef = useRef<HTMLDivElement | null>(null);
  const baseMapRef = useRef<MapLibreMap | null>(null);
  const overlayMapRef = useRef<MapLibreMap | null>(null);
  const markerRef = useRef<Marker | null>(null);
  const flowSvgRef = useRef<SVGSVGElement | null>(null);
  const inspectRef = useRef(onInspect);
  const viewportRef = useRef(onViewportChange);
  const viewportRef = useRef(onViewportChange);
  const viewportRef = useRef(onViewportChange);
  const initialImageUrlRef = useRef(imageUrl);

  useEffect(() => {
    inspectRef.current = onInspect;
  }, [onInspect]);

  useEffect(() => {
    viewportRef.current = onViewportChange;
  }, [onViewportChange]);

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
            attribution: "国土地理院",
          },
        },
        layers: [{ id: "gsi", type: "raster", source: "gsi" }],
      },
      bounds,
      fitBoundsOptions: { padding: 32, maxZoom: 18 },
      interactive: false,
    });
    baseMapRef.current = baseMap;

    const overlayMap = new MapLibreMap({
      container: overlayContainer,
      style: overlayStyle(metadata, initialImageUrlRef.current),
      bounds,
      fitBoundsOptions: { padding: 32, maxZoom: 18 },
      attributionControl: false,
      preserveDrawingBuffer: true,
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
      markerRef.current?.remove();
      markerRef.current = new Marker({ color: "#1f2937" })
        .setLngLat(event.lngLat)
        .addTo(overlayMap);
      inspectRef.current(event.lngLat.lng, event.lngLat.lat);
    };

    overlayMap.on("move", syncBase);
    overlayMap.on("moveend", emitViewport);
    overlayMap.on("click", handleClick);
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

        // The backend geometry already encodes the physical sampling rule:
        // shaft length = 0.8 * vector spacing. Never impose a pixel minimum,
        // because that would destroy the length/spacing ratio after zoom-time
        // decimation.
        const shaftLength = rawLength;
        const tipX = projectedTip.x;
        const tipY = projectedTip.y;
        const tailX = projectedTail.x;
        const tailY = projectedTail.y;
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
        line.setAttribute("stroke", flowColor(feature.properties.speed_mps));
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
      const displayFlow = flowVectorData;
      const source = map.getSource(FLOW_SOURCE_ID) as GeoJSONSource | undefined;
      source?.setData(displayFlow ?? EMPTY_FLOW);
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
  }, [flowVectorData, onFlowRenderStats]);

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
    </div>
  );
}
