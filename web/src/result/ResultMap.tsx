import { useEffect, useRef } from "react";
import {
  Map as MapLibreMap,
  Marker,
  NavigationControl,
  type ImageSource,
  type MapMouseEvent,
} from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";

import type { ResultMetadataResponse } from "../api/client";
import { resultBounds, resultImageCoordinates } from "./resultGeometry";

const TRANSPARENT_PIXEL =
  "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M/wHwAF/gL+Xo6kWQAAAABJRU5ErkJggg==";

type Props = {
  metadata: ResultMetadataResponse;
  imageUrl: string;
  flowImageUrl: string | null;
  backgroundOpacity: number;
  mapLabel: string;
  onInspect: (lon: number, lat: number) => void;
};

export default function ResultMap({
  metadata,
  imageUrl,
  flowImageUrl,
  backgroundOpacity,
  mapLabel,
  onInspect,
}: Props) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<MapLibreMap | null>(null);
  const markerRef = useRef<Marker | null>(null);
  const inspectRef = useRef(onInspect);
  const initialImageUrlRef = useRef(imageUrl);
  const initialFlowUrlRef = useRef(flowImageUrl ?? TRANSPARENT_PIXEL);
  const initialBackgroundOpacityRef = useRef(backgroundOpacity);

  useEffect(() => {
    inspectRef.current = onInspect;
  }, [onInspect]);

  useEffect(() => {
    if (!containerRef.current) return;

    const coordinates = resultImageCoordinates(metadata.bounds);
    const map = new MapLibreMap({
      container: containerRef.current,
      style: {
        version: 8,
        sources: {
          gsi: {
            type: "raster",
            tiles: ["https://cyberjapandata.gsi.go.jp/xyz/std/{z}/{x}/{y}.png"],
            tileSize: 256,
            attribution: "国土地理院",
          },
          "result-overlay": {
            type: "image",
            url: initialImageUrlRef.current,
            coordinates,
          },
          "flow-overlay": {
            type: "image",
            url: initialFlowUrlRef.current,
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
        },
        layers: [
          {
            id: "gsi",
            type: "raster",
            source: "gsi",
            paint: {
              "raster-opacity": initialBackgroundOpacityRef.current,
            },
          },
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
            id: "flow-overlay",
            type: "raster",
            source: "flow-overlay",
            paint: {
              "raster-opacity": flowImageUrl ? 1 : 0,
              "raster-fade-duration": 0,
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
      },
      bounds: resultBounds(metadata.bounds),
      fitBoundsOptions: { padding: 32, maxZoom: 18 },
    });
    mapRef.current = map;
    map.addControl(new NavigationControl({ showCompass: false }), "top-right");

    const handleClick = (event: MapMouseEvent) => {
      markerRef.current?.remove();
      markerRef.current = new Marker({ color: "#1f2937" })
        .setLngLat(event.lngLat)
        .addTo(map);
      inspectRef.current(event.lngLat.lng, event.lngLat.lat);
    };
    map.on("click", handleClick);

    return () => {
      markerRef.current?.remove();
      markerRef.current = null;
      map.off("click", handleClick);
      map.remove();
      mapRef.current = null;
    };
  }, [metadata]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    const update = () => {
      const source = map.getSource("result-overlay") as ImageSource | undefined;
      source?.updateImage({
        url: imageUrl,
        coordinates: resultImageCoordinates(metadata.bounds),
      });
      map.triggerRepaint();
    };
    if (map.isStyleLoaded()) update();
    else map.once("load", update);
    return () => {
      map.off("load", update);
    };
  }, [imageUrl, metadata.bounds]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    const update = () => {
      const source = map.getSource("flow-overlay") as ImageSource | undefined;
      source?.updateImage({
        url: flowImageUrl ?? TRANSPARENT_PIXEL,
        coordinates: resultImageCoordinates(metadata.bounds),
      });
      if (map.getLayer("flow-overlay")) {
        map.setPaintProperty("flow-overlay", "raster-opacity", flowImageUrl ? 1 : 0);
      }
      map.triggerRepaint();
    };
    if (map.isStyleLoaded()) update();
    else map.once("load", update);
    return () => {
      map.off("load", update);
    };
  }, [flowImageUrl, metadata.bounds]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    const update = () => {
      if (map.getLayer("gsi")) {
        map.setPaintProperty("gsi", "raster-opacity", backgroundOpacity);
      }
      map.triggerRepaint();
    };
    if (map.isStyleLoaded()) update();
    else map.once("load", update);
    return () => {
      map.off("load", update);
    };
  }, [backgroundOpacity]);

  return (
    <div
      ref={containerRef}
      className="result-map"
      role="region"
      aria-label={mapLabel}
    />
  );
}
