import { useEffect, useRef } from "react";
import {
  ImageSource,
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
  mapLabel: string;
  onInspect: (lon: number, lat: number) => void;
};

export default function ResultMap({
  metadata,
  imageUrl,
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
          "result-overlay": {
            type: "image",
            url: imageUrl,
            coordinates: resultImageCoordinates(metadata.bounds),
          },
        },
        layers: [
          {
            id: "gsi",
            type: "raster",
            source: "gsi",
          },
          {
            id: "result-overlay",
            type: "raster",
            source: "result-overlay",
            paint: {
              "raster-opacity": 0.82,
            },
          },
        ],
      },
      bounds: resultBounds(metadata.bounds),
      fitBoundsOptions: { padding: 32, maxZoom: 18 },
      attributionControl: true,
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

    const updateImage = () => {
      const source = map.getSource("result-overlay") as ImageSource | undefined;
      source?.updateImage({
        url: imageUrl,
        coordinates: resultImageCoordinates(metadata.bounds),
      });
    };

    if (map.isStyleLoaded()) {
      updateImage();
      return;
    }

    map.once("load", updateImage);
    return () => {
      map.off("load", updateImage);
    };
  }, [imageUrl, metadata]);

  return (
    <div
      ref={containerRef}
      className="result-map"
      aria-label={mapLabel}
    />
  );
}
