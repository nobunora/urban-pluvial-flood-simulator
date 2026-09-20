import { useEffect, useRef } from "react";
import {
  Map as MapLibreMap,
  Marker,
  NavigationControl,
  type MapMouseEvent,
} from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";

import type { ResultMetadataResponse } from "../api/client";
import { resultBounds, resultImageCoordinates } from "./resultGeometry";

type Props = {
  metadata: ResultMetadataResponse;
  imageUrl: string;
  flowImageUrl: string | null;
  backgroundOpacity: number;
  mapLabel: string;
  onInspect: (lon: number, lat: number) => void;
};

function overlayStyle(
  metadata: ResultMetadataResponse,
  imageUrl: string,
  flowImageUrl: string | null,
) {
  const coordinates = resultImageCoordinates(metadata.bounds);
  const sources: Record<string, object> = {
    "result-overlay": {
      type: "image",
      url: imageUrl,
      coordinates,
    },
    "analysis-boundary": {
      type: "geojson",
      data: {
        type: "Feature",
        properties: {},
        geometry: {
          type: "Polygon",
          coordinates: [[
            [metadata.bounds.west_deg, metadata.bounds.south_deg],
            [metadata.bounds.east_deg, metadata.bounds.south_deg],
            [metadata.bounds.east_deg, metadata.bounds.north_deg],
            [metadata.bounds.west_deg, metadata.bounds.north_deg],
            [metadata.bounds.west_deg, metadata.bounds.south_deg],
          ]],
        },
      },
    },
  };
  const layers: object[] = [
    {
      id: "result-overlay",
      type: "raster",
      source: "result-overlay",
      paint: {
        "raster-opacity": 1,
        "raster-fade-duration": 0,
      },
    },
  ];

  if (flowImageUrl) {
    sources["flow-overlay"] = {
      type: "image",
      url: flowImageUrl,
      coordinates,
    };
    layers.push({
      id: "flow-overlay",
      type: "raster",
      source: "flow-overlay",
      paint: {
        "raster-opacity": 1,
        "raster-fade-duration": 0,
      },
    });
  }

  layers.push(
    {
      id: "analysis-boundary-fill",
      type: "fill",
      source: "analysis-boundary",
      paint: {
        "fill-color": "#DC2626",
        "fill-opacity": 0.02,
      },
    },
    {
      id: "analysis-boundary-outline",
      type: "line",
      source: "analysis-boundary",
      paint: {
        "line-color": "#DC2626",
        "line-width": 4,
      },
    },
  );

  return {
    version: 8 as const,
    sources,
    layers,
  };
}

export default function ResultMap({
  metadata,
  imageUrl,
  flowImageUrl,
  backgroundOpacity,
  mapLabel,
  onInspect,
}: Props) {
  const baseContainerRef = useRef<HTMLDivElement | null>(null);
  const overlayContainerRef = useRef<HTMLDivElement | null>(null);
  const baseMapRef = useRef<MapLibreMap | null>(null);
  const overlayMapRef = useRef<MapLibreMap | null>(null);
  const markerRef = useRef<Marker | null>(null);
  const inspectRef = useRef(onInspect);
  const viewRef = useRef<{
    center: [number, number];
    zoom: number;
    bearing: number;
    pitch: number;
  } | null>(null);

  useEffect(() => {
    inspectRef.current = onInspect;
  }, [onInspect]);

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
      style: overlayStyle(metadata, imageUrl, flowImageUrl),
      bounds,
      fitBoundsOptions: { padding: 32, maxZoom: 18 },
      attributionControl: false,
    });
    overlayMapRef.current = overlayMap;
    overlayMap.addControl(new NavigationControl({ showCompass: false }), "top-right");

    const syncBase = () => {
      const center = overlayMap.getCenter();
      const view = {
        center: [center.lng, center.lat] as [number, number],
        zoom: overlayMap.getZoom(),
        bearing: overlayMap.getBearing(),
        pitch: overlayMap.getPitch(),
      };
      viewRef.current = view;
      baseMap.jumpTo(view);
    };

    const handleClick = (event: MapMouseEvent) => {
      markerRef.current?.remove();
      markerRef.current = new Marker({ color: "#1f2937" })
        .setLngLat(event.lngLat)
        .addTo(overlayMap);
      inspectRef.current(event.lngLat.lng, event.lngLat.lat);
    };

    overlayMap.on("move", syncBase);
    overlayMap.on("click", handleClick);
    overlayMap.once("load", syncBase);

    return () => {
      markerRef.current?.remove();
      markerRef.current = null;
      overlayMap.off("move", syncBase);
      overlayMap.off("click", handleClick);
      overlayMap.remove();
      baseMap.remove();
      overlayMapRef.current = null;
      baseMapRef.current = null;
    };
  }, [metadata, imageUrl, flowImageUrl]);

  useEffect(() => {
    const view = viewRef.current;
    const overlayMap = overlayMapRef.current;
    const baseMap = baseMapRef.current;
    if (!view || !overlayMap || !baseMap) return;
    overlayMap.jumpTo(view);
    baseMap.jumpTo(view);
  }, [imageUrl, flowImageUrl]);

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
    </div>
  );
}
