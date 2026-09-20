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
  overlayOpacity: number;
  mapLabel: string;
  onInspect: (lon: number, lat: number) => void;
};

export default function ResultMap({
  metadata,
  imageUrl,
  flowImageUrl,
  overlayOpacity,
  mapLabel,
  onInspect,
}: Props) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<MapLibreMap | null>(null);
  const markerRef = useRef<Marker | null>(null);
  const inspectRef = useRef(onInspect);

  useEffect(() => {
    inspectRef.current = onInspect;
  }, [onInspect]);

  useEffect(() => {
    if (!containerRef.current) return;

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

    const replaceResult = () => {
      if (map.getLayer("result-overlay")) map.removeLayer("result-overlay");
      if (map.getSource("result-overlay")) map.removeSource("result-overlay");
      map.addSource("result-overlay", {
        type: "image",
        url: imageUrl,
        coordinates: resultImageCoordinates(metadata.bounds),
      });
      map.addLayer(
        {
          id: "result-overlay",
          type: "raster",
          source: "result-overlay",
          paint: {
            "raster-opacity": overlayOpacity,
          },
        },
        "analysis-boundary-fill",
      );
      map.triggerRepaint();
    };

    if (map.isStyleLoaded()) {
      replaceResult();
      return;
    }
    map.once("load", replaceResult);
    return () => {
      map.off("load", replaceResult);
    };
  }, [imageUrl, metadata, overlayOpacity]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;

    const replaceFlow = () => {
      if (map.getLayer("flow-overlay")) map.removeLayer("flow-overlay");
      if (map.getSource("flow-overlay")) map.removeSource("flow-overlay");
      if (!flowImageUrl) {
        map.triggerRepaint();
        return;
      }
      map.addSource("flow-overlay", {
        type: "image",
        url: flowImageUrl,
        coordinates: resultImageCoordinates(metadata.bounds),
      });
      map.addLayer(
        {
          id: "flow-overlay",
          type: "raster",
          source: "flow-overlay",
          paint: {
            "raster-opacity": 0.95,
          },
        },
        "analysis-boundary-fill",
      );
      map.triggerRepaint();
    };

    if (map.isStyleLoaded()) {
      replaceFlow();
      return;
    }
    map.once("load", replaceFlow);
    return () => {
      map.off("load", replaceFlow);
    };
  }, [flowImageUrl, metadata]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !map.getLayer("result-overlay")) return;
    map.setPaintProperty("result-overlay", "raster-opacity", overlayOpacity);
    map.triggerRepaint();
  }, [overlayOpacity]);

  return (
    <div
      ref={containerRef}
      className="result-map"
      role="region"
      aria-label={mapLabel}
    />
  );
}
