import { useEffect, useRef } from "react";
import {
  GeoJSONSource,
  ImageSource,
  Map as MapLibreMap,
  Marker,
  NavigationControl,
  type MapMouseEvent,
  type StyleSpecification,
} from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";

import type { ResultMetadataResponse } from "../api/client";
import { resultBounds, resultImageCoordinates } from "./resultGeometry";

type Props = {
  metadata: ResultMetadataResponse;
  imageUrl: string;
  flowVectorUrl: string | null;
  backgroundOpacity: number;
  mapLabel: string;
  onInspect: (lon: number, lat: number) => void;
};

const EMPTY_FLOW = {
  type: "FeatureCollection" as const,
  features: [],
};

function overlayStyle(
  metadata: ResultMetadataResponse,
  imageUrl: string,
): StyleSpecification {
  const coordinates = resultImageCoordinates(metadata.bounds);
  return {
    version: 8,
    sources: {
      "result-overlay": {
        type: "image",
        url: imageUrl,
        coordinates,
      },
      "flow-vectors": {
        type: "geojson",
        data: EMPTY_FLOW,
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
        id: "flow-vectors",
        type: "line",
        source: "flow-vectors",
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
            0.01, 1.6,
            0.50, 2.2,
            2.00, 3.2,
          ],
          "line-opacity": 0.95,
        },
      },
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
    ],
  };
}

export default function ResultMap({
  metadata,
  imageUrl,
  flowVectorUrl,
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
  const initialImageUrlRef = useRef(imageUrl);

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
      style: overlayStyle(metadata, initialImageUrlRef.current),
      bounds,
      fitBoundsOptions: { padding: 32, maxZoom: 18 },
      attributionControl: false,
    });
    overlayMapRef.current = overlayMap;
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
  }, [metadata]);

  useEffect(() => {
    const map = overlayMapRef.current;
    if (!map) return;
    const update = () => {
      const source = map.getSource("result-overlay");
      if (!(source instanceof ImageSource)) return;
      source.updateImage({
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
    return () => map.off("load", update);
  }, [imageUrl, metadata.bounds]);

  useEffect(() => {
    const map = overlayMapRef.current;
    if (!map) return;
    const update = () => {
      const source = map.getSource("flow-vectors");
      if (!(source instanceof GeoJSONSource)) return;
      source.setData(flowVectorUrl ?? EMPTY_FLOW);
      map.setLayoutProperty(
        "flow-vectors",
        "visibility",
        flowVectorUrl ? "visible" : "none",
      );
      map.triggerRepaint();
    };
    if (map.getSource("flow-vectors")) {
      update();
      return;
    }
    map.once("load", update);
    return () => map.off("load", update);
  }, [flowVectorUrl]);

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
